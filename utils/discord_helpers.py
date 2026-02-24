import os

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import requests

DISCORD_API = "https://discord.com/api/v10"


def verify_signature(raw_body: bytes, signature: str, timestamp: str) -> bool:
    """Verify a Discord interaction request using Ed25519."""
    public_key = os.environ["DISCORD_BOT_PUBLIC_KEY"]
    vk = VerifyKey(bytes.fromhex(public_key))
    try:
        vk.verify(timestamp.encode() + raw_body, bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False


def edit_original_response(app_id: str, token: str, json_payload: dict):
    """PATCH the original deferred response with final content."""
    url = f"{DISCORD_API}/webhooks/{app_id}/{token}/messages/@original"
    resp = requests.patch(url, json=json_payload)
    resp.raise_for_status()
    return resp.json()
