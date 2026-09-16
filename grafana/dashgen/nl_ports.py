from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, target, timeseries, write
from _nl_common import nl, nl_multi

PORT_CARGO_LATEST = """
SELECT DISTINCT ON (m.port_code) p.name AS "Port", p.lat, p.lon,
       m.value AS "Cargo, 1000t", m.period_date AS "Period"
FROM port_metric m JOIN port p ON p.code = m.port_code
WHERE m.indicator='cargo_1000t' AND m.source='cbs'
ORDER BY m.port_code, m.period_date DESC
"""

PORT_CARGO_TREND = """
SELECT m.period_date AS time, p.name AS metric, m.value
FROM port_metric m JOIN port p ON p.code = m.port_code
WHERE m.indicator='cargo_1000t' AND m.source='cbs' AND $__timeFilter(m.period_date)
ORDER BY 1
"""

PORT_SHIPS_TREND = """
SELECT m.period_date AS time, p.name AS metric, m.value
FROM port_metric m JOIN port p ON p.code = m.port_code
WHERE m.indicator='ship_calls' AND m.source='cbs' AND $__timeFilter(m.period_date)
ORDER BY 1
"""

CONTAINERS = nl("containers_1000teu", "cbs")

FREIGHT_BY_MODE = """
SELECT period_date AS time,
       regexp_replace(indicator, '^freight_total_mt_', '') AS metric, value
FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator LIKE 'freight_total_mt_%'
  AND $__timeFilter(period_date)
ORDER BY 1
"""

_PORTS = ["Rotterdam", "Amsterdam", "Groningen Seaports", "Zeeland Seaports"]
PORT_COLORS = {name: CAT[i % len(CAT)] for i, name in enumerate(_PORTS)}
MODE_COLORS = {
    "road": CAT[0], "rail": CAT[1], "inland_waterway": CAT[2],
    "sea": CAT[3], "pipeline": CAT[4], "air": CAT[5],
}

panels = [
    stat("Rotterdam cargo, latest quarter", 0, 0, 6, 4,
         "SELECT value FROM port_metric WHERE port_code='A041797' AND indicator='cargo_1000t' "
         "AND source='cbs' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[0],
         description="1000 tonnes. Rotterdam alone handles roughly 10x Amsterdam's tonnage."),
    stat("Container throughput, national", 6, 0, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='containers_1000teu' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[3]),
    stat("Ship calls, Rotterdam", 12, 0, 6, 4,
         "SELECT value FROM port_metric WHERE port_code='A041797' AND indicator='ship_calls' "
         "AND source='cbs' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[2], description="Annual."),
    stat("Road freight, national", 18, 0, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='freight_total_mt_road' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[0]),

    geomap("Cargo by port, latest quarter", 0, 4, 14, 13,
           [marker_layer("Ports", "A", size_field="Cargo, 1000t", color_field="Cargo, 1000t",
                         size=(10, 36), color_scheme="continuous-BlPu", opacity=0.85,
                         text_field="Port")],
           targets=[target(PORT_CARGO_LATEST, "A", "table")],
           view={"id": "coords", "lat": 52.1, "lon": 5.0, "zoom": 7.0, "allLayers": True},
           description="CBS 85598NED, gross cargo tonnage per Dutch seaport."),
    barchart("Cargo by port, ranked", 14, 4, 10, 13,
             "SELECT p.name AS \"Port\", m.value AS \"Cargo, 1000t\" FROM port_metric m "
             "JOIN port p ON p.code=m.port_code WHERE m.indicator='cargo_1000t' "
             "AND m.source='cbs' AND m.period_date=(SELECT max(period_date) FROM port_metric "
             "WHERE indicator='cargo_1000t' AND source='cbs') ORDER BY m.value DESC",
             unit="short", color=CAT[0]),

    timeseries("Cargo tonnage by port, quarterly", 0, 17, 24, 9, PORT_CARGO_TREND, unit="short",
               decimals=0, colors=PORT_COLORS, fill=0, legend="right"),

    timeseries("Ship calls by port, annual", 0, 26, 12, 9, PORT_SHIPS_TREND, unit="short",
               decimals=0, colors=PORT_COLORS, fill=0),
    timeseries("Container throughput, national", 12, 26, 12, 9, CONTAINERS, unit="short",
               decimals=0, colors={"value": CAT[3]}, fill=15,
               description="1000 TEU/quarter, no per-port breakdown in this CBS table."),

    timeseries("Freight transport to/from NL, by mode", 0, 35, 24, 9, FREIGHT_BY_MODE,
               unit="short", decimals=0, colors=MODE_COLORS, fill=0, legend="right",
               description="CBS 83101NED, annual, million tonnes. Road dominates domestic "
                           "+ cross-border freight by a wide margin over rail/water/air."),
]

write(dashboard("nl-ports", "NL: Ports & Shipping", panels, ["netherlands"], refresh="1h",
                time_from="2000-01-01T00:00:00Z",
                description="Dutch seaport cargo tonnage and ship calls (Rotterdam, "
                            "Amsterdam, Groningen Seaports, Zeeland Seaports), national "
                            "container throughput, and freight transport by mode."),
      "NL/nl-ports")
