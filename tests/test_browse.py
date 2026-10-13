import json
from pathlib import Path

import httpx
import pytest

from pricing.browse import BrowseError, fetch_app_token, search_prices

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "browse_response.json").read_text())


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_app_token_sends_basic_auth_and_scope():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})

    assert fetch_app_token(_client(handler), "id", "pw") == "tok"
    assert seen["auth"] == "Basic aWQ6cHc="
    assert "grant_type=client_credentials" in seen["body"]
    assert "api_scope" in seen["body"]


def test_fetch_app_token_error_hides_client_secret():
    def handler(request):
        return httpx.Response(401, json={"error": "invalid_client"})

    with pytest.raises(BrowseError) as exc:
        fetch_app_token(_client(handler), "id", "do-not-leak")
    assert "do-not-leak" not in str(exc.value)
    assert "401" in str(exc.value)


def test_search_prices_filters_currency_and_missing_price():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        seen["marketplace"] = request.headers["x-ebay-c-marketplace-id"]
        return httpx.Response(200, json=FIXTURE)

    prices, candidate_count = search_prices(_client(handler), "tok", "sony wh-1000xm4", "112529", "used")
    assert prices == [189.0, 205.5, 210.0]
    assert candidate_count == 3
    assert seen["marketplace"] == "EBAY_DE"
    params = seen["url"].params
    assert params["q"] == "sony wh-1000xm4"
    assert params["category_ids"] == "112529"
    assert params["limit"] == "100"
    assert "buyingOptions:{FIXED_PRICE}" in params["filter"]
    assert "conditionIds:{2750|2990|3000|3010|4000|5000|6000}" in params["filter"]
    assert "7000" not in params["filter"]
    assert "itemLocationCountry:DE" in params["filter"]


def test_search_prices_empty_result():
    def handler(request):
        return httpx.Response(200, json={"total": 0})

    assert search_prices(_client(handler), "tok", "x", "1", "new") == ([], 0)


def test_search_prices_http_error():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(BrowseError):
        search_prices(_client(handler), "tok", "x", "1", "used")


def test_search_prices_rejects_unknown_condition():
    with pytest.raises(ValueError):
        search_prices(_client(lambda r: httpx.Response(200, json={})), "tok", "x", "1", "kaputt")


def _titled(items):
    def handler(request):
        return httpx.Response(200, json={"itemSummaries": items})

    return _client(handler)


def _item(title, value="100.00", currency="EUR"):
    item = {"price": {"value": value, "currency": currency}}
    if title is not None:
        item["title"] = title
    return item


def test_search_prices_title_filter_counts_candidates_before_filter():
    client = _titled([_item("Sony WH-1000XM4"), _item("Sony WH-1000XM3", "80"), _item("Sony WH-1000XM4", "90", "CHF")])
    prices, candidate_count = search_prices(client, "tok", "sony wh-1000xm4", "1", "used")
    assert prices == [100.0]
    assert candidate_count == 2


def test_search_prices_drops_items_without_title():
    prices, candidate_count = search_prices(_titled([_item(None), _item("Sony WH-1000XM4")]), "tok", "sony wh-1000xm4", "1", "used")
    assert prices == [100.0]
    assert candidate_count == 2


def test_search_prices_applies_exclude():
    client = _titled([_item("Sabrent Rocket Nano 1TB"), _item("Sabrent Rocket 1TB", "50")])
    prices, _ = search_prices(client, "tok", "Sabrent Rocket 1TB", "1", "used", exclude=("Nano",))
    assert prices == [50.0]
