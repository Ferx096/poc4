import json
import logging
import os
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import (
    DefaultAzureCredential,
    AzureCliCredential,
    ManagedIdentityCredential,
)
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
                agent_id = agent_id.strip('"')

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
                # De: https://ia-analytics.services.ai.azure.com/api/projects/PoC
                # Extraer: resource_group y project_name

                # Parsear el endpoint para obtener el project_name
                project_name = (
                    endpoint.split("/projects/")[-1]
                    if "/projects/" in endpoint
                    else "PoC"
                )

                # El resource group lo necesitamos de alguna forma
                # Podríamos extraerlo del AZURE_EXISTING_AIPROJECT_RESOURCE_ID si está disponible
                resource_id = os.environ.get("AZURE_EXISTING_AIPROJECT_RESOURCE_ID", "")
                resource_group = "IA-Analytics"  # Default basado en tu configuración

                if resource_id:
                    # Extraer resource group del resource ID
                    # /subscriptions/.../resourceGroups/IA-Analytics/...
                    parts = resource_id.split("/")
                    if "resourceGroups" in parts:
                        rg_index = parts.index("resourceGroups")
                        if rg_index + 1 < len(parts):
                            resource_group = parts[rg_index + 1]

                logging.info(f"Using project_name: {project_name}")
                logging.info(f"Using resource_group: {resource_group}")
                logging.info(f"Using subscription_id: {subscription_id}")

                # Intentar diferentes métodos de autenticación
                project_client = None

                # Método 1: Intentar con API Key si está disponible
                if api_key:
                    try:
                        logging.info("Attempting authentication with API Key")
                        credential = AzureKeyCredential(api_key)
                        project_client = AIProjectClient(
                            credential=credential,
                            endpoint=endpoint,
                            # Los siguientes parámetros podrían no ser necesarios con AzureKeyCredential
                            # pero los incluimos por si acaso
                            subscription_id=subscription_id,
                            resource_group_name=resource_group,
                            project_name=project_name,
                        )
                        logging.info("Successfully authenticated with API Key")
                    except TypeError as te:
                        # Si falla con TypeError, intentar sin los parámetros extra
                        logging.warning(f"Failed with extra params: {te}")
                        try:
                            project_client = AIProjectClient(
                                credential=credential, endpoint=endpoint
                            )
                            logging.info(
                                "Successfully authenticated with API Key (minimal params)"
                            )
                        except Exception as e2:
                            logging.error(f"API Key authentication failed: {e2}")
                            project_client = None

                # Método 2: Si API Key falla, intentar con DefaultAzureCredential
                if not project_client and subscription_id:
                    try:
                        logging.info(
                            "Attempting authentication with DefaultAzureCredential"
                        )
                        # Usar ManagedIdentityCredential en Azure Functions
                        credential = ManagedIdentityCredential()

                        project_client = AIProjectClient(
                            credential=credential,
                            endpoint=endpoint,
                            subscription_id=subscription_id,
                            resource_group_name=resource_group,
                            project_name=project_name,
                        )
                        logging.info("Successfully authenticated with Managed Identity")
                    except Exception as e:
                        logging.error(f"Managed Identity authentication failed: {e}")
                        # Intentar con DefaultAzureCredential como último recurso
                        try:
                            credential = DefaultAzureCredential()
                            project_client = AIProjectClient(
                                credential=credential,
                                endpoint=endpoint,
                                subscription_id=subscription_id,
                                resource_group_name=resource_group,
                                project_name=project_name,
                            )
                            logging.info(
                                "Successfully authenticated with DefaultAzureCredential"
                            )
                        except Exception as e2:
                            logging.error(f"DefaultAzureCredential failed: {e2}")
                            project_client = None

                if not project_client:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Failed to initialize AI Project Client",
                                "details": "Could not authenticate with any available method",
                                "suggestion": "Check your API key and endpoint configuration",
                            }
                        ),
                        status_code=500,
                        headers=headers,
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
                run = project_client.agents.runs.create_and_process(
                    thread_id=thread.id,
                    assistant_id=agent_id,  # Usar assistant_id, no agent_id
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
                    if msg.role == "assistant":
                        # Intentar diferentes formas de obtener el contenido
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
                        elif hasattr(msg, "text_messages") and msg.text_messages:
                            if len(msg.text_messages) > 0:
                                assistant_response = msg.text_messages[-1].text.value
                                break

                if not assistant_response:
                    assistant_response = "Lo siento, no pude generar una respuesta. Por favor, intenta de nuevo."

                logging.info(f"Assistant response: {assistant_response[:100]}...")

                return func.HttpResponse(
                    json.dumps({"response": assistant_response}),
                    status_code=200,
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
