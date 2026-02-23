import os
import discord
from discord import app_commands
import aiohttp
from dotenv import load_dotenv

load_dotenv()

ESI_BASE = "https://esi.evetech.net/latest"
HEADERS = {"User-Agent": "eve-wh-market-bot/1.0"}
JITA_SYSTEM_ID = 30000142
THE_FORGE_REGION_ID = 10000002


class MarketBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(headers=HEADERS)
        await self.tree.sync()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


bot = MarketBot()


# --- ESI helpers ---

async def esi_get(endpoint: str, params: dict | None = None) -> dict | list:
    url = f"{ESI_BASE}{endpoint}"
    async with bot.session.get(url, params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


async def esi_post(endpoint: str, json_body) -> dict:
    url = f"{ESI_BASE}{endpoint}"
    async with bot.session.post(url, json=json_body) as resp:
        resp.raise_for_status()
        return await resp.json()


async def resolve_system_id(system_name: str) -> tuple[int, str]:
    data = await esi_post("/universe/ids/", [system_name])
    systems = data.get("systems")
    if not systems:
        raise ValueError(f"System not found: **{system_name}**")
    return systems[0]["id"], systems[0]["name"]


async def resolve_type_id(item_name: str) -> tuple[int, str]:
    data = await esi_post("/universe/ids/", [item_name])
    types = data.get("inventory_types")
    if not types:
        raise ValueError(f"Item not found: **{item_name}**")
    return types[0]["id"], types[0]["name"]


async def get_region_for_system(system_id: int) -> tuple[int, str]:
    system_info = await esi_get(f"/universe/systems/{system_id}/")
    constellation_id = system_info["constellation_id"]
    constellation_info = await esi_get(f"/universe/constellations/{constellation_id}/")
    region_id = constellation_info["region_id"]
    region_info = await esi_get(f"/universe/regions/{region_id}/")
    return region_id, region_info["name"]


async def get_best_prices(region_id: int, type_id: int, system_id: int) -> dict:
    """Return best prices for system and region, plus location system IDs."""
    page = 1
    result = {
        "sys_buy": None, "sys_sell": None,
        "reg_buy": None, "reg_sell": None,
        "reg_buy_system": None, "reg_sell_system": None,
        "reg_buy_vol": 0, "reg_sell_vol": 0,
    }
    while True:
        try:
            orders = await esi_get(
                f"/markets/{region_id}/orders/",
                params={"order_type": "all", "type_id": type_id, "page": page},
            )
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                break
            raise
        if not orders:
            break
        for order in orders:
            price = order["price"]
            vol = order["volume_remain"]
            in_system = order["system_id"] == system_id
            if order["is_buy_order"]:
                if result["reg_buy"] is None or price > result["reg_buy"]:
                    result["reg_buy"] = price
                    result["reg_buy_system"] = order["system_id"]
                    result["reg_buy_vol"] = vol
                if in_system and (result["sys_buy"] is None or price > result["sys_buy"]):
                    result["sys_buy"] = price
            else:
                if result["reg_sell"] is None or price < result["reg_sell"]:
                    result["reg_sell"] = price
                    result["reg_sell_system"] = order["system_id"]
                    result["reg_sell_vol"] = vol
                if in_system and (result["sys_sell"] is None or price < result["sys_sell"]):
                    result["sys_sell"] = price
        page += 1
    return result


async def get_jumps(origin: int, destination: int) -> int | None:
    """Return number of jumps between two k-space systems, or None."""
    if origin == destination:
        return 0
    try:
        route = await esi_get(f"/route/{origin}/{destination}/")
        return len(route) - 1
    except aiohttp.ClientResponseError:
        return None


async def get_system_name(system_id: int) -> str:
    info = await esi_get(f"/universe/systems/{system_id}/")
    return info["name"]


async def get_type_volume(type_id: int) -> float:
    info = await esi_get(f"/universe/types/{type_id}/")
    return info.get("volume", 0.0)


def format_isk(value: float) -> str:
    return f"{value:,.2f} ISK"


# --- Slash commands ---

@bot.tree.command(name="price", description="Show buy/sell prices for an item in a system vs Jita")
@app_commands.describe(
    system="K-space system name (e.g. Amarr, Dodixie, Hek)",
    item="Item name (e.g. Tritanium, Ishtar, Large Shield Extender II)",
)
async def price(interaction: discord.Interaction, system: str, item: str):
    await interaction.response.defer()

    try:
        system_id, system_name = await resolve_system_id(system)
        type_id, type_name = await resolve_type_id(item)
        region_id, region_name = await get_region_for_system(system_id)

        reg = await get_best_prices(region_id, type_id, system_id)
        jita = await get_best_prices(THE_FORGE_REGION_ID, type_id, JITA_SYSTEM_ID)
        volume = await get_type_volume(type_id)
        jita_jumps = await get_jumps(system_id, JITA_SYSTEM_ID)

        embed = discord.Embed(title=type_name, color=0x00b0f4)
        embed.description = f"**Volume:** {volume:,.2f} m\u00b3"
        embed.set_footer(text="Data from EVE ESI")

        def price_line(sell: float | None, buy: float | None) -> str:
            s = format_isk(sell) if sell is not None else "No orders"
            b = format_isk(buy) if buy is not None else "No orders"
            return f"**Sell:** {s}\n**Buy:** {b}"

        embed.add_field(
            name=f"{system_name} (system)",
            value=price_line(reg["sys_sell"], reg["sys_buy"]),
            inline=True,
        )

        # Region field with jump info and volume for best orders
        reg_lines = []
        if reg["reg_sell"] is not None:
            jumps = await get_jumps(system_id, reg["reg_sell_system"])
            loc = await get_system_name(reg["reg_sell_system"])
            j = f" ({jumps}j)" if jumps is not None else ""
            reg_lines.append(
                f"**Sell:** {format_isk(reg['reg_sell'])}\n"
                f"  {loc}{j} \u2022 {reg['reg_sell_vol']:,} units"
            )
        else:
            reg_lines.append("**Sell:** No orders")
        if reg["reg_buy"] is not None:
            jumps = await get_jumps(system_id, reg["reg_buy_system"])
            loc = await get_system_name(reg["reg_buy_system"])
            j = f" ({jumps}j)" if jumps is not None else ""
            reg_lines.append(
                f"**Buy:** {format_isk(reg['reg_buy'])}\n"
                f"  {loc}{j} \u2022 {reg['reg_buy_vol']:,} units"
            )
        else:
            reg_lines.append("**Buy:** No orders")

        embed.add_field(
            name=f"{region_name} (region)",
            value="\n".join(reg_lines),
            inline=True,
        )

        jita_j = f" ({jita_jumps}j)" if jita_jumps is not None else ""
        embed.add_field(
            name=f"Jita{jita_j}",
            value=price_line(jita["reg_sell"], jita["reg_buy"]),
            inline=True,
        )

        # Comparison vs Jita (region price - Jita price)
        lines = []
        if reg["reg_sell"] is not None and jita["reg_sell"] is not None:
            diff = reg["reg_sell"] - jita["reg_sell"]
            pct = (diff / jita["reg_sell"]) * 100
            sign = "+" if diff >= 0 else ""
            lines.append(f"Sell: {sign}{format_isk(diff)} ({sign}{pct:.1f}%)")
        if reg["reg_buy"] is not None and jita["reg_buy"] is not None:
            diff = reg["reg_buy"] - jita["reg_buy"]
            pct = (diff / jita["reg_buy"]) * 100
            sign = "+" if diff >= 0 else ""
            lines.append(f"Buy: {sign}{format_isk(diff)} ({sign}{pct:.1f}%)")

        if lines:
            embed.add_field(
                name=f"{region_name} vs Jita",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    except ValueError as e:
        await interaction.followup.send(str(e))
    except Exception as e:
        await interaction.followup.send(f"ESI error: {e}")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
