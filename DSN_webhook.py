from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import datetime

app = Flask(__name__)

# Enable CORS for GitHub Pages origin
CORS(app, origins=["https://soazcomms.github.io"], methods=["POST", "OPTIONS"], allow_headers=["Content-Type"])

@app.route("/DSN_webhook", methods=["POST", "OPTIONS"])
def trigger_analysis():
    if request.method == "OPTIONS":
        # CORS preflight response
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.status_code = 204
        return response

    try:
        data = request.get_json(force=True)

        label = data.get("label")
        t_from = data.get("from")
        t_to = data.get("to")

        missing = [k for k in ("label", "from", "to") if data.get(k) is None]
        if missing:
            msg = f"Missing fields: {', '.join(missing)}"
            print(f"[{datetime.datetime.utcnow().isoformat()}] ❌ {msg}")
            response = jsonify({"error": msg})
            response.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
            return response, 400

        print(f"[{datetime.datetime.utcnow().isoformat()}] ✅ Trigger received:")
        print(f"  label: {label}")
        print(f"  from:  {t_from}")
        print(f"  to:    {t_to}")

        response = jsonify({"status": "✅ Triggered successfully."})
        response.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        return response

    except Exception as e:
        msg = f"Exception: {str(e)}"
        print(f"[{datetime.datetime.utcnow().isoformat()}] ❌ {msg}")
        response = jsonify({"error": msg})
        response.headers["Access-Control-Allow-Origin"] = "https://soazcomms.github.io"
        return response, 500

@app.route("/")
def index():
    return "✅ DSN Webhook is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
