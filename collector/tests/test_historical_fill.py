from datetime import UTC, date, datetime

import httpx
import respx

from mymon_collector import historical_fill as hf
from mymon_collector.source import Ctx


def _ctx(cities):
    return Ctx(http=httpx.Client(), cfg={"cities": cities, "env": {}},
               now=datetime(2026, 9, 16, tzinfo=UTC))


@respx.mock
def test_tcmb_daily_skips_non_200_and_parses_hits():
    xml_ok = (
        '<Tarih_Date Tarih="02.01.2026" Date="01/02/2026">'
        '<Currency CurrencyCode="USD"><Unit>1</Unit><ForexSelling>42.10</ForexSelling></Currency>'
        "</Tarih_Date>"
    )
    respx.get("https://www.tcmb.gov.tr/kurlar/202601/02012026.xml").mock(
        return_value=httpx.Response(200, content=xml_ok.encode())
    )
    respx.get("https://www.tcmb.gov.tr/kurlar/202601/03012026.xml").mock(
        return_value=httpx.Response(404)
    )
    rows = hf.tcmb_daily(_ctx([]), date(2026, 1, 2), date(2026, 1, 3))
    assert len(rows) == 1
    assert rows[0]["ts"] == datetime(2026, 1, 2, tzinfo=UTC)
    assert rows[0]["base"] == "USD"
    assert rows[0]["quote"] == "TRY"
    assert rows[0]["source"] == "tcmb"
    assert float(rows[0]["rate"]) == 42.10


@respx.mock
def test_kp_history_parses_gfz_shape():
    respx.get("https://kp.gfz-potsdam.de/app/json/").mock(
        return_value=httpx.Response(200, json={
            "Kp": [2.0, 3.333, None],
            "datetime": ["2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z", "2026-01-01T06:00:00Z"],
        })
    )
    rows = hf.kp_history(_ctx([]), date(2026, 1, 1), date(2026, 1, 1))
    assert len(rows) == 2  # the null Kp entry is dropped
    assert rows[0]["ts"] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert rows[0]["kp"] == 2.0
    assert rows[0]["solar_wind_speed"] is None


@respx.mock
def test_weather_hourly_merges_weather_and_air_quality():
    weather_payload = [{
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [1.0, 2.0],
            "apparent_temperature": [-1.0, 0.0],
            "relative_humidity_2m": [80, 81],
            "wind_speed_10m": [10, 11],
            "wind_direction_10m": [90, 95],
            "surface_pressure": [1010, 1011],
            "precipitation": [0, 0.1],
            "cloud_cover": [20, 30],
            "weather_code": [1, 2],
            "uv_index": [0, 0],
        }
    }]
    aq_payload = [{
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "european_aqi": [15, 16],
            "pm2_5": [5.0, 5.5],
            "pm10": [8.0, 8.5],
        }
    }]
    respx.get("https://archive-api.open-meteo.com/v1/archive").mock(
        return_value=httpx.Response(200, json=weather_payload)
    )
    respx.get("https://air-quality-api.open-meteo.com/v1/air-quality").mock(
        return_value=httpx.Response(200, json=aq_payload)
    )
    cities = [{"name": "Istanbul", "lat": 41.0, "lon": 29.0}]
    rows = hf.weather_hourly(_ctx(cities), date(2026, 1, 1), date(2026, 1, 1))
    assert len(rows) == 2
    assert rows[0]["city"] == "Istanbul"
    assert rows[0]["temp_c"] == 1.0
    assert rows[0]["aqi_eu"] == 15
    assert rows[1]["pm2_5"] == 5.5


@respx.mock
def test_weather_hourly_survives_aq_failure():
    weather_payload = [{
        "hourly": {"time": ["2026-01-01T00:00"], "temperature_2m": [1.0],
                   "apparent_temperature": [1.0], "relative_humidity_2m": [1],
                   "wind_speed_10m": [1], "wind_direction_10m": [1], "surface_pressure": [1],
                   "precipitation": [0], "cloud_cover": [0], "weather_code": [0], "uv_index": [0]}
    }]
    respx.get("https://archive-api.open-meteo.com/v1/archive").mock(
        return_value=httpx.Response(200, json=weather_payload)
    )
    respx.get("https://air-quality-api.open-meteo.com/v1/air-quality").mock(
        return_value=httpx.Response(500)
    )
    cities = [{"name": "Istanbul", "lat": 41.0, "lon": 29.0}]
    rows = hf.weather_hourly(_ctx(cities), date(2026, 1, 1), date(2026, 1, 1))
    assert len(rows) == 1
    assert rows[0]["aqi_eu"] is None


@respx.mock
def test_fuel_tr_wayback_parses_archived_snapshot():
    cdx_body = [["timestamp", "statuscode"], ["20260116172211", "200"]]
    respx.get("http://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=cdx_body)
    )
    page_html = """
    <table class="table-prices">
      <thead><tr><th>Sehir</th><th>V/Max Kursunsuz 95</th><th>V/Max Diesel</th>
      <th>PO/gaz Otogaz</th></tr></thead>
      <tbody>
        <tr class="price-row" data-disctrict-name="ISTANBUL (AVRUPA)">
          <td>ISTANBUL (AVRUPA)</td>
          <td><span class="with-tax">54.90</span></td>
          <td><span class="with-tax">54.82</span></td>
          <td><span class="with-tax">30.00</span></td>
        </tr>
      </tbody>
    </table>
    """
    # PROVINCES loops over all three cities; the same fixture page (an Istanbul-labeled
    # row) is served for all of them since Ankara/Izmir pass prefer=None and just take the
    # first row regardless of its district label — only the Istanbul rows are asserted on.
    respx.get(url__regex=r"http://web\.archive\.org/web/.*id_/.*akaryakit-fiyatlari.*").mock(
        return_value=httpx.Response(200, text=page_html)
    )
    rows = hf.fuel_tr_wayback(_ctx([]), date(2026, 1, 1), date(2026, 1, 31))
    istanbul_rows = [r for r in rows if r["region"] == "Istanbul"]
    assert {r["fuel_type"]: r["price"] for r in istanbul_rows} == {
        "petrol95": 54.90, "diesel": 54.82, "lpg": 30.00,
    }
    assert all(r["source"] == "petrolofisi_wayback" for r in istanbul_rows)
    assert all(r["period_date"] == date(2026, 1, 16) for r in istanbul_rows)
