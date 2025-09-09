import azure.functions as func
import json
import logging
import os
from datetime import datetime
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
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
    """Inicializa el cliente de AI con mejor manejo de errores"""
    global project, initialization_error, api_key_status

    try:
        # Debug: Listar variables relevantes
        logging.info("=== VERIFICANDO VARIABLES DE ENTORNO ===")
        found_vars = []
        for key in sorted(os.environ.keys()):
            if "API" in key.upper() or "AZURE" in key.upper():
                value = os.environ.get(key, "")
                if value:
                    masked = (
                        f"{value[:10]}...{value[-10:]}"
                        if len(value) > 20
                        else "[corto]"
                    )
                    logging.info(f"  {key}: {masked} (len={len(value)})")
                    found_vars.append(key)

        logging.info(f"Variables encontradas: {len(found_vars)}")

        # Buscar API Key
        api_key = os.environ.get("AZURE_AI_API_KEY")

        if not api_key:
            # Intentar con variaciones del nombre
            alternatives = ["AZURE_AI_API_KEY", "AZURE-AI-API-KEY", "azure_ai_api_key"]
            for alt in alternatives:
                api_key = os.environ.get(alt)
                if api_key:
                    logging.info(f"✅ API Key encontrada con nombre alternativo: {alt}")
                    break

        if api_key:
            # Limpiar posibles espacios o saltos de línea
            api_key = api_key.strip()
            logging.info(f"✅ API Key encontrada y limpiada (longitud: {len(api_key)})")
            logging.info(f"   Inicio: {api_key[:20]}...")
            logging.info(f"   Final: ...{api_key[-20:]}")
            api_key_status = "found"

            # Crear cliente
            project = AIProjectClient(
                credential=AzureKeyCredential(api_key),
                endpoint=PROJECT_ENDPOINT,
                project_name=PROJECT_NAME,
            )

            # Verificar conexión
            logging.info("Verificando conexión con el agente...")
            agent = project.agents.get_agent(AGENT_ID)
            logging.info(f"✅ Cliente inicializado exitosamente. Agente: {agent.id}")
            return True
        else:
            api_key_status = "not_found"
            initialization_error = "API Key no encontrada en variables de entorno"
            logging.error(f"❌ {initialization_error}")
            logging.error(f"Variables disponibles: {found_vars}")
            return False

    except Exception as e:
        initialization_error = f"Error: {str(e)}"
        logging.error(f"❌ Error crítico: {initialization_error}")
        project = None
        api_key_status = "error"
        return False


# Intentar inicializar al arrancar
logging.info("=== INICIANDO FUNCTION APP ===")
initialize_client()


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint con información detallada"""
    logging.info("Health check llamado")

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Reintentar inicialización si falló
    if not project and api_key_status != "checking":
        logging.info("Reintentando inicialización...")
        initialize_client()

    # Información del entorno
    env_debug = {
        "total_vars": len(os.environ),
        "azure_vars": [],
        "functions_version": os.environ.get("FUNCTIONS_EXTENSION_VERSION", "unknown"),
        "python_version": os.sys.version,
    }

    # Buscar variables Azure (con valores parcialmente ocultos)
    for key in os.environ:
        if "AZURE" in key.upper() or "API" in key.upper():
            value = os.environ[key]
            if len(value) > 20:
                masked = f"{value[:5]}...{value[-5:]}"
            else:
                masked = "***"
            env_debug["azure_vars"].append({key: masked})

    health_status = {
        "status": "healthy" if project else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_status": api_key_status,
        "api_key_configured": bool(os.environ.get("AZURE_AI_API_KEY")),
        "client_initialized": bool(project),
        "initialization_error": initialization_error,
        "agent_id": AGENT_ID,
        "endpoint": PROJECT_ENDPOINT,
        "project_name": PROJECT_NAME,
        "environment": env_debug,
    }

    # Agregar sugerencias si hay problemas
    if not project:
        if not os.environ.get("AZURE_AI_API_KEY"):
            health_status["solution"] = {
                "message": "API Key no encontrada",
                "steps": [
                    "1. En Azure Portal, ir a tu Function App",
                    "2. Configuración > Configuración de la aplicación",
                    "3. Agregar nueva configuración: AZURE_AI_API_KEY = [tu key]",
                    "4. Hacer clic en Guardar",
                    "5. Hacer clic en Actualizar para aplicar cambios",
                ],
            }

    status_code = 200 if project else 503

    return func.HttpResponse(
        json.dumps(health_status, indent=2), status_code=status_code, headers=headers
    )


@app.route(route="test", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Test endpoint simple"""
    logging.info("Test endpoint llamado")

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    test_data = {
        "message": "Function App is running",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_present": bool(os.environ.get("AZURE_AI_API_KEY")),
        "api_key_length": len(os.environ.get("AZURE_AI_API_KEY", "")),
        "client_ready": bool(project),
        "routes_registered": ["health", "test", "chat", "debug"],
    }

    return func.HttpResponse(
        json.dumps(test_data, indent=2), status_code=200, headers=headers
    )


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint principal del chat"""
    logging.info("Chat endpoint llamado")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    # Verificar si el cliente está inicializado
    if not project:
        logging.warning("Cliente no inicializado, reintentando...")
        if not initialize_client():
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "Servicio no disponible",
                        "details": "No se puede conectar con Azure AI",
                        "initialization_error": initialization_error,
                    }
                ),
                status_code=503,
                headers=headers,
            )

    try:
        # Obtener mensaje
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "El mensaje es requerido"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Procesando mensaje: {user_message[:50]}...")

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
            error_msg = str(run.last_error) if run.last_error else "Error desconocido"
            return func.HttpResponse(
                json.dumps({"error": "Error procesando mensaje", "details": error_msg}),
                status_code=500,
                headers=headers,
            )

        # Obtener respuesta
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        bot_response = "No se pudo generar una respuesta"
        for msg in reversed(list(messages)):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        return func.HttpResponse(
            json.dumps(
                {"response": bot_response, "thread_id": thread.id, "status": "success"}
            ),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Error en chat: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": "Error interno", "details": str(e)}),
            status_code=500,
            headers=headers,
        )


@app.route(route="chat", methods=["OPTIONS"])
def chat_options(req: func.HttpRequest) -> func.HttpResponse:
    """CORS preflight para chat"""
    logging.info("Chat OPTIONS llamado")
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return func.HttpResponse("", status_code=204, headers=headers)


@app.route(route="debug", methods=["GET"])
def debug_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Debug endpoint para diagnóstico"""
    logging.info("Debug endpoint llamado")

    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}

    # Recopilar información de debug
    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "environment_variables": {},
        "azure_specific": {},
        "api_key_check": {
            "present": False,
            "length": 0,
            "starts_with": "",
            "ends_with": "",
        },
        "client_status": {"initialized": bool(project), "error": initialization_error},
        "python_info": {"version": os.sys.version, "platform": os.sys.platform},
    }

    # Verificar API Key específicamente
    api_key = os.environ.get("AZURE_AI_API_KEY")
    if api_key:
        debug_info["api_key_check"] = {
            "present": True,
            "length": len(api_key),
            "starts_with": api_key[:10] if len(api_key) > 10 else api_key,
            "ends_with": api_key[-10:] if len(api_key) > 10 else api_key,
        }

    # Listar variables relevantes
    for key in sorted(os.environ.keys()):
        if any(term in key.upper() for term in ["AZURE", "API", "AI", "FUNCTION"]):
            value = os.environ[key]
            if len(value) > 30:
                masked = f"{value[:10]}...{value[-10:]}"
            else:
                masked = "***"
            debug_info["azure_specific"][key] = masked

    # Contar total de variables
    debug_info["environment_variables"]["total_count"] = len(os.environ)
    debug_info["environment_variables"]["azure_count"] = len(
        debug_info["azure_specific"]
    )

    return func.HttpResponse(
        json.dumps(debug_info, indent=2), status_code=200, headers=headers
    )
