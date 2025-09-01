import azure.functions as func
import json
import logging
import os
from datetime import datetime
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import ListSortOrder

# Configurar logging
logging.basicConfig(level=logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Constantes
AGENT_ID = "asst_XizkjMGP4EQaFZYnygjH8BET"
PROJECT_ENDPOINT = "https://ia-analytics.services.ai.azure.com/"
PROJECT_NAME = "PoC"

# Variables globales
project = None
initialization_error = None
auth_method = "checking"


def initialize_client():
    """Inicializa el cliente con Managed Identity o API Key"""
    global project, initialization_error, auth_method

    try:
        logging.info("=== INICIANDO CLIENTE DE AI ===")

        # Opción 1: Intentar con API Key primero (por si acaso funciona)
        api_key = os.environ.get("AZURE_AI_API_KEY")

        if api_key:
            logging.info(f"✅ API Key encontrada, intentando autenticación con Key...")
            try:
                project = AIProjectClient(
                    credential=AzureKeyCredential(api_key.strip()),
                    endpoint=PROJECT_ENDPOINT,
                    project_name=PROJECT_NAME,
                )
                # Verificar conexión
                agent = project.agents.get_agent(AGENT_ID)
                logging.info(f"✅ Conectado con API Key. Agente: {agent.id}")
                auth_method = "api_key"
                return True
            except Exception as e:
                logging.warning(f"⚠️ API Key no funcionó: {str(e)}")

        # Opción 2: Usar Managed Identity
        logging.info("🔐 Intentando con Managed Identity...")

        # Verificar si estamos en Azure con MSI habilitado
        if os.environ.get("MSI_ENDPOINT") or os.environ.get("IDENTITY_ENDPOINT"):
            try:
                # Usar ManagedIdentityCredential específicamente
                credential = ManagedIdentityCredential()

                project = AIProjectClient(
                    credential=credential,
                    endpoint=PROJECT_ENDPOINT,
                    project_name=PROJECT_NAME,
                )

                # Verificar conexión
                agent = project.agents.get_agent(AGENT_ID)
                logging.info(f"✅ Conectado con Managed Identity. Agente: {agent.id}")
                auth_method = "managed_identity"
                return True

            except Exception as e:
                logging.error(f"❌ Error con Managed Identity: {str(e)}")
                initialization_error = f"Managed Identity falló: {str(e)}"
        else:
            logging.error(
                "❌ MSI_ENDPOINT no encontrado. Managed Identity no está habilitada."
            )
            initialization_error = (
                "Managed Identity no está habilitada en esta Function App"
            )

        # Opción 3: Intentar con DefaultAzureCredential como último recurso
        try:
            logging.info("🔑 Último intento con DefaultAzureCredential...")
            credential = DefaultAzureCredential()

            project = AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT,
                project_name=PROJECT_NAME,
            )

            agent = project.agents.get_agent(AGENT_ID)
            logging.info(f"✅ Conectado con DefaultAzureCredential. Agente: {agent.id}")
            auth_method = "default_credential"
            return True

        except Exception as e:
            logging.error(f"❌ DefaultAzureCredential también falló: {str(e)}")
            initialization_error = (
                f"Ningún método de autenticación funcionó. Último error: {str(e)}"
            )
            return False

    except Exception as e:
        initialization_error = f"Error crítico: {str(e)}"
        logging.error(f"❌ {initialization_error}")
        project = None
        return False


# Inicializar al arrancar
logging.info("=== INICIANDO FUNCTION APP ===")
initialize_client()


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check con información detallada"""
    logging.info("Health check llamado")

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Reintentar si falló
    if not project:
        logging.info("Reintentando inicialización...")
        initialize_client()

    health_status = {
        "status": "healthy" if project else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "authentication": {
            "method_used": auth_method,
            "client_initialized": bool(project),
            "api_key_present": bool(os.environ.get("AZURE_AI_API_KEY")),
            "msi_endpoint": bool(os.environ.get("MSI_ENDPOINT")),
            "identity_endpoint": bool(os.environ.get("IDENTITY_ENDPOINT")),
            "managed_identity_available": bool(
                os.environ.get("MSI_ENDPOINT") or os.environ.get("IDENTITY_ENDPOINT")
            ),
        },
        "configuration": {
            "agent_id": AGENT_ID,
            "endpoint": PROJECT_ENDPOINT,
            "project_name": PROJECT_NAME,
        },
        "error": initialization_error if not project else None,
    }

    # Agregar sugerencias si hay problemas
    if not project:
        if not os.environ.get("MSI_ENDPOINT") and not os.environ.get(
            "IDENTITY_ENDPOINT"
        ):
            health_status["solution"] = {
                "message": "Managed Identity no está habilitada",
                "steps": [
                    "1. Ve a tu Function App en Azure Portal",
                    "2. Identidad → Asignado por el sistema",
                    "3. Cambia Estado a 'Activado'",
                    "4. Guardar",
                    "5. Ve a tu recurso IA-Analytics",
                    "6. Control de acceso (IAM)",
                    "7. Agregar asignación de rol",
                    "8. Selecciona 'Cognitive Services User'",
                    "9. Asigna a la identidad de tu Function App",
                ],
            }

    status_code = 200 if project else 503

    return func.HttpResponse(
        json.dumps(health_status, indent=2), status_code=status_code, headers=headers
    )


@app.route(route="test", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Test endpoint"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    return func.HttpResponse(
        json.dumps(
            {
                "message": "Function App is running",
                "timestamp": datetime.utcnow().isoformat(),
                "auth_method": auth_method,
                "client_ready": bool(project),
            },
            indent=2,
        ),
        status_code=200,
        headers=headers,
    )


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Chat endpoint principal"""
    logging.info("Chat endpoint llamado")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }

    if not project:
        if not initialize_client():
            return func.HttpResponse(
                json.dumps(
                    {"error": "Servicio no disponible", "details": initialization_error}
                ),
                status_code=503,
                headers=headers,
            )

    try:
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "Mensaje requerido"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Procesando: {user_message[:50]}...")

        # Interactuar con el agente
        agent = project.agents.get_agent(AGENT_ID)
        thread = project.agents.threads.create()

        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )

        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )

        if run.status == "failed":
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Error procesando mensaje",
                        "details": str(run.last_error) if run.last_error else "Unknown",
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Obtener respuesta
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        bot_response = "No se pudo generar respuesta"
        for msg in reversed(list(messages)):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        return func.HttpResponse(
            json.dumps({"response": bot_response, "status": "success"}),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}), status_code=500, headers=headers
        )


@app.route(route="chat", methods=["OPTIONS"])
def chat_options(req: func.HttpRequest) -> func.HttpResponse:
    """CORS preflight"""
    return func.HttpResponse(
        "",
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


@app.route(route="debug", methods=["GET"])
def debug_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Debug endpoint mejorado"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "authentication_status": {
            "method_attempted": auth_method,
            "client_initialized": bool(project),
            "error": initialization_error,
        },
        "environment_checks": {
            "api_key_configured": bool(os.environ.get("AZURE_AI_API_KEY")),
            "msi_endpoint": os.environ.get("MSI_ENDPOINT", "Not found"),
            "identity_endpoint": os.environ.get("IDENTITY_ENDPOINT", "Not found"),
            "identity_header": os.environ.get("IDENTITY_HEADER", "Not found"),
            "managed_identity_ready": bool(
                os.environ.get("MSI_ENDPOINT") or os.environ.get("IDENTITY_ENDPOINT")
            ),
        },
        "azure_variables": {},
    }

    # Listar variables Azure
    for key in sorted(os.environ.keys()):
        if any(term in key.upper() for term in ["AZURE", "MSI", "IDENTITY", "API"]):
            value = os.environ[key]
            if len(value) > 30:
                masked = f"{value[:10]}...{value[-10:]}"
            else:
                masked = "***"
            debug_info["azure_variables"][key] = masked

    return func.HttpResponse(
        json.dumps(debug_info, indent=2), status_code=200, headers=headers
    )
