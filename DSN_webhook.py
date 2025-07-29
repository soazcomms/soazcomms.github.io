# DSN_webhook.py
import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # store your PAT token as an env var
REPO = "soazcomms/soazcomms.github.io"
WORKFLOW = "DSN_generate-dashboard.yml"

@app.route("/run", methods=["GET"])
def run_workflow():
    from_time = request.args.get("from")
    to_time = request.args.get("to")
    label = request.args.get("label")

    if not (from_time and to_time and label):
        return jsonify({"error": "Missing required parameters"}), 400

    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "from": from_time,
            "to": to_time,
            "label": label
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return jsonify({"status": response.status_code, "response": response.json() if response.content else {}})

if __name__ == "__main__":
    app.run()
