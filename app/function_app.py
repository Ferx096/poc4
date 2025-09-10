import azure.functions as func
import json
import logging
import os
import asyncio
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

# ====== FUNCIONES HTTP (NUEVAS) ======

@app.function_name(name="ProcessAgentConversation")
@app.route(route="ProcessAgentConversation", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def process_agent_conversation_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint HTTP para procesar conversaciones con el agente
    """
    try:
        # Obtener datos del request
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "No se proporcionaron datos"}),
                status_code=400,
                mimetype="application/json"
            )
        
        query = req_body.get('query', '')
        thread_id = req_body.get('threadId')
        correlation_id = req_body.get('CorrelationId', 'unknown')
        
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Query es requerido"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f'Procesando consulta HTTP: {query}')
        
        # Interactuar con el agente existente
        response = agent_client.chat_with_agent(query, thread_id)
        
        # Formatear respuesta
        formatted_response = response_formatter.format_agent_response(
            response, 
            correlation_id
        )
        
        return func.HttpResponse(
            json.dumps(formatted_response),
            status_code=200,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, X-Session-ID, X-Agent-ID"
            }
        )
        
    except Exception as e:
        logging.error(f"Error en process_agent_conversation_http: {str(e)}")
        error_response = {
            "error": str(e),
            "Value": f"Error procesando tu consulta: {str(e)}",
            "CorrelationId": req_body.get('CorrelationId', 'unknown') if req_body else 'unknown',
            "Success": False
        }
        return func.HttpResponse(
            json.dumps(error_response),
            status_code=500,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, X-Session-ID, X-Agent-ID"
            }
        )

@app.function_name(name="DirectSearchQuery")
@app.route(route="DirectSearchQuery", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def direct_search_query_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint HTTP para búsquedas directas
    """
    try:
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "No se proporcionaron datos"}),
                status_code=400,
                mimetype="application/json"
            )
        
        query = req_body.get('query', '')
        correlation_id = req_body.get('CorrelationId', 'unknown')
        
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Query es requerido"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f'Procesando búsqueda HTTP: {query}')
        
        # Realizar búsqueda directa
        search_results = search_service.search(
            query=query,
            top_k=5
        )
        
        # Formatear respuesta
        formatted_response = response_formatter.format_search_response(
            search_results,
            correlation_id
        )
        
        return func.HttpResponse(
            json.dumps(formatted_response),
            status_code=200,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept"
            }
        )
        
    except Exception as e:
        logging.error(f"Error en direct_search_query_http: {str(e)}")
        error_response = {
            "error": str(e),
            "Value": f"Error en búsqueda: {str(e)}",
            "CorrelationId": correlation_id,
            "Success": False
        }
        return func.HttpResponse(
            json.dumps(error_response),
            status_code=500,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept"
            }
        )

@app.function_name(name="HealthCheck")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint de verificación de salud
    """
    return func.HttpResponse(
        json.dumps({
            "status": "healthy", 
            "service": "poc4-chatbot-functions",
            "timestamp": func.datetime.datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }),
        mimetype="application/json",
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept"
        }
    )

# Función para manejar OPTIONS (CORS preflight)
@app.function_name(name="CorsHandler")
@app.route(route="{*route}", methods=["OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def cors_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Maneja las peticiones OPTIONS para CORS
    """
    return func.HttpResponse(
        "",
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept, X-Session-ID, X-Agent-ID, User-Agent",
            "Access-Control-Max-Age": "86400"
        }
    )

# ====== FUNCIONES DE COLA (EXISTENTES) ======

@app.function_name(name="ProcessAgentConversationQueue")
@app.queue_output(arg_name="outputQueueItem", queue_name="ai-agent-output", connection="STORAGE_CONNECTION")
@app.queue_trigger(arg_name="msg", queue_name="ai-agent-input", connection="STORAGE_CONNECTION")
def process_agent_conversation_queue(msg: func.QueueMessage, outputQueueItem: func.Out[str]) -> None:
    """
    Función de cola para procesar conversaciones con el agente existente
    """
    try:
        # Procesar mensaje de entrada
        message_data = message_processor.parse_queue_message(msg)
        logging.info(f'Procesando consulta de cola: {message_data.query}')
        
        # Interactuar con el agente existente
        response = agent_client.chat_with_agent(
            message_data.query,
            message_data.thread_id
        )
        
        # Formatear y enviar respuesta
        formatted_response = response_formatter.format_agent_response(
            response, 
            message_data.correlation_id
        )
        
        outputQueueItem.set(json.dumps(formatted_response).encode('utf-8'))
        logging.info(f"Respuesta enviada para correlación: {message_data.correlation_id}")
        
    except Exception as e:
        logging.error(f"Error en process_agent_conversation_queue: {str(e)}")
        error_response = response_formatter.format_error_response(
            str(e), 
            message_data.correlation_id if 'message_data' in locals() else 'unknown'
        )
        outputQueueItem.set(json.dumps(error_response).encode('utf-8'))

@app.function_name(name="DirectSearchQueryQueue")
@app.queue_output(arg_name="outputQueueItem", queue_name="search-output", connection="STORAGE_CONNECTION")
@app.queue_trigger(arg_name="msg", queue_name="search-input", connection="STORAGE_CONNECTION")
def direct_search_query_queue(msg: func.QueueMessage, outputQueueItem: func.Out[str]) -> None:
    """
    Función de cola para búsquedas directas en AI Search
    """
    try:
        message_data = message_processor.parse_queue_message(msg)
        
        # Realizar búsqueda directa
        search_results = search_service.search(
            query=message_data.query,
            top_k=5
        )
        
        # Formatear respuesta
        formatted_response = response_formatter.format_search_response(
            search_results,
            message_data.correlation_id
        )
        
        outputQueueItem.set(json.dumps(formatted_response).encode('utf-8'))
        
    except Exception as e:
        logging.error(f"Error en direct_search_query_queue: {str(e)}")