import json
import logging
import os
import azure.functions as func

# Configurar logging
logging.basicConfig(level=logging.INFO)


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AFP Prima chat function started")

    # Configure CORS headers
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Content-Type": "application/json",
    }

    # Handle preflight OPTIONS request
    if req.method == "OPTIONS":
        logging.info("Handling OPTIONS request")
        return func.HttpResponse("", status_code=200, headers=headers)

    try:
        # Test basic functionality first
        if req.method == "GET":
            return func.HttpResponse(
                json.dumps({"message": "Chat API is working", "method": "GET"}),
                status_code=200,
                headers=headers,
            )

        # Parse request body for POST
        if req.method == "POST":
            try:
                req_body = req.get_json()
                if not req_body or "message" not in req_body:
                    return func.HttpResponse(
                        json.dumps({"error": "Message is required"}),
                        status_code=400,
                        headers=headers,
                    )

                user_message = req_body["message"]
                logging.info(f"Received message: {user_message}")

                # Get environment variables
                endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")
                api_key = os.environ.get("AZURE_AI_PROJECT_API_KEY")

                logging.info(
                    f"Environment check - Endpoint: {bool(endpoint)}, Agent: {bool(agent_id)}, Key: {bool(api_key)}"
                )

                # Check if environment variables are set
                missing_vars = []
                if not endpoint:
                    missing_vars.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                if not agent_id:
                    missing_vars.append("AZURE_EXISTING_AGENT_ID")
                if not api_key:
                    missing_vars.append("AZURE_AI_PROJECT_API_KEY")

                if missing_vars:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Missing environment variables",
                                "missing": missing_vars,
                                "help": "Configure these in Azure Static Web Apps settings",
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )

                # Try to import and use Azure AI
                try:
                    from azure.ai.projects import AIProjectClient
                    from azure.core.credentials import AzureKeyCredential

                    logging.info("Azure AI imports successful")

                    # Initialize client
                    credential = AzureKeyCredential(api_key)
                    project = AIProjectClient(
                        credential=credential,
                        endpoint=endpoint,
                    )

                    logging.info("AIProjectClient initialized")

                    # Get agent
                    agent = project.agents.get_agent(agent_id)
                    logging.info(f"Agent retrieved: {agent.id}")

                    # Create thread
                    thread = project.agents.threads.create()
                    logging.info(f"Thread created: {thread.id}")

                    # Create message
                    message = project.agents.messages.create(
                        thread_id=thread.id, role="user", content=user_message
                    )

                    # Run agent
                    run = project.agents.runs.create_and_process(
                        thread_id=thread.id, agent_id=agent.id
                    )

                    logging.info(f"Agent run status: {run.status}")

                    if run.status == "failed":
                        return func.HttpResponse(
                            json.dumps(
                                {
                                    "error": "Agent run failed",
                                    "details": str(
                                        getattr(run, "last_error", "Unknown error")
                                    ),
                                }
                            ),
                            status_code=500,
                            headers=headers,
                        )

                    # Get response
                    messages = project.agents.messages.list(thread_id=thread.id)

                    assistant_response = ""
                    if messages:
                        for msg in reversed(messages):
                            if (
                                msg.role == "assistant"
                                and hasattr(msg, "text_messages")
                                and msg.text_messages
                            ):
                                assistant_response = msg.text_messages[-1].text.value
                                break

                    if not assistant_response:
                        assistant_response = "Lo siento, no pude generar una respuesta."

                    return func.HttpResponse(
                        json.dumps({"response": assistant_response}),
                        status_code=200,
                        headers=headers,
                    )

                except ImportError as e:
                    logging.error(f"Import error: {str(e)}")
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Azure AI libraries not available",
                                "details": str(e),
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )
                except Exception as e:
                    logging.error(f"Azure AI error: {str(e)}")
                    return func.HttpResponse(
                        json.dumps(
                            {"error": "Azure AI processing failed", "details": str(e)}
                        ),
                        status_code=500,
                        headers=headers,
                    )

            except json.JSONDecodeError as e:
                return func.HttpResponse(
                    json.dumps({"error": "Invalid JSON in request"}),
                    status_code=400,
                    headers=headers,
                )

        # Unsupported method
        return func.HttpResponse(
            json.dumps({"error": f"Method {req.method} not supported"}),
            status_code=405,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Internal server error",
                    "details": str(e),
                    "type": type(e).__name__,
                }
            ),
            status_code=500,
            headers=headers,
        )
