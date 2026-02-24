from concurrent.futures import ThreadPoolExecutor

from utils.esi import (
    resolve_system_id, resolve_type_id, get_region_for_system,
    get_best_prices, get_jumps, get_system_name, get_type_volume,
    format_isk, JITA_SYSTEM_ID, THE_FORGE_REGION_ID,
)
from utils.discord_helpers import edit_original_response


def build_price_embed(type_name, volume, system_name, system_id,
                      region_name, reg, jita, jita_jumps):
    """Build a Discord embed dict for price results."""
    embed = {
        "title": type_name,
        "color": 0x00b0f4,
        "description": f"**Volume:** {volume:,.2f} m\u00b3",
        "footer": {"text": "Data from EVE ESI"},
        "fields": [],
    }

    def price_line(sell, buy):
        s = format_isk(sell) if sell is not None else "No orders"
        b = format_isk(buy) if buy is not None else "No orders"
        return f"**Sell:** {s}\n**Buy:** {b}"

    # System field
    embed["fields"].append({
        "name": f"{system_name} (system)",
        "value": price_line(reg["sys_sell"], reg["sys_buy"]),
        "inline": True,
    })

    # Region field with jump info and volume for best orders
    reg_lines = []
    if reg["reg_sell"] is not None:
        jumps = get_jumps(system_id, reg["reg_sell_system"])
        loc = get_system_name(reg["reg_sell_system"])
        j = f" ({jumps}j)" if jumps is not None else ""
        reg_lines.append(
            f"**Sell:** {format_isk(reg['reg_sell'])}\n"
            f"  {loc}{j} \u2022 {reg['reg_sell_vol']:,} units"
        )
    else:
        reg_lines.append("**Sell:** No orders")
    if reg["reg_buy"] is not None:
        jumps = get_jumps(system_id, reg["reg_buy_system"])
        loc = get_system_name(reg["reg_buy_system"])
        j = f" ({jumps}j)" if jumps is not None else ""
        reg_lines.append(
            f"**Buy:** {format_isk(reg['reg_buy'])}\n"
            f"  {loc}{j} \u2022 {reg['reg_buy_vol']:,} units"
        )
    else:
        reg_lines.append("**Buy:** No orders")

    embed["fields"].append({
        "name": f"{region_name} (region)",
        "value": "\n".join(reg_lines),
        "inline": True,
    })

    # Jita field
    jita_j = f" ({jita_jumps}j)" if jita_jumps is not None else ""
    embed["fields"].append({
        "name": f"Jita{jita_j}",
        "value": price_line(jita["reg_sell"], jita["reg_buy"]),
        "inline": True,
    })

    # Comparison vs Jita
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
        embed["fields"].append({
            "name": f"{region_name} vs Jita",
            "value": "\n".join(lines),
            "inline": False,
        })

    return embed


def handle_price_command(system: str, item: str, app_id: str, token: str):
    """Execute the /price command and PATCH the deferred response."""
    try:
        system_id, system_name = resolve_system_id(system)
        type_id, type_name = resolve_type_id(item)
        region_id, region_name = get_region_for_system(system_id)

        # Parallelize independent ESI calls
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_reg = pool.submit(get_best_prices, region_id, type_id, system_id)
            f_jita = pool.submit(get_best_prices, THE_FORGE_REGION_ID, type_id, JITA_SYSTEM_ID)
            f_volume = pool.submit(get_type_volume, type_id)
            f_jumps = pool.submit(get_jumps, system_id, JITA_SYSTEM_ID)

            reg = f_reg.result()
            jita = f_jita.result()
            volume = f_volume.result()
            jita_jumps = f_jumps.result()

        embed = build_price_embed(
            type_name, volume, system_name, system_id,
            region_name, reg, jita, jita_jumps,
        )
        edit_original_response(app_id, token, {"embeds": [embed]})

    except ValueError as e:
        edit_original_response(app_id, token, {"content": str(e)})
    except Exception as e:
        edit_original_response(app_id, token, {"content": f"ESI error: {e}"})
