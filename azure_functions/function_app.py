import azure.functions as func
import json
import logging
import os
from datetime import datetime
from azure.ai.projects import AIProjectClient
from azure.identity import ManagedIdentityCredential
from azure.ai.agents.models import ListSortOrder

# Configurar logging
logging.basicConfig(level=logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Constantes - Puedes obtener estas de variables de entorno si prefieres
AGENT_ID = os.environ.get("AZURE_EXISTING_AGENT_ID", "asst_XizkjMGP4EQaFZYnygjH8BET")
PROJECT_ENDPOINT = "https://ia-analytics.services.ai.azure.com/"
PROJECT_NAME = "PoC"

# Variables globales
project = None
initialization_error = None


def initialize_client():
    """Inicializa el cliente usando Managed Identity"""
    global project, initialization_error

    try:
        logging.info("=== INICIANDO CLIENTE CON MANAGED IDENTITY ===")

        # Verificar que Managed Identity esté disponible
        msi_endpoint = os.environ.get("MSI_ENDPOINT")
        identity_endpoint = os.environ.get("IDENTITY_ENDPOINT")

        if not (msi_endpoint or identity_endpoint):
            raise Exception("Managed Identity no está habilitada en esta Function App")

        logging.info(f"✅ Managed Identity disponible")
        logging.info(f"   MSI_ENDPOINT: {msi_endpoint}")
        logging.info(f"   IDENTITY_ENDPOINT: {identity_endpoint}")

        # Crear credencial con Managed Identity
        credential = ManagedIdentityCredential()

        # Crear cliente de AI Projects
        project = AIProjectClient(
            credential=credential, endpoint=PROJECT_ENDPOINT, project_name=PROJECT_NAME
        )

        # Verificar que podemos acceder al agente
        logging.info(f"Verificando acceso al agente {AGENT_ID}...")
        agent = project.agents.get_agent(AGENT_ID)
        logging.info(f"✅ Cliente inicializado exitosamente")
        logging.info(f"   Agente: {agent.id}")
        logging.info(f"   Nombre: {agent.name if hasattr(agent, 'name') else 'N/A'}")

        return True

    except Exception as e:
        initialization_error = str(e)
        logging.error(f"❌ Error inicializando cliente: {initialization_error}")

        # Dar información específica sobre el error
        if "401" in str(e) or "403" in str(e) or "Unauthorized" in str(e):
            logging.error(
                "⚠️ Error de permisos. Asegúrate de que la Managed Identity tiene el rol 'Cognitive Services User' en el recurso IA-Analytics"
            )
        elif "404" in str(e):
            logging.error(
                "⚠️ Agente no encontrado. Verifica que el AGENT_ID sea correcto"
            )

        project = None
        return False


# Inicializar al arrancar
logging.info("=== INICIANDO AZURE FUNCTION APP ===")
initialize_client()


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    logging.info("Health check endpoint llamado")

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Reintentar si no está inicializado
    if not project:
        logging.info("Cliente no inicializado, reintentando...")
        initialize_client()

    health_status = {
        "status": "healthy" if project else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "AFP Prima Chat Agent",
        "authentication": {
            "method": "Managed Identity",
            "initialized": bool(project),
            "msi_available": bool(os.environ.get("MSI_ENDPOINT")),
            "identity_available": bool(os.environ.get("IDENTITY_ENDPOINT")),
        },
        "configuration": {
            "agent_id": AGENT_ID,
            "endpoint": PROJECT_ENDPOINT,
            "project": PROJECT_NAME,
        },
    }

    if not project:
        health_status["error"] = initialization_error
        health_status["troubleshooting"] = {
            "message": "El cliente no se pudo inicializar",
            "possible_causes": [
                "Managed Identity no tiene permisos en IA-Analytics",
                "El AGENT_ID es incorrecto",
                "El endpoint o proyecto son incorrectos",
            ],
            "solution": [
                "1. Verificar que Managed Identity está habilitada",
                "2. Asignar rol 'Cognitive Services User' a la Function App en IA-Analytics",
                "3. Verificar que el AGENT_ID existe en el proyecto",
            ],
        }

    status_code = 200 if project else 503

    return func.HttpResponse(
        json.dumps(health_status, indent=2), status_code=status_code, headers=headers
    )


@app.route(route="test", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Simple test endpoint"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    return func.HttpResponse(
        json.dumps(
            {
                "status": "running",
                "message": "Azure Function App está funcionando",
                "timestamp": datetime.utcnow().isoformat(),
                "ready": bool(project),
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
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }

    # Verificar que el cliente esté inicializado
    if not project:
        logging.warning("Cliente no inicializado, intentando reinicializar...")
        if not initialize_client():
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Servicio temporalmente no disponible",
                        "details": "No se puede conectar con el agente de AI",
                        "message": initialization_error,
                    }
                ),
                status_code=503,
                headers=headers,
            )

    try:
        # Parsear el request
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Solicitud inválida",
                        "details": "El campo 'message' es requerido",
                    }
                ),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        session_id = req_body.get("session_id", "default")

        logging.info(
            f"Mensaje recibido: '{user_message[:100]}...' (session: {session_id})"
        )

        # Obtener el agente
        agent = project.agents.get_agent(AGENT_ID)

        # Crear un nuevo thread para la conversación
        thread = project.agents.threads.create()
        logging.info(f"Thread creado: {thread.id}")

        # Agregar el mensaje del usuario
        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )
        logging.info(f"Mensaje agregado al thread")

        # Ejecutar el agente
        logging.info("Ejecutando el agente...")
        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )

        logging.info(f"Run completado con estado: {run.status}")

        # Verificar si el run fue exitoso
        if run.status == "failed":
            error_details = (
                str(run.last_error) if run.last_error else "Error desconocido"
            )
            logging.error(f"El agente falló: {error_details}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "El agente no pudo procesar tu consulta",
                        "details": error_details,
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Obtener los mensajes del thread
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        # Extraer la respuesta del bot
        bot_response = None
        for msg in messages:
            if msg.role == "assistant" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value

        if not bot_response:
            bot_response = (
                "Lo siento, no pude generar una respuesta. Por favor, intenta de nuevo."
            )

        logging.info(f"Respuesta generada exitosamente")

        # Retornar la respuesta
        return func.HttpResponse(
            json.dumps(
                {
                    "response": bot_response,
                    "thread_id": thread.id,
                    "session_id": session_id,
                    "status": "success",
                }
            ),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Error en chat endpoint: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Error interno del servidor",
                    "details": str(e),
                    "type": type(e).__name__,
                }
            ),
            status_code=500,
            headers=headers,
        )


@app.route(route="chat", methods=["OPTIONS"])
def chat_options(req: func.HttpRequest) -> func.HttpResponse:
    """Handle CORS preflight requests"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "3600",
    }
    return func.HttpResponse("", status_code=204, headers=headers)


@app.route(route="debug", methods=["GET"])
def debug_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Debug endpoint para diagnóstico"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Información de debug
    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": {
            "client_initialized": bool(project),
            "last_error": initialization_error,
        },
        "managed_identity": {
            "msi_endpoint": os.environ.get("MSI_ENDPOINT", "Not found"),
            "identity_endpoint": os.environ.get("IDENTITY_ENDPOINT", "Not found"),
            "identity_header": os.environ.get("IDENTITY_HEADER", "Not found"),
            "available": bool(
                os.environ.get("MSI_ENDPOINT") or os.environ.get("IDENTITY_ENDPOINT")
            ),
        },
        "configuration": {
            "agent_id": AGENT_ID,
            "project_endpoint": PROJECT_ENDPOINT,
            "project_name": PROJECT_NAME,
        },
        "runtime": {
            "python_version": os.sys.version,
            "functions_version": os.environ.get(
                "FUNCTIONS_EXTENSION_VERSION", "Unknown"
            ),
        },
    }

    # Si hay error, agregar información de troubleshooting
    if not project and initialization_error:
        if "401" in str(initialization_error) or "403" in str(initialization_error):
            debug_info["troubleshooting"] = {
                "error_type": "Authorization Error",
                "message": "La Managed Identity no tiene permisos en el recurso",
                "solution": "Asignar el rol 'Cognitive Services User' a la Function App en IA-Analytics",
            }
        elif "404" in str(initialization_error):
            debug_info["troubleshooting"] = {
                "error_type": "Not Found Error",
                "message": "El agente o recurso no se encontró",
                "solution": "Verificar que el AGENT_ID y PROJECT_NAME sean correctos",
            }

    return func.HttpResponse(
        json.dumps(debug_info, indent=2), status_code=200, headers=headers
    )


# Log de inicio
logging.info("=== AZURE FUNCTION APP INICIADA ===")
logging.info(f"Agent ID: {AGENT_ID}")
logging.info(f"Endpoint: {PROJECT_ENDPOINT}")
logging.info(f"Project: {PROJECT_NAME}")
logging.info(f"MSI Disponible: {bool(os.environ.get('MSI_ENDPOINT'))}")
logging.info(f"Identity Disponible: {bool(os.environ.get('IDENTITY_ENDPOINT'))}")
