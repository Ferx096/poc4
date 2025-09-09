import os
import time
import logging
from typing import Optional
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from models.response_models import AgentResponse

class ExistingAgentClient:
    def __init__(self):
        """
        Inicializa el cliente para interactuar con el agente existente
        """
        self.project_client = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint=os.environ["PROJECT_ENDPOINT"]
        )
        self.agent_id = os.environ["EXISTING_AGENT_ID"]
        self.threads = {}  # Cache de hilos por sesión
        
    def chat_with_agent(self, query: str, thread_id: Optional[str] = None) -> AgentResponse:
        """
        Envía una consulta al agente existente y devuelve la respuesta
        """
        try:
            # Usar hilo existente o crear uno nuevo
            if thread_id and thread_id in self.threads:
                thread = self.threads[thread_id]
            else:
                thread = self.project_client.agents.create_thread()
                if thread_id:
                    self.threads[thread_id] = thread
                    
            # Enviar mensaje al agente
            message = self.project_client.agents.create_message(
                thread_id=thread.id,
                role="user",
                content=query
            )
            
            # Ejecutar el agente
            run = self.project_client.agents.create_run(
                thread_id=thread.id,
                agent_id=self.agent_id
            )
            
            # Esperar respuesta
            response_text = self._wait_for_response(thread.id, run.id)
            
            return AgentResponse(
                content=response_text,
                thread_id=thread.id,
                run_id=run.id,
                success=True
            )
            
        except Exception as e:
            logging.error(f"Error en chat_with_agent: {str(e)}")
            return AgentResponse(
                content=f"Error: {str(e)}",
                thread_id=thread_id,
                run_id=None,
                success=False
            )
    
    def _wait_for_response(self, thread_id: str, run_id: str, max_wait: int = 60) -> str:
        """
        Espera a que el agente complete la ejecución y devuelve la respuesta
        """
        wait_time = 0
        while wait_time < max_wait:
            run = self.project_client.agents.get_run(thread_id=thread_id, run_id=run_id)
            
            if run.status == "completed":
                # Obtener la última respuesta del asistente
                messages = self.project_client.agents.list_messages(thread_id=thread_id)
                for message in messages.data:
                    if message.role == "assistant":
                        return message.content[0].text.value
                break
            elif run.status in ["failed", "expired", "cancelled"]:
                raise Exception(f"El agente falló con estado: {run.status}")
            
            time.sleep(1)
            wait_time += 1
        
        raise Exception("Timeout esperando respuesta del agente")