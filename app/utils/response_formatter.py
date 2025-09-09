import json
from typing import List
from models.response_models import AgentResponse, SearchResult
from models.message_models import ResponseMessage

class ResponseFormatter:
    def format_agent_response(self, agent_response: AgentResponse, correlation_id: str) -> dict:
        """
        Formatea respuesta del agente para la cola de salida
        """
        return {
            'Value': agent_response.content,
            'CorrelationId': correlation_id,
            'Success': agent_response.success,
            'ThreadId': agent_response.thread_id,
            'RunId': agent_response.run_id,
            'Citations': agent_response.citations or [],
            'Metadata': agent_response.metadata or {}
        }
    
    def format_search_response(self, search_results: List[SearchResult], correlation_id: str) -> dict:
        """
        Formatea resultados de búsqueda para la cola de salida
        """
        if not search_results:
            response_text = "No se encontraron resultados relevantes para tu consulta."
        else:
            response_text = self._build_search_response_text(search_results)
        
        return {
            'Value': response_text,
            'CorrelationId': correlation_id,
            'Success': True,
            'ResultCount': len(search_results),
            'Results': [
                {
                    'title': result.title,
                    'content': result.content[:200] + '...' if len(result.content) > 200 else result.content,
                    'score': result.score,
                    'source': result.source
                }
                for result in search_results[:3]  # Solo los 3 mejores
            ]
        }
    
    def format_error_response(self, error_message: str, correlation_id: str) -> dict:
        """
        Formatea respuesta de error
        """
        return {
            'Value': f'Lo siento, ocurrió un error procesando tu consulta: {error_message}',
            'CorrelationId': correlation_id,
            'Success': False,
            'Error': error_message
        }
    
    def _build_search_response_text(self, results: List[SearchResult]) -> str:
        """
        Construye texto de respuesta basado en resultados de búsqueda
        """
        response = "Basado en la información encontrada en tus documentos:\n\n"
        
        for i, result in enumerate(results[:3], 1):
            response += f"**{i}. {result.title}**\n"
            response += f"{result.content[:300]}...\n"
            response += f"*(Relevancia: {result.score:.2f})*\n\n"
        
        if len(results) > 3:
            response += f"*Se encontraron {len(results)} resultados adicionales.*"
        
        return response