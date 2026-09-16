from _lib import CAT, DS, dashboard, gauge, stat, table, target, timeseries, write

def fx(quote, label=None, invert=False):
    expr = "1/rate" if invert else "rate"
    return f"""SELECT ts AS time, {expr} AS "{label or quote}" FROM fx_rate
WHERE base='USD' AND quote='{quote}' AND source='frankfurter' AND $__timeFilter(ts) ORDER BY 1"""

FX_TRY = """
SELECT ts AS time, base || '/TRY' AS metric, rate AS value FROM fx_rate
WHERE quote='TRY' AND source='tcmb' AND base IN ('USD','EUR','GBP') AND $__timeFilter(ts) ORDER BY 1
"""
FX_MAJORS = """
SELECT ts AS time, 'EUR/USD' AS metric, 1/rate AS value FROM fx_rate WHERE base='USD' AND quote='EUR' AND source='frankfurter' AND $__timeFilter(ts)
UNION ALL
SELECT ts, 'GBP/USD', 1/rate FROM fx_rate WHERE base='USD' AND quote='GBP' AND source='frankfurter' AND $__timeFilter(ts)
ORDER BY 1
"""
FX_EM = """
SELECT ts AS time, 'USD/' || quote AS metric, rate AS value FROM fx_rate
WHERE base='USD' AND source='frankfurter' AND quote IN ('TRY','BRL','MXN','ZAR','INR') AND $__timeFilter(ts) ORDER BY 1
"""
FX_INDEXED = """
WITH base AS (
  SELECT quote, rate AS r0 FROM fx_rate
  WHERE base='USD' AND source='frankfurter' AND quote IN ('EUR','GBP','JPY','TRY','CHF','CNY')
    AND ts = (SELECT min(ts) FROM fx_rate WHERE base='USD' AND source='frankfurter' AND $__timeFilter(ts))
)
SELECT f.ts AS time, 'USD/' || f.quote AS metric, 100 * f.rate / b.r0 AS value
FROM fx_rate f JOIN base b ON b.quote = f.quote
WHERE f.base='USD' AND f.source='frankfurter' AND $__timeFilter(f.ts) ORDER BY 1
"""

def crypto_line(sym):
    return f"""SELECT ts AS time, price AS "{sym}" FROM crypto_tick WHERE symbol='{sym}' AND $__timeFilter(ts) ORDER BY 1"""

CRYPTO_DAILY = """
SELECT day AS time, symbol AS metric, close AS value FROM crypto_daily
WHERE symbol IN ('BTC','ETH','SOL','BNB','XRP') AND $__timeFilter(day) ORDER BY 1
"""
CRYPTO_INDEXED = """
WITH b AS (
  SELECT symbol, close AS c0 FROM crypto_daily
  WHERE day = (SELECT min(day) FROM crypto_daily WHERE $__timeFilter(day))
)
SELECT d.day AS time, d.symbol AS metric, 100 * d.close / b.c0 AS value
FROM crypto_daily d JOIN b ON b.symbol = d.symbol
WHERE d.symbol IN ('BTC','ETH','SOL','BNB','XRP') AND $__timeFilter(d.day) ORDER BY 1
"""
CRYPTO_TABLE = """
SELECT DISTINCT ON (symbol) symbol AS "Coin", price AS "Price", change_24h_pct AS "24 h %", volume_24h AS "24 h volume"
FROM crypto_tick WHERE ts > now() - interval '1 hour' ORDER BY symbol, ts DESC
"""

def commodity(name, label, src="stooq"):
    return f"""SELECT period_date AS time, price AS "{label}" FROM commodity_price
WHERE commodity='{name}' AND source='{src}' AND $__timeFilter(period_date) ORDER BY 1"""

OIL = """
SELECT period_date AS time, CASE commodity WHEN 'brent' THEN 'Brent' ELSE 'WTI' END AS metric, price AS value
FROM commodity_price WHERE commodity IN ('brent','wti') AND source='stooq' AND $__timeFilter(period_date) ORDER BY 1
"""
METALS = """
SELECT period_date AS time, commodity AS metric, price AS value
FROM commodity_price WHERE commodity IN ('gold','silver') AND source='stooq' AND $__timeFilter(period_date) ORDER BY 1
"""
INDICES = """
SELECT day AS time, symbol AS metric, close AS value FROM stock_index
WHERE symbol IN ('SPX','DJI','NDQ','DAX','UKX','NKX','XU100') AND $__timeFilter(day) ORDER BY 1
"""
INDICES_INDEXED = """
WITH b AS (
  SELECT symbol, close AS c0 FROM stock_index
  WHERE day = (SELECT min(day) FROM stock_index WHERE $__timeFilter(day))
)
SELECT s.day AS time, s.symbol AS metric, 100 * s.close / b.c0 AS value
FROM stock_index s JOIN b ON b.symbol = s.symbol
WHERE s.symbol IN ('SPX','DJI','NDQ','DAX','UKX','NKX','XU100') AND $__timeFilter(s.day) ORDER BY 1
"""
BTC_GOLD = """
SELECT d.day AS time, d.close / g.price AS "BTC priced in gold ounces"
FROM crypto_daily d JOIN commodity_price g ON g.period_date = d.day AND g.commodity='gold' AND g.source='stooq'
WHERE d.symbol='BTC' AND $__timeFilter(d.day) ORDER BY 1
"""
PAXG_VS_GOLD = """
SELECT d.day AS time, 'PAXG (Binance)' AS metric, d.close AS value FROM crypto_daily d WHERE d.symbol='PAXG' AND $__timeFilter(d.day)
UNION ALL
SELECT period_date, 'Gold spot (Stooq)', price FROM commodity_price WHERE commodity='gold' AND source='stooq' AND $__timeFilter(period_date)
ORDER BY 1
"""

panels = [
    stat("BTC", 0, 0, 4, 4, crypto_line("BTC"), unit="currencyUSD", decimals=0, color=CAT[3]),
    stat("ETH", 4, 0, 4, 4, crypto_line("ETH"), unit="currencyUSD", decimals=0, color=CAT[6]),
    stat("USD/TRY", 8, 0, 4, 4, fx("TRY"), decimals=2, color=CAT[1]),
    stat("EUR/USD", 12, 0, 4, 4, fx("EUR", invert=True), decimals=4, color=CAT[0]),
    stat("Gold", 16, 0, 4, 4, commodity("gold", "gold"), unit="currencyUSD", decimals=0, color=CAT[3]),
    stat("Brent", 20, 0, 4, 4, commodity("brent", "brent"), unit="currencyUSD", decimals=2, color=CAT[2]),

    timeseries("Turkish lira — USD, EUR, GBP (TCMB selling)", 0, 4, 12, 9, FX_TRY, decimals=2, colors={"USD/TRY": CAT[0], "EUR/TRY": CAT[1], "GBP/TRY": CAT[2]}),
    timeseries("Majors vs USD", 12, 4, 12, 9, FX_MAJORS, decimals=4, colors={"EUR/USD": CAT[0], "GBP/USD": CAT[2]}),
    timeseries("USD vs emerging currencies, indexed to 100 at range start", 0, 13, 12, 9, FX_INDEXED, decimals=1,
               colors={"USD/EUR": CAT[0], "USD/GBP": CAT[1], "USD/JPY": CAT[2], "USD/TRY": CAT[3],
                       "USD/CHF": CAT[4], "USD/CNY": CAT[5]},
               fill=0, description="Rising line = currency weakening against the dollar."),
    timeseries("USD/TRY, USD/BRL, USD/MXN, USD/ZAR, USD/INR", 12, 13, 12, 9, FX_EM, decimals=2,
               colors={"USD/TRY": CAT[0], "USD/BRL": CAT[1], "USD/MXN": CAT[2], "USD/ZAR": CAT[3],
                       "USD/INR": CAT[4]}, fill=0),

    timeseries("Crypto, indexed to 100 at range start", 0, 22, 12, 9, CRYPTO_INDEXED, decimals=0,
               colors={"BTC": CAT[3], "ETH": CAT[6], "SOL": CAT[4], "BNB": CAT[1], "XRP": CAT[0]},
               fill=0),
    timeseries("BTC intraday (1-minute ticks)", 12, 22, 12, 9, crypto_line("BTC"), unit="currencyUSD", decimals=0, colors={"BTC": CAT[3]}),
    table("Crypto now", 0, 31, 8, 8, CRYPTO_TABLE, sort=("24 h volume", True),
          overrides=[{"matcher": {"id": "byName", "options": "Price"}, "properties": [{"id": "unit", "value": "currencyUSD"}]},
                     {"matcher": {"id": "byName", "options": "24 h volume"}, "properties": [{"id": "unit", "value": "currencyUSD"}, {"id": "decimals", "value": 0}]},
                     {"matcher": {"id": "byName", "options": "24 h %"},
                      "properties": [{"id": "unit", "value": "percent"}, {"id": "decimals", "value": 2},
                                     {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                     {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "#d03b3b", "value": None}, {"color": "#0ca30c", "value": 0}]}},
                                     {"id": "color", "value": {"mode": "thresholds"}}]}]),
    timeseries("BTC priced in gold ounces", 8, 31, 8, 8, BTC_GOLD, decimals=1, colors={"BTC priced in gold ounces": CAT[3]}, fill=15),
    timeseries("Tokenised gold (PAXG) vs spot gold", 16, 31, 8, 8, PAXG_VS_GOLD, unit="currencyUSD", decimals=0,
               colors={"PAXG (Binance)": CAT[3], "Gold spot (Stooq)": CAT[0]}, fill=0),

    timeseries("Oil — Brent and WTI, USD/bbl", 0, 39, 12, 9, OIL, unit="currencyUSD", decimals=2, colors={"Brent": CAT[2], "WTI": CAT[1]}, fill=0),
    timeseries("Gold and silver, USD/oz", 12, 39, 12, 9, METALS, unit="currencyUSD", decimals=2, colors={"gold": CAT[3], "silver": CAT[0]}, fill=0,
               description="Silver is on the same axis; use the legend to isolate a series."),
    timeseries("Stock indices, indexed to 100 at range start", 0, 48, 24, 10, INDICES_INDEXED, decimals=0,
               colors={"SPX": CAT[0], "DJI": CAT[1], "NDQ": CAT[2], "DAX": CAT[3], "UKX": CAT[4],
                       "NKX": CAT[5], "XU100": CAT[6]}, fill=0, legend="right",
               description="S&P 500, Dow, Nasdaq, DAX, FTSE 100, Nikkei 225, BIST 100."),
]

write(dashboard("markets", "Markets", panels, ["markets"], refresh="1m", time_from="now-90d",
                description="FX, crypto, oil, metals and equity indices from public feeds."),
      "markets")
