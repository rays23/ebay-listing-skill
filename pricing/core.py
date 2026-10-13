from dataclasses import dataclass

from pricing import config


class NoCompsError(Exception):
    pass


@dataclass(frozen=True)
class PriceResult:
    active_count: int
    active_median: float
    new_price: float | None
    cap_applied: bool
    listing_price: int
    auto_accept_price: int
    warnings: tuple[str, ...]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _quartiles(ordered: list[float]) -> tuple[float, float]:
    half = len(ordered) // 2
    lower = ordered[:half]
    upper = ordered[half + len(ordered) % 2:]
    return median(lower), median(upper)


def iqr_filter(prices: list[float]) -> list[float]:
    ordered = sorted(prices)
    if len(ordered) < 4:
        return ordered
    q1, q3 = _quartiles(ordered)
    spread = (q3 - q1) * config.IQR_FACTOR
    return [p for p in ordered if q1 - spread <= p <= q3 + spread]


def _round_euro(value: float) -> int:
    return int(value + 0.5)


def compute_price(active_prices: list[float], new_price: float | None) -> PriceResult:
    comps = iqr_filter(active_prices)
    if len(comps) < config.MIN_ACTIVE_COMPS:
        raise NoCompsError(f"nur {len(comps)} vergleichbare Angebote gefunden")

    active_median = median(comps)
    basis = active_median * config.ACTIVE_DISCOUNT
    warnings: list[str] = []

    cap_applied = False
    if new_price is not None:
        cap = new_price * config.NEW_PRICE_CAP_RATIO
        if cap < basis:
            basis = cap
            cap_applied = True
            warnings.append(f"Preis durch Neupreis gedeckelt ({new_price:.0f} € × {config.NEW_PRICE_CAP_RATIO:.0%})")

    listing_price = _round_euro(basis * config.LISTING_MARKUP)
    auto_accept_price = _round_euro(listing_price * config.AUTO_ACCEPT_RATIO)

    if len(comps) < config.LOW_COMPS_WARNING:
        warnings.append(f"wenig Vergleichsdaten ({len(comps)} Angebote)")
    if listing_price < config.MIN_WORTHWHILE_PRICE:
        warnings.append("Verkauf lohnt sich kaum (unter 5 €)")

    return PriceResult(
        active_count=len(comps),
        active_median=active_median,
        new_price=new_price,
        cap_applied=cap_applied,
        listing_price=listing_price,
        auto_accept_price=auto_accept_price,
        warnings=tuple(warnings),
    )
