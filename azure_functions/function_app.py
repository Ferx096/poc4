import azure.functions as func
import json
import logging
import os
from datetime import datetime
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, AzureKeyCredential
from azure.ai.agents.models import ListSortOrder

# Configurar logging
logging.basicConfig(level=logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Constantes
AGENT_ID = "asst_XizkjMGP4EQaFZYnygjH8BET"
PROJECT_ENDPOINT = "https://ia-analytics.services.ai.azure.com/"
PROJECT_NAME = "PoC"

# Variables globales para el cliente
project = None
initialization_error = None
api_key_status = "checking"


def initialize_client():
    """Inicializa el cliente de AI con reintentos y mejor manejo de errores"""
    global project, initialization_error, api_key_status

    try:
        # Opción 1: Intentar con API Key primero
        api_key = os.environ.get("AZURE_AI_API_KEY")

        if api_key:
            logging.info(f"✅ API Key encontrada (longitud: {len(api_key)})")
            api_key_status = "found"

            # Usar AzureKeyCredential para autenticación con API Key
            project = AIProjectClient(
                credential=AzureKeyCredential(api_key),
                endpoint=PROJECT_ENDPOINT,
                project_name=PROJECT_NAME,
            )

            # Verificar que el cliente funciona
            try:
                agent = project.agents.get_agent(AGENT_ID)
                logging.info(f"✅ Cliente inicializado y agente verificado: {agent.id}")
                return True
            except Exception as e:
                logging.error(f"❌ Error verificando agente: {str(e)}")
                initialization_error = (
                    f"Cliente creado pero no puede acceder al agente: {str(e)}"
                )
                project = None
                return False

        else:
            # Opción 2: Intentar con Managed Identity si no hay API Key
            logging.warning(
                "⚠️ API Key no encontrada, intentando con Managed Identity..."
            )
            api_key_status = "not_found"

            # Verificar si Managed Identity está habilitada
            if os.environ.get("MSI_ENDPOINT"):
                logging.info(
                    "MSI_ENDPOINT encontrado, intentando con DefaultAzureCredential..."
                )
                project = AIProjectClient(
                    credential=DefaultAzureCredential(),
                    endpoint=PROJECT_ENDPOINT,
                    project_name=PROJECT_NAME,
                )

                # Verificar conexión
                agent = project.agents.get_agent(AGENT_ID)
                logging.info(f"✅ Conectado con Managed Identity: {agent.id}")
                api_key_status = "managed_identity"
                return True
            else:
                logging.error("❌ Managed Identity no está habilitada")
                initialization_error = "Ni API Key ni Managed Identity disponibles"
                return False

    except Exception as e:
        initialization_error = str(e)
        logging.error(f"❌ Error crítico inicializando cliente: {initialization_error}")
        project = None
        return False


# Intentar inicializar al arrancar
initialize_client()


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint mejorado"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Reintentar inicialización si falló
    if not project:
        initialize_client()

    # Debug detallado del entorno
    env_debug = {
        "total_vars": len(os.environ),
        "azure_vars": [k for k in os.environ.keys() if "AZURE" in k.upper()][:10],
        "msi_endpoint": bool(os.environ.get("MSI_ENDPOINT")),
        "identity_endpoint": bool(os.environ.get("IDENTITY_ENDPOINT")),
        "functions_extension": os.environ.get(
            "FUNCTIONS_EXTENSION_VERSION", "not_found"
        ),
        "website_instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "not_found")[:10]
        + "...",
    }

    health_status = {
        "status": "checking",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_status": api_key_status,
        "api_key_configured": bool(os.environ.get("AZURE_AI_API_KEY")),
        "api_key_length": len(os.environ.get("AZURE_AI_API_KEY", "")),
        "client_initialized": bool(project),
        "initialization_error": initialization_error,
        "agent_id": AGENT_ID,
        "endpoint": PROJECT_ENDPOINT,
        "project_name": PROJECT_NAME,
        "environment": env_debug,
        "python_version": os.sys.version,
    }

    # Determinar estado de salud
    if project:
        try:
            # Verificar conexión real
            agent = project.agents.get_agent(AGENT_ID)
            health_status["status"] = "healthy"
            health_status["agent_verified"] = True
            status_code = 200
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = f"No se puede conectar al agente: {str(e)}"
            status_code = 503
    else:
        health_status["status"] = "unhealthy"
        health_status["error"] = "Cliente no inicializado"

        # Sugerencias específicas
        if not os.environ.get("AZURE_AI_API_KEY"):
            health_status["solution"] = (
                "Agregar AZURE_AI_API_KEY en Configuración > Configuración de la aplicación (NO en Variables de entorno)"
            )
            health_status["steps"] = [
                "1. Ir a Configuración > Configuración de la aplicación",
                "2. Click en '+ Nueva configuración de aplicación'",
                "3. Nombre: AZURE_AI_API_KEY",
                "4. Valor: [tu API key]",
                "5. Click en Guardar",
                "6. Click en el botón de refrescar arriba para aplicar cambios",
            ]
        else:
            health_status["solution"] = (
                "API Key presente pero no válida o permisos insuficientes"
            )

        status_code = 503

    return func.HttpResponse(
        json.dumps(health_status, indent=2), status_code=status_code, headers=headers
    )


@app.route(route="test", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Test endpoint simplificado"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Información básica del entorno
    test_data = {
        "message": "Function App is running",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_present": bool(os.environ.get("AZURE_AI_API_KEY")),
        "api_key_length": len(os.environ.get("AZURE_AI_API_KEY", "")),
        "client_ready": bool(project),
        "azure_vars_count": len([k for k in os.environ.keys() if "AZURE" in k.upper()]),
        "config_source": (
            "Configuración de la aplicación"
            if os.environ.get("AZURE_AI_API_KEY")
            else "No configurado"
        ),
    }

    return func.HttpResponse(
        json.dumps(test_data, indent=2), status_code=200, headers=headers
    )


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint principal del chat"""
    logging.info("=== CHAT ENDPOINT CALLED ===")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    # Reintentar inicialización si es necesario
    if not project:
        logging.info("Cliente no inicializado, reintentando...")
        if not initialize_client():
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Servicio no disponible",
                        "details": "No se puede conectar con Azure AI",
                        "initialization_error": initialization_error,
                        "suggestion": "Verifica la configuración de AZURE_AI_API_KEY",
                    }
                ),
                status_code=503,
                headers=headers,
            )

    try:
        # Obtener mensaje del request
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "El mensaje es requerido"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        session_id = req_body.get("session_id", "default")

        logging.info(
            f"Procesando mensaje: '{user_message[:50]}...' (session: {session_id})"
        )

        # Obtener el agente
        agent = project.agents.get_agent(AGENT_ID)
        logging.info(f"✅ Agente obtenido: {agent.id}")

        # Crear thread
        thread = project.agents.threads.create()
        logging.info(f"✅ Thread creado: {thread.id}")

        # Crear mensaje
        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )
        logging.info("✅ Mensaje creado")

        # Ejecutar el agente con timeout
        logging.info("Ejecutando agente...")
        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )

        logging.info(f"✅ Run completado con estado: {run.status}")

        if run.status == "failed":
            error_details = (
                str(run.last_error) if run.last_error else "Error desconocido"
            )
            logging.error(f"Run falló: {error_details}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "El agente no pudo procesar la consulta",
                        "details": error_details,
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Obtener respuesta
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        # Extraer última respuesta del bot
        bot_response = "Lo siento, no pude generar una respuesta."
        for msg in reversed(list(messages)):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        logging.info("✅ Respuesta generada exitosamente")

        return func.HttpResponse(
            json.dumps(
                {
                    "response": bot_response,
                    "thread_id": thread.id,
                    "status": "success",
                    "session_id": session_id,
                }
            ),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"❌ Error inesperado: {str(e)}", exc_info=True)
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
    """Manejo de CORS preflight"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return func.HttpResponse("", status_code=204, headers=headers)


@app.route(route="debug", methods=["GET"])
def debug_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint de debug para verificar configuración"""
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Obtener todas las variables que contienen "AZURE" o "AI"
    relevant_vars = {}
    for key in os.environ:
        if "AZURE" in key.upper() or "AI" in key.upper() or "API" in key.upper():
            value = os.environ[key]
            # Ocultar parcialmente valores sensibles
            if len(value) > 10:
                masked_value = f"{value[:5]}...{value[-5:]}"
            else:
                masked_value = "***"
            relevant_vars[key] = masked_value

    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "relevant_variables": relevant_vars,
        "total_env_vars": len(os.environ),
        "client_initialized": bool(project),
        "initialization_error": initialization_error,
        "runtime": {
            "python_version": os.sys.version,
            "functions_version": os.environ.get(
                "FUNCTIONS_EXTENSION_VERSION", "unknown"
            ),
            "platform": os.environ.get("WEBSITE_PLATFORM_VERSION", "unknown"),
        },
    }

    return func.HttpResponse(
        json.dumps(debug_info, indent=2), status_code=200, headers=headers
    )
