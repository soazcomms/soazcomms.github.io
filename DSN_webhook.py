from flask import Flask, request, jsonify, make_response
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Load GitHub token from .env
load_dotenv()
GITHUB_TOKEN = os.getenv("DSN_PAT")  # Must be a classic PAT with 'repo' and 'workflow'

REPO = "soazcomms/soazcomms.github.io"
EVENT_TYPE = "DSN_analysis"
BRANCH = "main"

app = Flask(__name__)

@app.route("/DSN_webhook", methods=["POST", "OPTIONS"])
def trigger_analysis():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.status_code = 204
        return response

    try:
        payload = request.get_json(force=True)

        raw_label = payload.get("label")
        label = raw_label[:8] if raw_label else None
        if not label:
            return jsonify({"error": "Missing or invalid label"}), 400

        t_from = payload.get("from")
        t_to = payload.get("to")

        # Validate input
        missing = [k for k in ("label", "from", "to") if payload.get(k) is None]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        # Write initial "processing" status JSON
        with open(f"public/status/status-{label}.json", "w") as f:
            json.dump({
                "status": "⏳ Generating plots...",
                "html": ""
            }, f)

        print(f"[{datetime.utcnow().isoformat()}] Trigger received:")
        print(f"  label: {label}")
        print(f"  from:  {t_from}")
        print(f"  to:    {t_to}")

        # Ensure public/status directory exists
        os.makedirs("public/status", exist_ok=True)

    
        # Dispatch to GitHub
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
            print("Status:", response.status_code)
            print("Body:", response.text)
            return jsonify({"error": "GitHub dispatch failed", "details": response.text}), 500

        print("✅ GitHub dispatch succeeded.")
        result = jsonify({"status": "✅ Triggered successfully."})
        result.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        return result

    except Exception as e:
        print(f"❌ Exception: {e}")
        result = jsonify({"error": str(e)})
        result.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        return result, 500

@app.route("/")
def index():
    return "✅ DSN Webhook is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
