from flask import Flask, request, jsonify
import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
CORS(app)

GITHUB_REPO = "soazcomms/soazcomms.github.io"
GITHUB_WORKFLOW = "DSN_analysis.yml"
GITHUB_PAT = os.getenv("DSN_PAT")
STATUS_DIR = "public/status"  # For local write to gh-pages-tracked dir

@app.route("/DSN_webhook", methods=["GET", "POST"])
def dsn_webhook():
    data = request.get_json(silent=True) or request.args or {}

    label = data.get("label")
    from_time = data.get("from")
    to_time = data.get("to")

    if not all([label, from_time, to_time]):
        return jsonify({"error": "Missing label/from/to"}), 400

    print(f"🚀 Triggering for {label} from {from_time} to {to_time}")

    # Step 1: Write status JSON
    os.makedirs(STATUS_DIR, exist_ok=True)
    status_path = os.path.join(STATUS_DIR, f"{label}.json")
    with open(status_path, "w") as f:
        json.dump({
            "status": "generating",
            "label": label,
            "updated": datetime.utcnow().isoformat() + "Z",
            "url": ""
        }, f, indent=2)

    print(f"📝 Status file written to {status_path}")

    # Step 2: Call GitHub API to trigger workflow
    headers = {
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github+json"
    }

    dispatch_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "label": label,
            "from": from_time,
            "to": to_time
        }
    }

    r = requests.post(dispatch_url, headers=headers, json=payload)
    if r.status_code != 204:
        print(f"❌ GitHub API error {r.status_code}: {r.text}")
        return jsonify({"error": f"GitHub API error {r.status_code}: {r.text}"}), 500

    print(f"✅ GitHub workflow dispatched for {label}")
    return jsonify({"status": "✅ Triggered successfully."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
