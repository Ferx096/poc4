import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import AzureError
import azure.functions as func

# Configuración desde variables de entorno
PROJECT_ENDPOINT = os.environ.get("PROJECT_ENDPOINT")
AGENT_ID = os.environ.get("EXISTING_AGENT_ID")

class AgentProxyClient:
    def __init__(self):
        """Inicializar cliente del agente con autenticación segura"""
        try:
            self.credential = DefaultAzureCredential()
            self.project_client = AIProjectClient(
                credential=self.credential,
                endpoint=PROJECT_ENDPOINT
            )
            self.agent_id = AGENT_ID
            self.threads_cache = {}
            logging.info(f"Cliente inicializado para agente: {self.agent_id}")
        except Exception as e:
            logging.error(f"Error inicializando cliente: {str(e)}")
            raise

    async def chat_with_agent(self, message: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """Envía mensaje al agente usando la API correcta de Azure AI Foundry"""
        try:
            # Crear o recuperar thread
            if thread_id and thread_id in self.threads_cache:
                thread = self.threads_cache[thread_id]
                logging.info(f"Usando thread existente: {thread.id}")
            else:
                thread = self.project_client.agents.create_thread()
                if thread_id:
                    self.threads_cache[thread_id] = thread
                logging.info(f"Nuevo thread creado: {thread.id}")

            # Crear mensaje del usuario
            message_obj = self.project_client.agents.create_message(
                thread_id=thread.id,
                role="user",
                content=message
            )

            # Ejecutar el agente
            run = self.project_client.agents.create_run(
                thread_id=thread.id,
                agent_id=self.agent_id
            )

            # Esperar respuesta
            response_content = await self._wait_for_completion(thread.id, run.id)

            return {
                "success": True,
                "content": response_content,
                "thread_id": thread.id,
                "run_id": run.id
            }

        except Exception as e:
            logging.error(f"Error en chat: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _wait_for_completion(self, thread_id: str, run_id: str, max_wait: int = 60) -> str:
        """Espera a que el agente complete la ejecución"""
        wait_time = 0
        check_interval = 2

        while wait_time < max_wait:
            try:
                run = self.project_client.agents.get_run(thread_id=thread_id, run_id=run_id)
                
                if run.status == "completed":
                    messages = self.project_client.agents.list_messages(thread_id=thread_id)
                    for message in messages.data:
                        if message.role == "assistant":
                            return message.content[0].text.value
                    return "Respuesta recibida sin contenido."

                elif run.status in ["failed", "expired", "cancelled"]:
                    raise Exception(f"Run falló con estado: {run.status}")

                await asyncio.sleep(check_interval)
                wait_time += check_interval

            except Exception as e:
                logging.error(f"Error verificando estado: {str(e)}")
                raise

        raise Exception(f"Timeout esperando respuesta ({max_wait}s)")

# Instancia global del cliente
agent_client = None

def get_agent_client():
    """Singleton para el cliente del agente"""
    global agent_client
    if agent_client is None:
        agent_client = AgentProxyClient()
    return agent_client

# Azure Function App
app = func.FunctionApp()

@app.function_name(name="ChatProxy")
@app.route(route="chat", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def chat_proxy(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint HTTP que hace de proxy entre el frontend y Azure AI Foundry Agents"""
    
    # Headers CORS
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Content-Type': 'application/json'
    }
    
    try:
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "Body JSON requerido"}),
                status_code=400,
                headers=headers,
                mimetype="application/json"
            )

        message = req_body.get('message', '').strip()
        thread_id = req_body.get('thread_id')

        if not message:
            return func.HttpResponse(
                json.dumps({"error": "Mensaje requerido"}),
                status_code=400,
                headers=headers,
                mimetype="application/json"
            )

        if len(message) > 1000:
            return func.HttpResponse(
                json.dumps({"error": "Mensaje demasiado largo"}),
                status_code=400,
                headers=headers,
                mimetype="application/json"
            )

        # Obtener cliente y enviar mensaje
        client = get_agent_client()
        response = await client.chat_with_agent(message, thread_id)

        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            status_code=200,
            headers=headers,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error en chat_proxy: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": "Error interno del servidor"
            }),
            status_code=500,
            headers=headers,
            mimetype="application/json"
        )

@app.function_name(name="HealthCheck")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint de verificación de salud"""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }
    
    try:
        health_status = {
            "status": "healthy",
            "service": "AFP Prima Chat Proxy",
            "agent_id": AGENT_ID,
            "timestamp": func.datetime.utcnow().isoformat()
        }

        return func.HttpResponse(
            json.dumps(health_status),
            status_code=200,
            headers=headers,
            mimetype="application/json"
        )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"status": "unhealthy", "error": str(e)}),
            status_code=503,
            headers=headers,
            mimetype="application/json"
        )

@app.function_name(name="Options")
@app.route(route="{*route}", methods=["OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def options_handler(req: func.HttpRequest) -> func.HttpResponse:
    """Manejar requests OPTIONS para CORS"""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '3600'
    }
    
    return func.HttpResponse("", status_code=200, headers=headers)