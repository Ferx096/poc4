# api/chat.py
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")

        project = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint="https://ia-analytics.services.ai.azure.com/api/projects/PoC",
        )

        agent = project.agents.get_agent("asst_XizkjMGP4EQaFZYnygjH8BET")
        thread = project.agents.threads.create()

        message = project.agents.messages.create(
            thread_id=thread.id, role="user", content=user_message
        )

        run = project.agents.runs.create_and_process(
            thread_id=thread.id, agent_id=agent.id
        )

        if run.status == "failed":
            return jsonify({"error": "Agent failed"}), 500

        messages = project.agents.messages.list(thread_id=thread.id)
        response = messages[0].text_messages[-1].text.value if messages else ""

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run()
