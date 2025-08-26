import json
import logging
import os
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AFP Prima chat function processed a request.")

    # Configure CORS headers
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Content-Type": "application/json",
    }

    # Handle preflight OPTIONS request
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=headers)

    try:
        # Parse request body
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            logging.error("No message provided in request body")
            return func.HttpResponse(
                json.dumps({"error": "Message is required"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Received message: {user_message}")

        # Get configuration from environment variables
        endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")
        api_key = os.environ.get("AZURE_AI_PROJECT_API_KEY")

        # Debug logging (sin exponer valores sensibles)
        logging.info(f"Endpoint configured: {bool(endpoint)}")
        logging.info(f"Agent ID configured: {bool(agent_id)}")
        logging.info(f"API Key configured: {bool(api_key)}")

        if endpoint:
            logging.info(f"Using endpoint: {endpoint}")
        if agent_id:
            logging.info(f"Using agent ID: {agent_id}")

        # Validar que todas las variables estén presentes
        missing_vars = []
        if not endpoint:
            missing_vars.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        if not agent_id:
            missing_vars.append("AZURE_EXISTING_AGENT_ID")
        if not api_key:
            missing_vars.append("AZURE_AI_PROJECT_API_KEY")

        if missing_vars:
            error_msg = (
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )
            logging.error(error_msg)
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Server configuration error",
                        "missing_variables": missing_vars,
                        "help": "Check Azure Static Web App environment variables in the portal",
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Initialize Azure AI Project Client with API Key
        try:
            credential = AzureKeyCredential(api_key)
            project = AIProjectClient(
                credential=credential,
                endpoint=endpoint,
            )
            logging.info("Successfully initialized AIProjectClient with API Key")
        except Exception as e:
            logging.error(f"Failed to initialize AIProjectClient: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to initialize AI client",
                        "details": str(e),
                        "endpoint_provided": bool(endpoint),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Get the agent
        try:
            agent = project.agents.get_agent(agent_id)
            logging.info(f"Successfully retrieved agent: {agent.id}")
        except Exception as e:
            logging.error(f"Failed to get agent {agent_id}: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to retrieve agent",
                        "details": str(e),
                        "agent_id": agent_id,
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Create a new thread
        try:
            thread = project.agents.threads.create()
            logging.info(f"Created thread: {thread.id}")
        except Exception as e:
            logging.error(f"Failed to create thread: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {"error": "Failed to create conversation thread", "details": str(e)}
                ),
                status_code=500,
                headers=headers,
            )

        # Create message
        try:
            message = project.agents.messages.create(
                thread_id=thread.id, role="user", content=user_message
            )
            logging.info(f"Created message in thread {thread.id}")
        except Exception as e:
            logging.error(f"Failed to create message: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to create message",
                        "details": str(e),
                        "thread_id": getattr(thread, "id", "unknown"),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Run the agent
        try:
            run = project.agents.runs.create_and_process(
                thread_id=thread.id, agent_id=agent.id
            )
            logging.info(f"Agent run completed with status: {run.status}")
        except Exception as e:
            logging.error(f"Failed to run agent: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to process request with agent",
                        "details": str(e),
                        "thread_id": getattr(thread, "id", "unknown"),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Check run status
        if run.status == "failed":
            error_details = getattr(run, "last_error", "Unknown error")
            logging.error(f"Agent run failed: {error_details}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Agent processing failed",
                        "details": str(error_details),
                        "run_status": run.status,
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Get messages from the thread
        try:
            messages = project.agents.messages.list(thread_id=thread.id)
            logging.info(
                f"Retrieved {len(messages) if messages else 0} messages from thread"
            )
        except Exception as e:
            logging.error(f"Failed to retrieve messages: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to retrieve response",
                        "details": str(e),
                        "thread_id": getattr(thread, "id", "unknown"),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Extract the assistant's response
        assistant_response = ""
        if messages:
            # Buscar la respuesta más reciente del assistant
            for msg in reversed(messages):  # Revisar en orden inverso
                if (
                    msg.role == "assistant"
                    and hasattr(msg, "text_messages")
                    and msg.text_messages
                ):
                    assistant_response = msg.text_messages[-1].text.value
                    break

        if not assistant_response:
            assistant_response = "Lo siento, no pude generar una respuesta. Por favor intenta nuevamente."
            logging.warning("No assistant response found, using default message")

        logging.info(f"Returning response: {assistant_response[:100]}...")

        return func.HttpResponse(
            json.dumps({"response": assistant_response}),
            status_code=200,
            headers=headers,
        )

    except AzureError as e:
        logging.error(f"Azure service error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Azure service error",
                    "details": str(e),
                    "type": "AzureError",
                }
            ),
            status_code=502,
            headers=headers,
        )
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request", "details": str(e)}),
            status_code=400,
            headers=headers,
        )
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Internal server error",
                    "details": str(e),
                    "type": "UnexpectedError",
                }
            ),
            status_code=500,
            headers=headers,
        )
