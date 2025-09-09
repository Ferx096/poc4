import json
import logging
import azure.functions as func
from models.message_models import QueueMessage

class MessageProcessor:
    def parse_queue_message(self, msg: func.QueueMessage) -> QueueMessage:
        """
        Parsea mensaje de la cola y devuelve objeto tipado
        """
        try:
            message_payload = json.loads(msg.get_body().decode('utf-8'))
            
            return QueueMessage(
                query=message_payload.get('query', ''),
                correlation_id=message_payload.get('CorrelationId', ''),
                thread_id=message_payload.get('threadId'),
                user_id=message_payload.get('userId'),
                session_id=message_payload.get('sessionId'),
                metadata=message_payload.get('metadata', {})
            )
        except Exception as e:
            logging.error(f"Error parseando mensaje: {str(e)}")
            raise