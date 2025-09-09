from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class AgentResponse:
    """
    Respuesta del agente
    """
    content: str
    thread_id: Optional[str]
    run_id: Optional[str]
    success: bool
    citations: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class SearchResult:
    """
    Resultado de búsqueda individual
    """
    content: str
    title: str
    score: float
    source: str
    highlights: Dict[str, List[str]]