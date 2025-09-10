import azure.functions as func
import json
import logging
import os
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

@app.function_name(name="ProcessAgentConversation")
@app.queue_output(arg_name="outputQueueItem", queue_name="ai-agent-output", connection="STORAGE_CONNECTION")
@app.queue_trigger(arg_name="msg", queue_name="ai-agent-input", connection="STORAGE_CONNECTION")
def process_agent_conversation(msg: func.QueueMessage, outputQueueItem: func.Out[str]) -> None:
    """
    Función principal para procesar conversaciones con el agente existente
    """
    try:
        # Procesar mensaje de entrada
        message_data = message_processor.parse_queue_message(msg)
        logging.info(f'Procesando consulta: {message_data.query}')
        
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
        logging.error(f"Error en process_agent_conversation: {str(e)}")
        error_response = response_formatter.format_error_response(
            str(e), 
            message_data.correlation_id if 'message_data' in locals() else 'unknown'
        )
        outputQueueItem.set(json.dumps(error_response).encode('utf-8'))

@app.function_name(name="DirectSearchQuery")
@app.queue_output(arg_name="outputQueueItem", queue_name="search-output", connection="STORAGE_CONNECTION")
@app.queue_trigger(arg_name="msg", queue_name="search-input", connection="STORAGE_CONNECTION")
def direct_search_query(msg: func.QueueMessage, outputQueueItem: func.Out[str]) -> None:
    """
    Función para búsquedas directas en AI Search (sin usar el agente)
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
        logging.error(f"Error en direct_search_query: {str(e)}")

@app.function_name(name="HealthCheck")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint de verificación de salud
    """
    return func.HttpResponse(
        json.dumps({"status": "healthy", "service": "poc4-chatbot-functions"}),
        mimetype="application/json",
        status_code=200
    )