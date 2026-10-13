import httpx

from pricing.match import title_matches

API_BASE = "https://api.ebay.com"
MARKETPLACE_ID = "EBAY_DE"
CURRENCY = "EUR"
SEARCH_LIMIT = 100
APP_SCOPE = "https://api.ebay.com/oauth/api_scope"
# conditions:{USED} liefert laut Doku nur die grobe Einstufung, deshalb explizite IDs.
# 7000 (Defekt/Ersatzteile) und Refurbished (2000-2500) bewusst ausgeschlossen.
CONDITION_IDS = {
    "used": "2750|2990|3000|3010|4000|5000|6000",
    "new": "1000|1500|1750",
}


class BrowseError(Exception):
    pass


def fetch_app_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    response = client.post(
        f"{API_BASE}/identity/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": APP_SCOPE},
    )
    if response.status_code != 200:
        raise BrowseError(f"Token-Abruf fehlgeschlagen (HTTP {response.status_code})")
    return response.json()["access_token"]


def _eur_price(item: dict) -> float | None:
    price = item.get("price") or {}
    if price.get("currency") != CURRENCY or "value" not in price:
        return None
    return float(price["value"])


def search_prices(
    client: httpx.Client,
    token: str,
    query: str,
    category_id: str,
    condition: str,
    exclude: tuple[str, ...] = (),
) -> tuple[list[float], int]:
    if condition not in CONDITION_IDS:
        raise ValueError(f"condition muss used oder new sein, nicht {condition!r}")
    filters = ",".join([
        "buyingOptions:{FIXED_PRICE}",
        f"conditionIds:{{{CONDITION_IDS[condition]}}}",
        "itemLocationCountry:DE",
    ])
    response = client.get(
        f"{API_BASE}/buy/browse/v1/item_summary/search",
        params={"q": query, "category_ids": category_id, "filter": filters, "limit": str(SEARCH_LIMIT)},
        headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE_ID},
    )
    if response.status_code != 200:
        raise BrowseError(f"Browse-Suche fehlgeschlagen (HTTP {response.status_code})")
    items = response.json().get("itemSummaries", [])
    priced = [(item, price) for item in items if (price := _eur_price(item)) is not None]
    matching = [
        price for item, price in priced
        if item.get("title") and title_matches(item["title"], query, exclude)
    ]
    return matching, len(priced)
