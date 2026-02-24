import os

from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

from utils.discord_helpers import verify_signature
from utils.price import handle_price_command

app = Flask(__name__)


@app.route("/", methods=["GET"])
@app.route("/api/interactions", methods=["GET"])
def health():
    return "OK", 200


@app.route("/", methods=["POST"])
@app.route("/api/interactions", methods=["POST"])
def interactions():
    # Verify Ed25519 signature
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    raw_body = request.data

    if not verify_signature(raw_body, signature, timestamp):
        return "Invalid signature", 401

    data = request.json

    # PING → PONG
    if data.get("type") == 1:
        return jsonify({"type": 1})

    # APPLICATION_COMMAND
    if data.get("type") == 2:
        command_name = data["data"]["name"]
        app_id = os.environ["DISCORD_APP_ID"]
        token = data["token"]

        if command_name == "price":
            options = {opt["name"]: opt["value"] for opt in data["data"].get("options", [])}
            system = options.get("system", "")
            item = options.get("item", "")

            # Return deferred response, then run ESI work via call_on_close
            # so the function stays alive until the PATCH completes.
            response = jsonify({"type": 5})
            response.call_on_close(
                lambda: handle_price_command(system, item, app_id, token)
            )
            return response

    return "Unknown interaction type", 400
