import requests

ESI_BASE = "https://esi.evetech.net/latest"
HEADERS = {"User-Agent": "eve-wh-market-bot/1.0"}
JITA_SYSTEM_ID = 30000142
THE_FORGE_REGION_ID = 10000002

session = requests.Session()
session.headers.update(HEADERS)


def esi_get(endpoint: str, params: dict | None = None):
    url = f"{ESI_BASE}{endpoint}"
    resp = session.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def esi_post(endpoint: str, json_body):
    url = f"{ESI_BASE}{endpoint}"
    resp = session.post(url, json=json_body)
    resp.raise_for_status()
    return resp.json()


def resolve_system_id(system_name: str) -> tuple[int, str]:
    data = esi_post("/universe/ids/", [system_name])
    systems = data.get("systems")
    if not systems:
        raise ValueError(f"System not found: **{system_name}**")
    return systems[0]["id"], systems[0]["name"]


def resolve_type_id(item_name: str) -> tuple[int, str]:
    data = esi_post("/universe/ids/", [item_name])
    types = data.get("inventory_types")
    if not types:
        raise ValueError(f"Item not found: **{item_name}**")
    return types[0]["id"], types[0]["name"]


def get_region_for_system(system_id: int) -> tuple[int, str]:
    system_info = esi_get(f"/universe/systems/{system_id}/")
    constellation_id = system_info["constellation_id"]
    constellation_info = esi_get(f"/universe/constellations/{constellation_id}/")
    region_id = constellation_info["region_id"]
    region_info = esi_get(f"/universe/regions/{region_id}/")
    return region_id, region_info["name"]


def get_best_prices(region_id: int, type_id: int, system_id: int) -> dict:
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
            orders = esi_get(
                f"/markets/{region_id}/orders/",
                params={"order_type": "all", "type_id": type_id, "page": page},
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
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


def get_jumps(origin: int, destination: int) -> int | None:
    """Return number of jumps between two k-space systems, or None."""
    if origin == destination:
        return 0
    try:
        route = esi_get(f"/route/{origin}/{destination}/")
        return len(route) - 1
    except requests.HTTPError:
        return None


def get_system_name(system_id: int) -> str:
    info = esi_get(f"/universe/systems/{system_id}/")
    return info["name"]


def get_type_volume(type_id: int) -> float:
    info = esi_get(f"/universe/types/{type_id}/")
    return info.get("volume", 0.0)


def format_isk(value: float) -> str:
    return f"{value:,.2f} ISK"
