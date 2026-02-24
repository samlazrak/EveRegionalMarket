"""One-time script to register slash commands with Discord.

Usage:
    python register_commands.py

Requires DISCORD_APP_ID and DISCORD_BOT_TOKEN in .env or environment.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.environ["DISCORD_APP_ID"]
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
URL = f"https://discord.com/api/v10/applications/{APP_ID}/commands"

COMMANDS = [
    {
        "name": "price",
        "description": "Show buy/sell prices for an item in a system vs Jita",
        "type": 1,  # CHAT_INPUT
        "options": [
            {
                "name": "system",
                "description": "K-space system name (e.g. Amarr, Dodixie, Hek)",
                "type": 3,  # STRING
                "required": True,
            },
            {
                "name": "item",
                "description": "Item name (e.g. Tritanium, Ishtar, Large Shield Extender II)",
                "type": 3,  # STRING
                "required": True,
            },
        ],
    },
]

resp = requests.put(
    URL,
    json=COMMANDS,
    headers={"Authorization": f"Bot {BOT_TOKEN}"},
)

if resp.ok:
    print(f"Registered {len(resp.json())} command(s) successfully.")
else:
    print(f"Error {resp.status_code}: {resp.text}")
