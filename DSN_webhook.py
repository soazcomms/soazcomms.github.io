from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
from flask_cors import CORS

# Load token from .env
load_dotenv()
GITHUB_TOKEN = os.getenv("DSN_PAT")
if not GITHUB_TOKEN:
    raise EnvironmentError("❌ DSN_PAT is not set in .env")

# GitHub settings
REPO = "soazcomms/soazcomms.github.io"
EVENT_TYPE = "DSN_analysis"  # must match `on: repository_dispatch: types: [...]` in workflow
BRANCH = "main"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # more explicit CORS config

@app.route("/DSN_webhook", methods=["POST"])
def trigger_analysis():
    try:
        payload = request.get_json()
        label = payload.get("label")
        t_from = payload.get("from")
        t_to = payload.get("to")

        # Check required fields
        missing = [k for k in ("label", "from", "to") if payload.get(k) is None]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        print(f"🔔 Request received:\n  label: {label}\n  from:  {t_from}\n  to:    {t_to}")

        # Build dispatch
        url = f"https://api.github.com/repos/{REPO}/dispatches"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "event_type": EVENT_TYPE,
            "client_payload": {
                "label": label,
                "from": t_from,
                "to": t_to
            }
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 204:
            print("❌ GitHub dispatch failed:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            return jsonify({"error": "GitHub dispatch failed", "details": response.text}), 500

        print("✅ Workflow triggered.")
        return jsonify({"status": "✅ Triggered successfully."})

    except Exception as e:
        print(f"❌ Exception during webhook: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return "✅ DSN Webhook is running."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
