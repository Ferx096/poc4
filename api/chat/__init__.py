import json
import logging
import os
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AFP Prima chat function started")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Content-Type": "application/json",
    }

    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=headers)

    if req.method == "GET":
        return func.HttpResponse(
            json.dumps({"message": "Chat API is working", "method": "GET"}),
            status_code=200,
            headers=headers,
        )

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

            # Obtener variables de entorno
            endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
            agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")
            api_key = os.environ.get("AZURE_AI_PROJECT_API_KEY")

            # Limpiar el agent_id si tiene comillas extras
            if agent_id:
                agent_id = agent_id.strip('"')

            # Validar variables requeridas
            if not all([endpoint, agent_id, api_key]):
                missing = []
                if not endpoint:
                    missing.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                if not agent_id:
                    missing.append("AZURE_EXISTING_AGENT_ID")
                if not api_key:
                    missing.append("AZURE_AI_PROJECT_API_KEY")

                logging.error(f"Missing environment variables: {missing}")
                return func.HttpResponse(
                    json.dumps(
                        {"error": "Missing environment variables", "missing": missing}
                    ),
                    status_code=500,
                    headers=headers,
                )

            try:
                logging.info(f"Connecting to endpoint: {endpoint}")
                logging.info(f"Using agent ID: {agent_id}")

                # Crear el cliente de Azure AI Projects con AzureKeyCredential
                credential = AzureKeyCredential(api_key)

                # IMPORTANTE: El endpoint ya incluye /api/projects/PoC
                # No necesitamos parámetros adicionales de subscription_id, etc.
                project_client = AIProjectClient(
                    credential=credential, endpoint=endpoint
                )

                logging.info("AIProjectClient created successfully")

                # Crear un nuevo thread
                thread = project_client.agents.threads.create()
                logging.info(f"Created thread with ID: {thread.id}")

                # Crear mensaje en el thread
                message = project_client.agents.messages.create(
                    thread_id=thread.id, role="user", content=user_message
                )
                logging.info(f"Created message with ID: {message.id}")

                # Ejecutar el agente y esperar respuesta
                # Nota: Usamos assistant_id en lugar de agent_id para el parámetro
                run = project_client.agents.runs.create_and_process(
                    thread_id=thread.id,
                    assistant_id=agent_id,  # El parámetro es assistant_id, no agent_id
                )

                logging.info(f"Run completed with status: {run.status}")

                if run.status == "failed":
                    error_details = getattr(run, "last_error", None)
                    if error_details:
                        logging.error(f"Run failed with error: {error_details}")
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Agent run failed",
                                "details": (
                                    str(error_details)
                                    if error_details
                                    else "Unknown error"
                                ),
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )

                # Obtener los mensajes del thread
                messages = project_client.agents.messages.list(thread_id=thread.id)

                # Buscar la respuesta del asistente
                assistant_response = ""
                for msg in messages:
                    logging.info(f"Message role: {msg.role}")
                    if msg.role == "assistant":
                        # El contenido puede estar en diferentes formatos
                        if hasattr(msg, "content") and msg.content:
                            if isinstance(msg.content, list) and len(msg.content) > 0:
                                content_item = msg.content[0]
                                if hasattr(content_item, "text"):
                                    if hasattr(content_item.text, "value"):
                                        assistant_response = content_item.text.value
                                    else:
                                        assistant_response = str(content_item.text)
                                    break
                            elif isinstance(msg.content, str):
                                assistant_response = msg.content
                                break
                        # Alternativa: verificar text_messages
                        elif hasattr(msg, "text_messages") and msg.text_messages:
                            if len(msg.text_messages) > 0:
                                assistant_response = msg.text_messages[-1].text.value
                                break

                if not assistant_response:
                    # Log para debug
                    logging.warning("No assistant response found in messages")
                    for msg in messages:
                        logging.info(
                            f"Debug - Message: role={msg.role}, content={getattr(msg, 'content', 'N/A')}"
                        )

                    assistant_response = "Lo siento, no pude generar una respuesta. Por favor, intenta de nuevo."

                logging.info(f"Assistant response: {assistant_response[:100]}...")

                return func.HttpResponse(
                    json.dumps({"response": assistant_response}),
                    status_code=200,
                    headers=headers,
                )

            except AttributeError as e:
                logging.error(f"AttributeError: {str(e)}")
                # Este error sugiere que el SDK no se está inicializando correctamente
                return func.HttpResponse(
                    json.dumps(
                        {
                            "error": "SDK initialization error",
                            "details": str(e),
                            "suggestion": "Check if the endpoint format and API key are correct",
                        }
                    ),
                    status_code=500,
                    headers=headers,
                )

            except ImportError as e:
                logging.error(f"ImportError: {str(e)}")
                return func.HttpResponse(
                    json.dumps(
                        {
                            "error": "Missing required packages",
                            "details": str(e),
                            "suggestion": "Ensure azure-ai-projects is installed",
                        }
                    ),
                    status_code=500,
                    headers=headers,
                )

            except Exception as e:
                logging.error(f"Azure AI error: {str(e)}")
                logging.error(f"Error type: {type(e).__name__}")

                # Análisis específico del error
                error_message = str(e)

                if "Resource not found" in error_message:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Resource not found",
                                "details": error_message,
                                "suggestion": "Verify that the agent ID exists and the endpoint is correct",
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )
                elif (
                    "missing" in error_message.lower()
                    and "arguments" in error_message.lower()
                ):
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Configuration error",
                                "details": error_message,
                                "suggestion": "The SDK may require additional configuration. Try using DefaultAzureCredential instead.",
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )
                else:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Azure AI processing failed",
                                "details": error_message,
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )

        except ValueError as e:
            logging.error(f"JSON parsing error: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                headers=headers,
            )
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": "Request processing failed", "details": str(e)}),
                status_code=500,
                headers=headers,
            )

    return func.HttpResponse(
        json.dumps({"error": f"Method {req.method} not supported"}),
        status_code=405,
        headers=headers,
    )
