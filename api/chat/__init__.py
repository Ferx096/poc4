import json
import logging
import os
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
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
            subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")

            # Limpiar el agent_id si tiene comillas extras
            if agent_id:
                agent_id = agent_id.strip('"').strip()

            # Validar variables requeridas
            if not all([endpoint, agent_id]):
                missing = []
                if not endpoint:
                    missing.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                if not agent_id:
                    missing.append("AZURE_EXISTING_AGENT_ID")

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

                # Extraer información del endpoint
                project_name = (
                    endpoint.split("/projects/")[-1]
                    if "/projects/" in endpoint
                    else "PoC"
                )

                # Extraer resource group del resource ID si está disponible
                resource_id = os.environ.get("AZURE_EXISTING_AIPROJECT_RESOURCE_ID", "")
                resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "IA-Analytics")

                if resource_id and not os.environ.get("AZURE_RESOURCE_GROUP"):
                    parts = resource_id.split("/")
                    if "resourceGroups" in parts:
                        rg_index = parts.index("resourceGroups")
                        if rg_index + 1 < len(parts):
                            resource_group = parts[rg_index + 1]

                logging.info(f"Using project_name: {project_name}")
                logging.info(f"Using resource_group: {resource_group}")
                logging.info(f"Using subscription_id: {subscription_id}")

                # Crear el cliente
                project_client = None

                # Intentar con API Key primero
                if api_key:
                    try:
                        logging.info("Attempting authentication with API Key")
                        credential = AzureKeyCredential(api_key)

                        # Primero intentar solo con credential y endpoint
                        try:
                            project_client = AIProjectClient(
                                credential=credential, endpoint=endpoint
                            )
                            logging.info(
                                "Successfully created client with API Key (minimal params)"
                            )
                        except Exception as e1:
                            logging.warning(f"Minimal params failed: {e1}")
                            # Si falla, intentar con todos los parámetros
                            project_client = AIProjectClient(
                                credential=credential,
                                endpoint=endpoint,
                                subscription_id=subscription_id,
                                resource_group_name=resource_group,
                                project_name=project_name,
                            )
                            logging.info(
                                "Successfully created client with API Key (full params)"
                            )
                    except Exception as e:
                        logging.error(f"API Key authentication failed: {e}")
                        project_client = None

                # Si API Key falla, intentar con DefaultAzureCredential
                if not project_client:
                    try:
                        logging.info(
                            "Attempting authentication with DefaultAzureCredential"
                        )

                        # En Azure Functions, usar ManagedIdentityCredential
                        try:
                            credential = ManagedIdentityCredential()
                            logging.info("Using ManagedIdentityCredential")
                        except:
                            credential = DefaultAzureCredential()
                            logging.info("Using DefaultAzureCredential")

                        project_client = AIProjectClient(
                            credential=credential,
                            endpoint=endpoint,
                            subscription_id=subscription_id,
                            resource_group_name=resource_group,
                            project_name=project_name,
                        )
                        logging.info("Successfully authenticated with Azure Identity")
                    except Exception as e:
                        logging.error(f"Azure Identity authentication failed: {e}")
                        return func.HttpResponse(
                            json.dumps(
                                {"error": "Authentication failed", "details": str(e)}
                            ),
                            status_code=500,
                            headers=headers,
                        )

                logging.info("AIProjectClient created successfully")

                # IMPORTANTE: La estructura correcta del SDK es:
                # project_client.agents.create_thread() NO project_client.agents.threads.create()

                try:
                    # Opción 1: Usar el método correcto según la versión del SDK
                    if hasattr(project_client.agents, "create_thread"):
                        # Versión más nueva del SDK
                        thread = project_client.agents.create_thread()
                        logging.info(f"Created thread with create_thread: {thread.id}")
                    elif hasattr(project_client.agents, "threads"):
                        # Versión anterior del SDK
                        thread = project_client.agents.threads.create()
                        logging.info(f"Created thread with threads.create: {thread.id}")
                    else:
                        # Intentar acceso directo
                        # Algunos SDKs usan AgentsClient directamente
                        from azure.ai.projects.models import ThreadCreationOptions

                        thread = project_client.agents.create_thread(
                            ThreadCreationOptions()
                        )
                        logging.info(f"Created thread with direct method: {thread.id}")

                except AttributeError as ae:
                    logging.error(f"Thread creation failed with AttributeError: {ae}")
                    # Intentar método alternativo
                    try:
                        # Algunos SDKs requieren inicialización diferente
                        from azure.ai.projects.operations import AgentsOperations

                        agents_ops = project_client.agents

                        # Verificar qué métodos están disponibles
                        available_methods = dir(agents_ops)
                        logging.info(
                            f"Available methods in agents: {[m for m in available_methods if not m.startswith('_')]}"
                        )

                        # Intentar crear thread con el método disponible
                        if "create_thread" in available_methods:
                            thread = agents_ops.create_thread()
                        else:
                            raise Exception(
                                f"No thread creation method found. Available: {available_methods}"
                            )

                    except Exception as e2:
                        logging.error(f"Alternative thread creation failed: {e2}")
                        return func.HttpResponse(
                            json.dumps(
                                {
                                    "error": "SDK method error",
                                    "details": "Unable to create thread - SDK version incompatibility",
                                    "suggestion": "Check azure-ai-projects version in requirements.txt",
                                }
                            ),
                            status_code=500,
                            headers=headers,
                        )

                # Crear mensaje en el thread
                try:
                    if hasattr(project_client.agents, "create_message"):
                        message = project_client.agents.create_message(
                            thread_id=thread.id, role="user", content=user_message
                        )
                    elif hasattr(project_client.agents, "messages"):
                        message = project_client.agents.messages.create(
                            thread_id=thread.id, role="user", content=user_message
                        )
                    else:
                        # Método directo
                        from azure.ai.projects.models import MessageCreationOptions

                        message = project_client.agents.create_message(
                            thread_id=thread.id,
                            message=MessageCreationOptions(
                                role="user", content=user_message
                            ),
                        )

                    logging.info(f"Created message: {message.id}")

                except Exception as e:
                    logging.error(f"Message creation failed: {e}")
                    return func.HttpResponse(
                        json.dumps(
                            {"error": "Failed to create message", "details": str(e)}
                        ),
                        status_code=500,
                        headers=headers,
                    )

                # Ejecutar el agente
                try:
                    if hasattr(project_client.agents, "create_and_run"):
                        run = project_client.agents.create_and_run(
                            thread_id=thread.id, assistant_id=agent_id
                        )
                    elif hasattr(project_client.agents, "runs"):
                        run = project_client.agents.runs.create_and_process(
                            thread_id=thread.id, assistant_id=agent_id
                        )
                    else:
                        # Método directo
                        from azure.ai.projects.models import RunCreationOptions

                        run = project_client.agents.create_run(
                            thread_id=thread.id,
                            run=RunCreationOptions(assistant_id=agent_id),
                        )
                        # Esperar a que complete
                        import time

                        max_attempts = 30
                        for _ in range(max_attempts):
                            run = project_client.agents.get_run(
                                thread_id=thread.id, run_id=run.id
                            )
                            if run.status in ["completed", "failed", "cancelled"]:
                                break
                            time.sleep(1)

                    logging.info(f"Run status: {run.status}")

                except Exception as e:
                    logging.error(f"Run creation failed: {e}")
                    return func.HttpResponse(
                        json.dumps({"error": "Failed to run agent", "details": str(e)}),
                        status_code=500,
                        headers=headers,
                    )

                if run.status == "failed":
                    error_details = getattr(run, "last_error", None)
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

                # Obtener mensajes
                try:
                    if hasattr(project_client.agents, "list_messages"):
                        messages = project_client.agents.list_messages(
                            thread_id=thread.id
                        )
                    elif hasattr(project_client.agents, "messages"):
                        messages = project_client.agents.messages.list(
                            thread_id=thread.id
                        )
                    else:
                        messages = project_client.agents.get_messages(
                            thread_id=thread.id
                        )

                    assistant_response = ""
                    for msg in messages:
                        if msg.role == "assistant":
                            # Intentar diferentes formas de obtener el contenido
                            if hasattr(msg, "content"):
                                if (
                                    isinstance(msg.content, list)
                                    and len(msg.content) > 0
                                ):
                                    content_item = msg.content[0]
                                    if hasattr(content_item, "text"):
                                        if hasattr(content_item.text, "value"):
                                            assistant_response = content_item.text.value
                                        else:
                                            assistant_response = str(content_item.text)
                                    elif isinstance(content_item, str):
                                        assistant_response = content_item
                                elif isinstance(msg.content, str):
                                    assistant_response = msg.content
                            elif hasattr(msg, "text_messages") and msg.text_messages:
                                assistant_response = msg.text_messages[-1].text.value

                            if assistant_response:
                                break

                    if not assistant_response:
                        assistant_response = "Lo siento, no pude generar una respuesta. Por favor, intenta de nuevo."

                    logging.info(
                        f"Assistant response received: {len(assistant_response)} chars"
                    )

                    return func.HttpResponse(
                        json.dumps({"response": assistant_response}),
                        status_code=200,
                        headers=headers,
                    )

                except Exception as e:
                    logging.error(f"Failed to get messages: {e}")
                    return func.HttpResponse(
                        json.dumps(
                            {"error": "Failed to retrieve response", "details": str(e)}
                        ),
                        status_code=500,
                        headers=headers,
                    )

            except Exception as e:
                logging.error(f"Azure AI error: {str(e)}")
                logging.error(f"Error type: {type(e).__name__}")

                return func.HttpResponse(
                    json.dumps(
                        {
                            "error": "Azure AI processing failed",
                            "details": str(e),
                            "type": type(e).__name__,
                        }
                    ),
                    status_code=500,
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
