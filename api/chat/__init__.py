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

            endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
            agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")
            api_key = os.environ.get("AZURE_AI_PROJECT_API_KEY")

            if not all([endpoint, agent_id, api_key]):
                missing = []
                if not endpoint:
                    missing.append("AZURE_EXISTING_AIPROJECT_ENDPOINT")
                if not agent_id:
                    missing.append("AZURE_EXISTING_AGENT_ID")
                if not api_key:
                    missing.append("AZURE_AI_PROJECT_API_KEY")

                return func.HttpResponse(
                    json.dumps(
                        {"error": "Missing environment variables", "missing": missing}
                    ),
                    status_code=500,
                    headers=headers,
                )

            try:
                from azure.ai.projects import AIProjectClient
                from azure.core.credentials import AzureKeyCredential

                credential = AzureKeyCredential(api_key)
                project = AIProjectClient(credential=credential, endpoint=endpoint)

                agent = project.agents.get_agent(agent_id)
                thread = project.agents.threads.create()

                project.agents.messages.create(
                    thread_id=thread.id, role="user", content=user_message
                )

                run = project.agents.runs.create_and_process(
                    thread_id=thread.id, agent_id=agent.id
                )

                if run.status == "failed":
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Agent run failed",
                                "details": str(getattr(run, "last_error", "Unknown")),
                            }
                        ),
                        status_code=500,
                        headers=headers,
                    )

                messages = project.agents.messages.list(thread_id=thread.id)

                assistant_response = ""
                if messages:
                    for msg in reversed(messages):
                        if (
                            msg.role == "assistant"
                            and hasattr(msg, "text_messages")
                            and msg.text_messages
                        ):
                            assistant_response = msg.text_messages[-1].text.value
                            break

                if not assistant_response:
                    assistant_response = "Lo siento, no pude generar una respuesta."

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
