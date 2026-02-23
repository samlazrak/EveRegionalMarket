import sys
import requests

ESI_BASE = "https://esi.evetech.net/latest"
HEADERS = {"User-Agent": "simple-eve-cli/1.0"}

JITA_SYSTEM_ID = 30000142
THE_FORGE_REGION_ID = 10000002


def esi_get(endpoint, params=None):
    url = f"{ESI_BASE}{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def get_system_id(system_name):
    response = requests.post(
        f"{ESI_BASE}/universe/ids/",
        headers=HEADERS,
        json=[system_name]
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("systems"):
        raise ValueError(f"System not found: {system_name}")

    return data["systems"][0]["id"]


def get_region_id_from_system(system_id):
    system_info = esi_get(f"/universe/systems/{system_id}/")
    constellation_id = system_info["constellation_id"]

    constellation_info = esi_get(f"/universe/constellations/{constellation_id}/")
    return constellation_info["region_id"]


def get_type_id(item_name):
    response = requests.post(
        f"{ESI_BASE}/universe/ids/",
        headers=HEADERS,
        json=[item_name]
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("inventory_types"):
        raise ValueError(f"Item not found: {item_name}")
    return data["inventory_types"][0]["id"]


def get_lowest_sell(region_id, type_id):
    page = 1
    lowest = None

    while True:
        try:
            orders = esi_get(
                f"/markets/{region_id}/orders/",
                params={
                    "order_type": "sell",
                    "type_id": type_id,
                    "page": page
                }
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                break
            raise

        if not orders:
            break

        for order in orders:
            price = order["price"]
            if lowest is None or price < lowest:
                lowest = price

        page += 1

    return lowest


def main():
    if len(sys.argv) < 3:
        print("Usage: python market_api_poc.py <system_name> <item_name>")
        sys.exit(1)

    system_name = sys.argv[1]
    item_name = " ".join(sys.argv[2:])

    print(f"Resolving system: {system_name}")
    system_id = get_system_id(system_name)
    region_id = get_region_id_from_system(system_id)

    print(f"Resolving item: {item_name}")
    type_id = get_type_id(item_name)

    print("Fetching lowest sell in target region...")
    region_price = get_lowest_sell(region_id, type_id)

    print("Fetching lowest sell in Jita (The Forge)...")
    jita_price = get_lowest_sell(THE_FORGE_REGION_ID, type_id)

    if region_price is None:
        print("No sell orders found in target region.")
        return

    if jita_price is None:
        print("No sell orders found in Jita.")
        return

    print("\n--- Result ---")
    print(f"Lowest sell in region: {region_price:,.2f} ISK")
    print(f"Lowest sell in Jita:   {jita_price:,.2f} ISK")

    diff = region_price - jita_price
    pct = (diff / jita_price) * 100

    print(f"Difference: {diff:,.2f} ISK ({pct:.2f}%)")

    if pct < 0:
        print("Cheaper than Jita. Potential buy opportunity.")
    else:
        print("More expensive than Jita. Potential sell opportunity.")


if __name__ == "__main__":
    main()