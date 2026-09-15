from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from mymon_collector.sources import energy_prices_eu as ep
from tests.conftest import fixture_json

PK = {"period_date", "country_iso3", "indicator", "source"}
COLS = PK | {"value", "unit"}

ELEC_RE = r"https://ec\.europa\.eu/eurostat/api/dissemination/statistics/1\.0/data/nrg_pc_204\?.*"
GAS_RE = r"https://ec\.europa\.eu/eurostat/api/dissemination/statistics/1\.0/data/nrg_pc_202\?.*"


def _mock_both():
    elec = respx.get(url__regex=ELEC_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("energy_prices_eu_nrg_pc_204.json"))
    )
    gas = respx.get(url__regex=GAS_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("energy_prices_eu_nrg_pc_202.json"))
    )
    return elec, gas


def _find(rows, iso3, indicator, period):
    return next(
        r
        for r in rows
        if r["country_iso3"] == iso3 and r["indicator"] == indicator and r["period_date"] == period
    )


def test_source_metadata():
    assert ep.SOURCE.name == "energy_prices_eu"
    assert ep.SOURCE.interval == 86400
    assert ep.SOURCE.tables == ["price_index"]
    assert ep.SOURCE.backfill is None
    assert ep.SOURCE.requires_env == []


@respx.mock
def test_fetch_decodes_both_datasets(ctx):
    elec, gas = _mock_both()
    out = ep.fetch(ctx)
    assert elec.called and gas.called
    assert "nrg_cons=KWH2500-4999" in str(elec.calls[0].request.url)
    assert "nrg_cons=GJ20-199" in str(gas.calls[0].request.url)
    assert [t for t, _ in out] == ["price_index"]
    rows = out[0][1]
    assert all(set(r) == COLS for r in rows)
    assert all(r[k] is not None for r in rows for k in PK)

    # electricity fixture: 7 geos x 3 semesters, UK absent -> 18; gas: 6 geos, UK absent -> 15
    elec_rows = [r for r in rows if r["indicator"] == "electricity_household_eur_kwh"]
    gas_rows = [r for r in rows if r["indicator"] == "gas_household_eur_kwh"]
    assert len(elec_rows) == 18
    assert len(gas_rows) == 15
    assert len(rows) == 33
    assert {r["source"] for r in rows} == {"eurostat"}
    assert {r["unit"] for r in rows} == {"EUR/kWh"}
    assert {r["country_iso3"] for r in elec_rows} == {"EUU", "EMU", "DEU", "GRC", "TUR", "XKX"}

    de = _find(rows, "DEU", "electricity_household_eur_kwh", date(2024, 1, 1))
    assert de["value"] == pytest.approx(0.3951)
    gr = _find(rows, "GRC", "electricity_household_eur_kwh", date(2023, 7, 1))
    assert gr["value"] == pytest.approx(0.2309)
    eu = _find(rows, "EUU", "gas_household_eur_kwh", date(2024, 7, 1))
    assert eu["value"] == pytest.approx(0.1244)
    tr = _find(rows, "TUR", "gas_household_eur_kwh", date(2024, 1, 1))
    assert tr["value"] == pytest.approx(0.0163)


@respx.mock
def test_one_dataset_failing_keeps_other(ctx):
    respx.get(url__regex=ELEC_RE).mock(return_value=httpx.Response(500))
    respx.get(url__regex=GAS_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("energy_prices_eu_nrg_pc_202.json"))
    )
    rows = ep.fetch(ctx)[0][1]
    assert {r["indicator"] for r in rows} == {"gas_household_eur_kwh"}


@respx.mock
def test_both_failing_raises(ctx):
    respx.get(url__regex=ELEC_RE).mock(return_value=httpx.Response(500))
    respx.get(url__regex=GAS_RE).mock(
        return_value=httpx.Response(200, json={"error": [{"label": "bad request"}]})
    )
    with pytest.raises(RuntimeError):
        ep.fetch(ctx)


def test_jsonstat_rows_decodes_row_major_order():
    payload = {
        "id": ["a", "geo", "time"],
        "size": [1, 2, 3],
        "dimension": {
            "a": {"category": {"index": {"x": 0}}},
            "geo": {"category": {"index": {"DE": 0, "FR": 1}}},
            "time": {"category": {"index": ["2023-S1", "2023-S2", "2024-S1"]}},
        },
        "value": {"0": 1.0, "2": 3.0, "4": 5.0, "5": None},
    }
    cells = list(ep.jsonstat_rows(payload))
    assert cells == [
        ({"a": "x", "geo": "DE", "time": "2023-S1"}, 1.0),
        ({"a": "x", "geo": "DE", "time": "2024-S1"}, 3.0),
        ({"a": "x", "geo": "FR", "time": "2023-S2"}, 5.0),
    ]


def test_jsonstat_rows_rejects_non_jsonstat():
    with pytest.raises(ValueError):
        list(ep.jsonstat_rows({"error": "nope"}))


def test_period_parsing():
    assert ep._period("2024-S1") == date(2024, 1, 1)
    assert ep._period("2024-S2") == date(2024, 7, 1)
    assert ep._period("2024") == date(2024, 1, 1)
    assert ep._period("2024-03") == date(2024, 3, 1)
    assert ep._period("2024-Q3") == date(2024, 7, 1)
    assert ep._period("junk") is None


def test_unknown_geo_and_zero_prices_skipped():
    payload = {
        "id": ["geo", "time"],
        "size": [3, 1],
        "dimension": {
            "geo": {"category": {"index": {"DE": 0, "ZZ": 1, "AL": 2}}},
            "time": {"category": {"index": {"2021-S1": 0}}},
        },
        "value": {"0": 0.2, "1": 0.3, "2": 0.0},
    }
    rows = ep._dataset_rows(payload, "gas_household_eur_kwh")
    assert [(r["country_iso3"], r["value"]) for r in rows] == [("DEU", 0.2)]
