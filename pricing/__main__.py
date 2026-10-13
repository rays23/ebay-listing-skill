import argparse
import json
import os
import sys
from collections.abc import Mapping

import httpx

from pricing.browse import BrowseError, fetch_app_token, search_prices
from pricing.core import NoCompsError, compute_price

REQUIRED_ENV = ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET")
HTTP_TIMEOUT_SECONDS = 20


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m pricing")
    parser.add_argument("--query", required=True)
    parser.add_argument("--category-id", required=True)
    parser.add_argument("--condition", choices=["used", "new"], default="used")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--new-price", type=float, default=None)
    return parser.parse_args(argv)


def main(argv: list[str], env: Mapping[str, str], client: httpx.Client) -> int:
    args = _parse(argv)
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        print(f"Fehlende Umgebungsvariablen: {', '.join(missing)} (siehe README, Abschnitt Secrets)", file=sys.stderr)
        return 1
    try:
        token = fetch_app_token(client, env["EBAY_CLIENT_ID"], env["EBAY_CLIENT_SECRET"])
        prices, candidate_count = search_prices(
            client, token, args.query, args.category_id, args.condition, tuple(args.exclude)
        )
        result = compute_price(prices, args.new_price)
    except NoCompsError as exc:
        print(f"NO_COMPS: {exc}", file=sys.stderr)
        return 2
    except BrowseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"Netzwerkfehler bei eBay: {type(exc).__name__}", file=sys.stderr)
        return 1
    except (KeyError, ValueError):
        print("Unerwartete Antwort von eBay", file=sys.stderr)
        return 1
    print(json.dumps({
        "query": args.query,
        "category_id": args.category_id,
        "candidate_count": candidate_count,
        "active_count": result.active_count,
        "active_median": result.active_median,
        "new_price": result.new_price,
        "cap_applied": result.cap_applied,
        "listing_price": result.listing_price,
        "auto_accept_price": result.auto_accept_price,
        "warnings": list(result.warnings),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
        sys.exit(main(sys.argv[1:], os.environ, http_client))
