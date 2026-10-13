import pytest

from pricing.core import NoCompsError, compute_price, iqr_filter, median


def test_median_odd_and_even():
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_iqr_filter_removes_accessories_and_outliers():
    headphones = [180.0, 190.0, 195.0, 200.0, 205.0, 210.0, 220.0]
    accessories = [12.0, 15.0]
    bundle = [650.0]
    assert iqr_filter(headphones + accessories + bundle) == sorted(headphones)


def test_iqr_filter_keeps_small_lists_unchanged():
    assert iqr_filter([10.0, 50.0, 90.0]) == [10.0, 50.0, 90.0]


def test_compute_price_without_new_price():
    result = compute_price([90.0, 100.0, 100.0, 110.0, 100.0], new_price=None)
    # Median 100 → Basis 90 → Angebot 99 → Auto-Annahme round(84.15) = 84
    assert result.active_median == 100.0
    assert result.listing_price == 99
    assert result.auto_accept_price == 84
    assert result.cap_applied is False
    assert result.warnings == ()


def test_compute_price_new_price_cap_applies():
    result = compute_price([200.0] * 6, new_price=220.0)
    # Basis min(180, 154) = 154 → Angebot round(169.4) = 169 → Auto round(143.65) = 144
    assert result.cap_applied is True
    assert result.listing_price == 169
    assert result.auto_accept_price == 144
    assert any("Neupreis" in w for w in result.warnings)


def test_compute_price_new_price_cap_not_needed():
    result = compute_price([100.0] * 6, new_price=500.0)
    assert result.cap_applied is False
    assert result.listing_price == 99


def test_low_comps_warning():
    result = compute_price([100.0, 100.0, 100.0], new_price=None)
    assert any("wenig Vergleichsdaten" in w for w in result.warnings)


def test_not_worthwhile_warning():
    result = compute_price([4.0, 4.0, 4.0, 4.0, 4.0], new_price=None)
    assert result.listing_price == 4
    assert any("lohnt sich kaum" in w for w in result.warnings)


def test_no_comps_raises():
    with pytest.raises(NoCompsError):
        compute_price([100.0, 110.0], new_price=None)


def test_no_comps_after_filter_raises():
    with pytest.raises(NoCompsError):
        compute_price([], new_price=None)
