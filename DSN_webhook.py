from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import datetime

app = Flask(__name__)
CORS(app)  # Allow all origins for development

@app.route("/DSN_webhook", methods=["POST"])
def trigger_analysis():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing or invalid JSON payload"}), 400

        label = data.get("label")
        t_from = data.get("from")
        t_to = data.get("to")

        missing = [k for k in ("label", "from", "to") if data.get(k) is None]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

        # Log the received data
        print(f"[{datetime.datetime.utcnow().isoformat()}] Trigger received:")
        print(f"  label: {label}")
        print(f"  from:  {t_from}")
        print(f"  to:    {t_to}")
        sys.stdout.flush()

        # Trigger GitHub Actions or other processing here if needed
        return jsonify({"status": "✅ Triggered successfully"}), 200

    except Exception as e:
        print(f"❌ Exception: {e}", file=sys.stderr)
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return "✅ DSN Webhook is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
