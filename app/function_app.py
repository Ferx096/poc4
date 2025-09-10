import azure.functions as func
import json
import logging
import os
import datetime
import uuid
from agent_client import ExistingAgentClient
from search_service import DirectSearchService
from utils.message_processor import MessageProcessor
from utils.response_formatter import ResponseFormatter

app = func.FunctionApp()

# Inicializar servicios
agent_client = ExistingAgentClient()
search_service = DirectSearchService()
message_processor = MessageProcessor()
response_formatter = ResponseFormatter()

# ====== FUNCIONES HTTP PROXY (Ponen mensajes en colas) ======

@app.function_name(name="ProcessAgentConversationProxy")
@app.route(route="ProcessAgentConversation", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@app.queue_output(arg_name="outputQueueItem", queue_name="ai-agent-input", connection="STORAGE_CONNECTION")
def process_agent_conversation_proxy(req: func.HttpRequest, outputQueueItem: func.Out[str]) -> func.HttpResponse:
    """
    Proxy HTTP que coloca mensajes en la cola para procesamiento del agente
    """
    try:
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "No se proporcionaron datos"}),
                status_code=400,
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        query = req_body.get('query', '')
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Query es requerido"}),
                status_code=400,
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        # Crear mensaje para la cola
        correlation_id = req_body.get('CorrelationId', str(uuid.uuid4()))
        queue_message = {
            'query': query,
            'CorrelationId': correlation_id,
            'threadId': req_body.get('threadId'),
            'userId': req_body.get('userId', 'web_user'),
            'sessionId': req_body.get('sessionId'),
            'metadata': req_body.get('metadata', {
                'source': 'web_proxy',
                'timestamp': datetime.datetime.utcnow().isoformat()
            })
        }
        
        # Enviar a la cola
        outputQueueItem.set(json.dumps(queue_message))
        
        # Respuesta inmediata al frontend
        return func.HttpResponse(
            json.dumps({
                "message": "Consulta recibida y en procesamiento",
                "CorrelationId": correlation_id,
                "status": "queued",
                "timestamp": datetime.datetime.utcnow().isoformat()
            }),
            status_code=202,  # 202 Accepted
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept"
            }
        )
        
    except Exception as e:
        logging.error(f"Error en process_agent_conversation_proxy: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "error": str(e),
                "message": "Error procesando la solicitud"
            }),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )

@app.function_name(name="DirectSearchQueryProxy")
@app.route(route="DirectSearchQuery", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@app.queue_output(arg_name="outputQueueItem", queue_name="search-input", connection="STORAGE_CONNECTION")
def direct_search_query_proxy(req: func.HttpRequest, outputQueueItem: func.Out[str]) -> func.HttpResponse:
    """
    Proxy HTTP que coloca mensajes de búsqueda en la cola
    """
    try:
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "No se proporcionaron datos"}),
                status_code=400,
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        query = req_body.get('query', '')
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Query es requerido"}),
                status_code=400,
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        correlation_id = req_body.get('CorrelationId', str(uuid.uuid4()))
        queue_message = {
            'query': query,
            'CorrelationId': correlation_id,
            'metadata': req_body.get('metadata', {})
        }
        
        outputQueueItem.set(json.dumps(queue_message))
        
        return func.HttpResponse(
            json.dumps({
                "message": "Búsqueda recibida y en procesamiento",
                "CorrelationId": correlation_id,
                "status": "queued"
            }),
            status_code=202,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
        
    except Exception as e:
        logging.error(f"Error en direct_search_query_proxy: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )