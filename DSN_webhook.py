from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # more explicit CORS config

@app.route("/DSN_webhook", methods=["POST", "OPTIONS"])
def trigger_analysis():
    if request.method == "OPTIONS":
        # CORS preflight response
        return '', 204

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

        print(f"✅ Trigger received: label={label}, from={t_from}, to={t_to}")

        return jsonify({"status": "✅ Triggered successfully."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
