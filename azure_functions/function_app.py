import azure.functions as func
import json
import logging
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder
import os

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Configuración del cliente de Azure AI
project = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint="https://ia-analytics.services.ai.azure.com/api/projects/PoC",
)

AGENT_ID = "asst_XizkjMGP4EQaFZYnygjH8BET"


@app.route(route="chat", methods=["POST"])
def chat_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Chat endpoint called")

    # Headers CORS
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    try:
        # Obtener mensaje del request
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "Message is required"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Processing message: {user_message}")

        # Obtener el agente
        agent = project.agents.get_agent(AGENT_ID)

        # Crear thread
        thread = project.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")

        # Crear mensaje del usuario
        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )

        # Ejecutar el agente
        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
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
        messages = project.agents.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )

        # Extraer la respuesta del agente (último mensaje que no sea del usuario)
        bot_response = "Lo siento, no pude generar una respuesta."
        for msg in reversed(messages):
            if msg.role != "user" and msg.text_messages:
                bot_response = msg.text_messages[-1].text.value
                break

        logging.info(f"Bot response: {bot_response}")

        return func.HttpResponse(
            json.dumps({"response": bot_response, "thread_id": thread.id}),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Error in chat endpoint: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": "Error interno del servidor", "details": str(e)}),
            status_code=500,
            headers=headers,
        )


# Manejar preflight requests (OPTIONS)
@app.route(route="chat", methods=["OPTIONS"])
def chat_options(req: func.HttpRequest) -> func.HttpResponse:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    return func.HttpResponse("", status_code=200, headers=headers)
