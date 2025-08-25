import json
import logging
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("AFP Prima chat function processed a request.")

    # Configure CORS headers
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    # Handle preflight OPTIONS request
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=200, headers=headers)

    try:
        # Parse request body
        req_body = req.get_json()
        if not req_body or "message" not in req_body:
            return func.HttpResponse(
                json.dumps({"error": "Message is required"}),
                status_code=400,
                headers=headers,
            )

        user_message = req_body["message"]
        logging.info(f"Received message: {user_message}")

        # Initialize Azure AI Project Client
        project = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint="https://ia-analytics.services.ai.azure.com/api/projects/PoC",
        )

        # Get your agent
        agent = project.agents.get_agent("asst_XizkjMGP4EQaFZYnygjH8BET")
        logging.info(f"Got agent: {agent.id}")

        # Create a new thread for each conversation
        thread = project.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")

        # Create message
        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )

        # Run the agent
        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )

        if run.status == "failed":
            logging.error(f"Agent run failed: {run.last_error}")
            return func.HttpResponse(
                json.dumps(
                    {"error": "Agent processing failed", "details": str(run.last_error)}
                ),
                status_code=500,
                headers=headers,
            )

        # Get messages from the thread
        messages = project.agents.messages.list(thread_id=thread.id)

        # Extract the assistant's response
        assistant_response = ""
        for msg in messages:
            if msg.role == "assistant" and msg.text_messages:
                assistant_response = msg.text_messages[-1].text.value
                break

        if not assistant_response:
            assistant_response = "Lo siento, no pude generar una respuesta. Por favor intenta nuevamente."

        logging.info(f"Returning response: {assistant_response[:100]}...")

        return func.HttpResponse(
            json.dumps({"response": assistant_response}),
            status_code=200,
            headers=headers,
        )

    except Exception as e:
        logging.error(f"Error processing request: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": "Internal server error", "details": str(e)}),
            status_code=500,
            headers=headers,
        )
