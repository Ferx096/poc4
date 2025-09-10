from dataclasses import dataclass
from typing import Optional

@dataclass
class QueueMessage:
    """
    Modelo para mensajes de entrada de la cola
    """
    query: str
    correlation_id: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[dict] = None

@dataclass
class ResponseMessage:
    """
    Modelo para mensajes de respuesta
    """
    value: str
    correlation_id: str
    success: bool
    thread_id: Optional[str] = None
    metadata: Optional[dict] = None