import azure.functions as func
import json
import logging
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.agents.models import ListSortOrder
import os
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Obtener la API key de las variables de entorno
API_KEY = os.getenv("AZURE_AI_API_KEY")

if not API_KEY:
    logging.error("AZURE_AI_API_KEY not found in environment variables")
else:
    logging.info("API Key loaded successfully")

# Configuración del cliente de Azure AI con API Key
try:
    project = AIProjectClient(
        credential=AzureKeyCredential(API_KEY) if API_KEY else None,
        endpoint="https://ia-analytics.services.ai.azure.com/",  # Sin /api/projects/PoC
        project_name="PoC",  # Especificar el proyecto por separado
    )
    logging.info("AIProjectClient initialized successfully")
except Exception as e:
    logging.error(f"Error initializing AIProjectClient: {str(e)}")
    project = None

AGENT_ID = "asst_XizkjMGP4EQaFZYnygjH8BET"


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Chat endpoint called")

    # Headers CORS - Permitir tu dominio de GitHub Pages
    headers = {
        "Access-Control-Allow-Origin": "*",  # Cambiado a * para pruebas
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    # Verificar que el cliente esté inicializado
    if not project:
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Servicio no disponible",
                    "details": "El cliente de AI no está inicializado. Verifica la configuración.",
                }
            ),
            status_code=503,
            headers=headers,
        )

    if not API_KEY:
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Configuración incompleta",
                    "details": "API Key no configurada en el servidor",
                }
            ),
            status_code=500,
            headers=headers,
        )

    try:
        # Obtener y validar el body
        try:
            req_body = req.get_json()
        except ValueError as e:
            logging.error(f"Invalid JSON in request: {e}")
            return func.HttpResponse(
                json.dumps({"error": "Formato JSON inválido"}),
                status_code=400,
                headers=headers,
            )

        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "El mensaje es requerido"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(
            f"Processing message: {user_message[:50]}..."
        )  # Log primeros 50 chars

        # Obtener el agente
        try:
            agent = project.agents.get_agent(AGENT_ID)
            logging.info(f"Agent retrieved successfully: {agent.id}")
        except Exception as e:
            logging.error(f"Error retrieving agent: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "No se pudo acceder al agente",
                        "details": f"Error: {str(e)}",
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Crear thread
        try:
            thread = project.agents.threads.create()
            logging.info(f"Created thread: {thread.id}")
        except Exception as e:
            logging.error(f"Error creating thread: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {"error": "No se pudo crear la conversación", "details": str(e)}
                ),
                status_code=500,
                headers=headers,
            )

        # Crear mensaje del usuario
        try:
            message = project.agents.messages.create(
                thread_id=thread.id, role="user", content=user_message
            )
            logging.info(f"Created message in thread")
        except Exception as e:
            logging.error(f"Error creating message: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {"error": "No se pudo procesar el mensaje", "details": str(e)}
                ),
                status_code=500,
                headers=headers,
            )

        # Ejecutar el agente
        try:
            logging.info("Starting agent run...")
            run = project.agents.runs.create_and_process(
                thread_id=thread.id, agent_id=agent.id
            )
            logging.info(f"Run completed with status: {run.status}")
        except Exception as e:
            logging.error(f"Error running agent: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": "Error al ejecutar el agente", "details": str(e)}),
                status_code=500,
                headers=headers,
            )

        if run.status == "failed":
            logging.error(f"Run failed: {run.last_error}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "El agente no pudo procesar tu consulta",
                        "details": (
                            str(run.last_error)
                            if run.last_error
                            else "Error desconocido"
                        ),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Obtener mensajes
        try:
            messages = project.agents.messages.list(
                thread_id=thread.id, order=ListSortOrder.ASCENDING
            )
            logging.info(f"Retrieved {len(list(messages))} messages")
        except Exception as e:
            logging.error(f"Error retrieving messages: {str(e)}")
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "No se pudieron recuperar los mensajes",
                        "details": str(e),
                    }
                ),
                status_code=500,
                headers=headers,
            )

        # Extraer la respuesta del agente
        bot_response = "Lo siento, no pude generar una respuesta."
        messages_list = list(messages)
        for msg in reversed(messages_list):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        logging.info(f"Bot response generated successfully")

        return func.HttpResponse(
            json.dumps(
                {"response": bot_response, "thread_id": thread.id, "status": "success"}
            ),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Unexpected error in chat endpoint: {str(e)}", exc_info=True)
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


# Manejar preflight requests (OPTIONS)
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


# Health check endpoint
@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint para verificar el estado de la función"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    health_status = {
        "status": "checking",
        "timestamp": datetime.utcnow().isoformat(),
        "api_key_configured": bool(API_KEY),
        "client_initialized": bool(project),
    }

    if not API_KEY:
        health_status["status"] = "unhealthy"
        health_status["error"] = "API Key not configured"
        return func.HttpResponse(
            json.dumps(health_status), status_code=503, headers=headers
        )

    if not project:
        health_status["status"] = "unhealthy"
        health_status["error"] = "AI Client not initialized"
        return func.HttpResponse(
            json.dumps(health_status), status_code=503, headers=headers
        )

    try:
        # Intentar obtener el agente como prueba
        agent = project.agents.get_agent(AGENT_ID)
        health_status["status"] = "healthy"
        health_status["agent_id"] = AGENT_ID
        health_status["agent_connected"] = True

        return func.HttpResponse(
            json.dumps(health_status), status_code=200, headers=headers
        )
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = f"Cannot connect to agent: {str(e)}"

        return func.HttpResponse(
            json.dumps(health_status), status_code=503, headers=headers
        )
