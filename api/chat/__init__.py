import json
import logging
import os
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AFP Prima chat function started")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Content-Type": "application/json",
    }

    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=headers)

    if req.method == "GET":
        return func.HttpResponse(
            json.dumps({"message": "Chat API is working", "method": "GET"}),
            status_code=200,
            headers=headers,
        )

    if req.method == "POST":
        try:
            req_body = req.get_json()
            if not req_body or "message" not in req_body:
                return func.HttpResponse(
                    json.dumps({"error": "Message is required"}),
                    status_code=400,
                    headers=headers,
                )

            user_message = req_body["message"]
            logging.info(f"Received message: {user_message}")

            # Obtener variables de entorno
            endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
            agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")

            # Opción A: Si usas API Key
            api_key = os.environ.get("AZURE_AI_PROJECT_API_KEY")

            # Opción B: Si usas DefaultAzureCredential (necesitas estas variables adicionales)
            subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
            resource_group = os.environ.get("AZURE_RESOURCE_GROUP")
            project_name = os.environ.get("AZURE_PROJECT_NAME")

            if not endpoint or not agent_id:
                missing = []
                if not endpoint:
                    missing.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                if not agent_id:
                    missing.append("AZURE_EXISTING_AGENT_ID")

                return func.HttpResponse(
                    json.dumps(
                        {
                            "error": "Missing required environment variables",
                            "missing": missing,
                        }
                    ),
                    status_code=500,
                    headers=headers,
                )

            try:
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential
                from azure.core.credentials import AzureKeyCredential

                # Inicializar el cliente según el método de autenticación disponible
                if api_key:
                    # Método 1: Usar API Key con el endpoint completo
                    # El endpoint debe incluir el api-version parameter
                    if "api-version" not in endpoint:
                        endpoint = f"{endpoint}?api-version=2024-10-01-preview"

                    # Crear headers personalizados para la autenticación con API Key
                    import requests

                    # Usar requests directamente para llamar al endpoint
                    headers_req = {
                        "api-key": api_key,
                        "Content-Type": "application/json",
                    }

                    # Construir la URL completa para el thread
                    thread_url = f"{endpoint}/threads"

                    # Crear un nuevo thread
                    thread_response = requests.post(thread_url, headers=headers_req)

                    if thread_response.status_code != 200:
                        raise Exception(
                            f"Failed to create thread: {thread_response.text}"
                        )

                    thread_id = thread_response.json()["id"]

                    # Añadir mensaje al thread
                    message_url = f"{endpoint}/threads/{thread_id}/messages"
                    message_data = {"role": "user", "content": user_message}

                    message_response = requests.post(
                        message_url, headers=headers_req, json=message_data
                    )

                    if message_response.status_code != 200:
                        raise Exception(
                            f"Failed to add message: {message_response.text}"
                        )

                    # Ejecutar el agente
                    run_url = f"{endpoint}/threads/{thread_id}/runs"
                    run_data = {"assistant_id": agent_id}

                    run_response = requests.post(
                        run_url, headers=headers_req, json=run_data
                    )

                    if run_response.status_code != 200:
                        raise Exception(f"Failed to create run: {run_response.text}")

                    run_id = run_response.json()["id"]

                    # Esperar a que el run termine
                    import time

                    max_attempts = 30
                    for _ in range(max_attempts):
                        run_status_url = f"{endpoint}/threads/{thread_id}/runs/{run_id}"
                        status_response = requests.get(
                            run_status_url, headers=headers_req
                        )

                        if status_response.status_code == 200:
                            status = status_response.json()["status"]
                            if status == "completed":
                                break
                            elif status == "failed":
                                raise Exception("Agent run failed")

                        time.sleep(1)

                    # Obtener mensajes
                    messages_url = f"{endpoint}/threads/{thread_id}/messages"
                    messages_response = requests.get(messages_url, headers=headers_req)

                    if messages_response.status_code != 200:
                        raise Exception(
                            f"Failed to get messages: {messages_response.text}"
                        )

                    messages = messages_response.json()["data"]

                    # Buscar la última respuesta del asistente
                    assistant_response = ""
                    for msg in messages:
                        if msg["role"] == "assistant":
                            if msg.get("content") and len(msg["content"]) > 0:
                                assistant_response = (
                                    msg["content"][0].get("text", {}).get("value", "")
                                )
                                break

                    if not assistant_response:
                        assistant_response = "Lo siento, no pude generar una respuesta."

                elif subscription_id and resource_group and project_name:
                    # Método 2: Usar DefaultAzureCredential (para identidad administrada)
                    credential = DefaultAzureCredential()

                    # Asegurarse de que el endpoint tenga el formato correcto
                    # Debe ser: https://{resource-name}.services.ai.azure.com/api/projects/{project-name}
                    if "/api/projects/" not in endpoint:
                        endpoint = f"{endpoint}/api/projects/{project_name}"

                    project = AIProjectClient(
                        credential=credential,
                        endpoint=endpoint,
                        subscription_id=subscription_id,
                        resource_group_name=resource_group,
                        project_name=project_name,
                    )

                    agent = project.agents.get_agent(agent_id)
                    thread = project.agents.threads.create()

                    project.agents.messages.create(
                        thread_id=thread.id, role="user", content=user_message
                    )

                    run = project.agents.runs.create_and_process(
                        thread_id=thread.id, assistant_id=agent.id
                    )

                    if run.status == "failed":
                        raise Exception(
                            f"Agent run failed: {getattr(run, 'last_error', 'Unknown')}"
                        )

                    messages = project.agents.messages.list(thread_id=thread.id)

                    assistant_response = ""
                    if messages:
                        for msg in reversed(list(messages)):
                            if msg.role == "assistant" and hasattr(msg, "content"):
                                if msg.content and len(msg.content) > 0:
                                    assistant_response = msg.content[0].text.value
                                    break

                    if not assistant_response:
                        assistant_response = "Lo siento, no pude generar una respuesta."

                else:
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Missing authentication credentials",
                                "details": "Provide either AZURE_AI_PROJECT_API_KEY or (AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_PROJECT_NAME)",
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )

                return func.HttpResponse(
                    json.dumps({"response": assistant_response}),
                    status_code=200,
                    headers=headers,
                )

            except Exception as e:
                logging.error(f"Azure AI error: {str(e)}")
                return func.HttpResponse(
                    json.dumps(
                        {"error": "Azure AI processing failed", "details": str(e)}
                    ),
                    status_code=500,
                    headers=headers,
                )

        except Exception as e:
            logging.error(f"Request processing error: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": "Request processing failed", "details": str(e)}),
                status_code=500,
                headers=headers,
            )

    return func.HttpResponse(
        json.dumps({"error": f"Method {req.method} not supported"}),
        status_code=405,
        headers=headers,
    )
