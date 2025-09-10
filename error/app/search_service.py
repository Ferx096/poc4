import os
import logging
from typing import List, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from models.response_models import SearchResult

class DirectSearchService:
    def __init__(self):
        """
        Inicializa el cliente de Azure AI Search
        """
        self.search_client = SearchClient(
            endpoint=os.environ["SEARCH_ENDPOINT"],
            index_name=os.environ["SEARCH_INDEX_NAME"],
            credential=DefaultAzureCredential()
        )
    
    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Realiza búsqueda en el índice de AI Search
        """
        try:
            # Realizar búsqueda híbrida (texto + vector)
            results = self.search_client.search(
                search_text=query,
                top=top_k,
                include_total_count=True,
                search_mode="all"
            )
            
            search_results = []
            for result in results:
                search_result = SearchResult(
                    content=result.get('content', ''),
                    title=result.get('title', ''),
                    score=result.get('@search.score', 0),
                    source=result.get('metadata_storage_path', ''),
                    highlights=result.get('@search.highlights', {})
                )
                search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logging.error(f"Error en búsqueda: {str(e)}")
            return []
    
    def vector_search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Realiza búsqueda vectorial específica
        """
        # Implementar búsqueda vectorial si es necesario
        pass