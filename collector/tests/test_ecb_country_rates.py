from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import ecb_country_rates as ecr

CSV_HEADER = "KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\n"


def csv_body(rows):
    body = CSV_HEADER
    for period, value in rows:
        body += f"X,M,XX,{period},{value}\n"
    return body


@respx.mock
def test_bond_yield_rows_for_maps_to_iso3():
    respx.get("https://data-api.ecb.europa.eu/service/data/IRS/M.IT.L.L40.CI.0000.EUR.N.Z").mock(
        return_value=httpx.Response(200, text=csv_body([("2026-07", 3.881), ("2026-08", 3.986)]))
    )
    fetch_fn = ecr._bond_yield_rows_for("IT", "ITA")
    rows = fetch_fn(_ctx())
    assert len(rows) == 2
    assert all(r["country_iso3"] == "ITA" and r["indicator"] == "gov_bond_10y_pct" for r in rows)
    latest = max(rows, key=lambda r: r["period_date"])
    assert latest["value"] == 3.986
    assert latest["period_date"] == date(2026, 8, 1)


@respx.mock
def test_bank_rate_rows_for_covers_all_three_series():
    csv = csv_body([("2026-08", 3.5)])
    for suffix in ecr.MIR_SUFFIXES.values():
        respx.get(f"https://data-api.ecb.europa.eu/service/data/MIR/M.GR.B.{suffix}.EUR.N").mock(
            return_value=httpx.Response(200, text=csv)
        )
    fetch_fn = ecr._bank_rate_rows_for("GR", "GRC")
    rows = fetch_fn(_ctx())
    indicators = {r["indicator"] for r in rows}
    assert indicators == set(ecr.MIR_SUFFIXES)
    assert all(r["country_iso3"] == "GRC" for r in rows)


def test_countries_excludes_turkey():
    assert "TR" not in ecr.COUNTRIES
    assert ecr.COUNTRIES["GR"] == "GRC"


@respx.mock
def test_fetch_survives_one_country_failing():
    csv = csv_body([("2026-08", 3.0)])
    for ecb_cc in ecr.COUNTRIES:
        url_bond = f"https://data-api.ecb.europa.eu/service/data/IRS/M.{ecb_cc}.L.L40.CI.0000.EUR.N.Z"
        if ecb_cc == "DE":
            respx.get(url_bond).mock(return_value=httpx.Response(500))
        else:
            respx.get(url_bond).mock(return_value=httpx.Response(200, text=csv))
        for suffix in ecr.MIR_SUFFIXES.values():
            respx.get(
                f"https://data-api.ecb.europa.eu/service/data/MIR/M.{ecb_cc}.B.{suffix}.EUR.N"
            ).mock(return_value=httpx.Response(200, text=csv))
    table, rows = ecr.fetch(_ctx())[0]
    assert table == "price_index"
    assert not any(r["country_iso3"] == "DEU" and r["indicator"] == "gov_bond_10y_pct"
                   for r in rows)
    assert any(r["country_iso3"] == "ITA" and r["indicator"] == "gov_bond_10y_pct"
               for r in rows)


def _ctx():
    return ecr.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))
