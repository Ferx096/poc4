import azure.functions as func
import json
import logging
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import ListSortOrder
import os
from datetime import datetime

# Configurar logging level
logging.basicConfig(level=logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Debug: Imprimir todas las variables de entorno (solo para debugging)
logging.info("=== ENVIRONMENT VARIABLES CHECK ===")
env_vars = os.environ.keys()
logging.info(f"Total environment variables: {len(env_vars)}")
for var in env_vars:
    if "AZURE" in var or "API" in var:
        # Solo mostrar primeros 10 caracteres por seguridad
        value = os.environ.get(var, "")
        masked_value = f"{value[:10]}..." if len(value) > 10 else value
        logging.info(f"{var}: {masked_value}")

# Obtener la API key de las variables de entorno
API_KEY = os.getenv("AZURE_AI_API_KEY")

# Debug mejorado
if not API_KEY:
    logging.error("❌ AZURE_AI_API_KEY NOT FOUND in environment variables")
    logging.error(
        "Available env vars with 'AZURE': "
        + str([k for k in os.environ.keys() if "AZURE" in k])
    )
else:
    logging.info(f"✅ API Key loaded successfully (length: {len(API_KEY)})")
    logging.info(f"API Key starts with: {API_KEY[:10]}...")

# Inicialización del cliente
project = None
initialization_error = None

if API_KEY:
    try:
        logging.info("Initializing AIProjectClient...")
        project = AIProjectClient(
            credential=AzureKeyCredential(API_KEY),
            endpoint="https://ia-analytics.services.ai.azure.com/",
            project_name="PoC",
        )
        logging.info("✅ AIProjectClient initialized successfully")
    except Exception as e:
        initialization_error = str(e)
        logging.error(f"❌ Error initializing AIProjectClient: {initialization_error}")
        project = None
else:
    initialization_error = "API Key not found in environment"

AGENT_ID = "asst_XizkjMGP4EQaFZYnygjH8BET"


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("=== CHAT ENDPOINT CALLED ===")

    # Headers CORS
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    # Debug info
    logging.info(f"API Key configured: {bool(API_KEY)}")
    logging.info(f"Project client initialized: {bool(project)}")

    # Verificar configuración
    if not API_KEY:
        error_msg = {
            "error": "Configuración incompleta",
            "details": "API Key no está configurada en las variables de entorno",
            "debug": {
                "api_key_present": False,
                "env_vars_with_azure": [k for k in os.environ.keys() if "AZURE" in k][
                    :5
                ],  # Solo mostrar 5
            },
        }
        logging.error(f"Error response: {error_msg}")
        return func.HttpResponse(
            json.dumps(error_msg),
            status_code=500,
            headers=headers,
        )

    if not project:
        error_msg = {
            "error": "Servicio no disponible",
            "details": "El cliente de AI no está inicializado",
            "initialization_error": initialization_error,
        }
        logging.error(f"Error response: {error_msg}")
        return func.HttpResponse(
            json.dumps(error_msg),
            status_code=503,
            headers=headers,
        )

    try:
        # Obtener el body del request
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "El mensaje es requerido"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Processing message: '{user_message[:50]}...'")

        # Obtener el agente
        logging.info(f"Getting agent with ID: {AGENT_ID}")
        agent = project.agents.get_agent(AGENT_ID)
        logging.info(f"✅ Agent retrieved: {agent.id}")

        # Crear thread
        thread = project.agents.threads.create()
        logging.info(f"✅ Thread created: {thread.id}")

        # Crear mensaje
        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )
        logging.info("✅ Message created")

        # Ejecutar el agente
        logging.info("Starting agent run...")
        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )
        logging.info(f"✅ Run completed with status: {run.status}")

        if run.status == "failed":
            error_details = str(run.last_error) if run.last_error else "Unknown error"
            logging.error(f"Run failed: {error_details}")
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

        # Obtener mensajes
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        # Extraer respuesta
        bot_response = "Lo siento, no pude generar una respuesta."
        for msg in reversed(list(messages)):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        logging.info("✅ Response generated successfully")

        return func.HttpResponse(
            json.dumps(
                {"response": bot_response, "thread_id": thread.id, "status": "success"}
            ),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"❌ Unexpected error: {str(e)}", exc_info=True)
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
    logging.info("OPTIONS request received")
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return func.HttpResponse("", status_code=204, headers=headers)


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint con información detallada"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    # Información detallada para debugging
    health_status = {
        "status": "checking",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_configured": bool(API_KEY),
        "api_key_length": len(API_KEY) if API_KEY else 0,
        "client_initialized": bool(project),
        "initialization_error": initialization_error,
        "agent_id": AGENT_ID,
        "environment": {
            "total_vars": len(os.environ),
            "azure_vars": [k for k in os.environ.keys() if "AZURE" in k][
                :10
            ],  # Primeras 10
            "python_version": os.sys.version,
        },
    }

    if not API_KEY:
        health_status["status"] = "unhealthy"
        health_status["error"] = "API Key not configured"
        health_status["solution"] = "Add AZURE_AI_API_KEY to Function App Configuration"
    elif not project:
        health_status["status"] = "unhealthy"
        health_status["error"] = "AI Client not initialized"
        health_status["solution"] = "Check API Key format and endpoint configuration"
    else:
        try:
            # Intentar obtener el agente
            agent = project.agents.get_agent(AGENT_ID)
            health_status["status"] = "healthy"
            health_status["agent_connected"] = True
            status_code = 200
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = f"Cannot connect to agent: {str(e)}"
            health_status["solution"] = "Verify API Key permissions and agent ID"
            status_code = 503

    if health_status["status"] == "unhealthy":
        status_code = 503

    return func.HttpResponse(
        json.dumps(health_status, indent=2), status_code=status_code, headers=headers
    )


@app.route(route="test", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint de prueba simple"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    return func.HttpResponse(
        json.dumps(
            {
                "message": "Function App is running",
                "timestamp": datetime.utcnow().isoformat(),
                "api_key_present": bool(os.getenv("AZURE_AI_API_KEY")),
            }
        ),
        status_code=200,
        headers=headers,
    )
