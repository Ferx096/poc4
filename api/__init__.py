import json
import logging
import os
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
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

        # DEBUG: Log all environment variables (sin mostrar valores sensibles)
        env_vars = {
            k: (
                "***"
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower()
                else v
            )
            for k, v in os.environ.items()
            if k.startswith("AZURE")
        }
        logging.info(f"Available Azure environment variables: {list(env_vars.keys())}")

        if not endpoint or not agent_id:
            logging.error(
                f"Missing environment variables. Endpoint: {bool(endpoint)}, Agent ID: {bool(agent_id)}"
            )
            logging.error(
                f"AZURE_EXISTING_AIPROJECT_ENDPOINT: {'SET' if endpoint else 'NOT SET'}"
            )
            logging.error(
                f"AZURE_EXISTING_AGENT_ID: {'SET' if agent_id else 'NOT SET'}"
            )

            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Server configuration error. Missing environment variables.",
                        "debug": {
                            "endpoint_set": bool(endpoint),
                            "agent_id_set": bool(agent_id),
                        },
                    }
                ),
                status_code=500,
                headers=headers,
            )

        logging.info(f"Using endpoint: {endpoint}")
        logging.info(f"Using agent ID: {agent_id}")

        # Try different credential types for Azure Functions
        credential = None
        credential_type = "unknown"

        try:
            # Try Managed Identity first (recommended for Azure Functions)
            credential = ManagedIdentityCredential()
            credential_type = "ManagedIdentity"
            logging.info("Using ManagedIdentityCredential")

            # Test credential by getting a token
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            logging.info(f"Successfully obtained token with {credential_type}")

        except Exception as e:
            logging.warning(f"ManagedIdentityCredential failed: {e}")
            try:
                # Fallback to DefaultAzureCredential
                credential = DefaultAzureCredential()
                credential_type = "DefaultAzureCredential"
                logging.info("Using DefaultAzureCredential")

                # Test credential by getting a token
                token = credential.get_token(
                    "https://cognitiveservices.azure.com/.default"
                )
                logging.info(f"Successfully obtained token with {credential_type}")

            except Exception as e2:
                logging.error(f"All credential methods failed: {e2}")
                return func.HttpResponse(
                    json.dumps(
                        {
                            "error": "Authentication configuration error",
                            "debug": {
                                "managed_identity_error": str(e),
                                "default_credential_error": str(e2),
                            },
                        }
                    ),
                    status_code=500,
                    headers=headers,
                )

        # Initialize Azure AI Project Client
        try:
            project = AIProjectClient(
                credential=credential,
                endpoint=endpoint,
            )
            logging.info("Successfully initialized AIProjectClient")
        except Exception as e:
            logging.error(f"Failed to initialize AIProjectClient: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to initialize AI client",
                        "debug": {
                            "details": str(e),
                            "endpoint": endpoint,
                            "credential_type": credential_type,
                        },
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Get your agent
        try:
            agent = project.agents.get_agent(agent_id)
            logging.info(f"Successfully retrieved agent: {agent.id}")
        except Exception as e:
            logging.error(f"Failed to get agent: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to retrieve agent",
                        "debug": {
                            "details": str(e),
                            "agent_id": agent_id,
                            "endpoint": endpoint,
                        },
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Create a new thread for each conversation
        try:
            thread = project.agents.threads.create()
            logging.info(f"Created thread: {thread.id}")
        except Exception as e:
            logging.error(f"Failed to create thread: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to create conversation thread",
                        "debug": {"details": str(e)},
                    }
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
            logging.error(f"Failed to create message: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to create message",
                        "debug": {
                            "details": str(e),
                            "thread_id": getattr(thread, "id", "unknown"),
                        },
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
            logging.error(f"Failed to run agent: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to process request with agent",
                        "debug": {
                            "details": str(e),
                            "thread_id": getattr(thread, "id", "unknown"),
                            "agent_id": agent_id,
                        },
                    }
                ),
                status_code=500,
                headers=headers,
            )

        if run.status == "failed":
            logging.error(f"Agent run failed: {run.last_error}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Agent processing failed",
                        "debug": {
                            "details": str(run.last_error),
                            "run_status": run.status,
                        },
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
            logging.error(f"Failed to retrieve messages: {e}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Failed to retrieve response",
                        "debug": {
                            "details": str(e),
                            "thread_id": getattr(thread, "id", "unknown"),
                        },
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Extract the assistant's response
        assistant_response = ""
        if messages:
            for msg in messages:
                if msg.role == "assistant" and msg.text_messages:
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
                    "debug": {"details": str(e), "type": "AzureError"},
                }
            ),
            status_code=502,
            headers=headers,
        )
    except Exception as e:
        logging.error(f"Unexpected error processing request: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Internal server error",
                    "debug": {"details": str(e), "type": "UnexpectedError"},
                }
            ),
            status_code=500,
            headers=headers,
        )
