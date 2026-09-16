from _lib import CAT, dashboard, table, timeseries, write

SYMBOLS = [
    ("ASML", "ASML Holding"), ("ING", "ING Groep"), ("PHG", "Koninklijke Philips"),
    ("NXPI", "NXP Semiconductors"), ("STLA", "Stellantis"),
    ("LYB", "LyondellBasell Industries"), ("QGEN", "Qiagen"),
]
SYMBOL_COLORS = {sym: CAT[i % len(CAT)] for i, (sym, _) in enumerate(SYMBOLS)}

LATEST_TABLE = """
SELECT name AS "Company", symbol AS "Symbol", close AS "Close (USD)",
       round(100 * (close - prev_close) / prev_close, 2) AS "Change %", day AS "Session"
FROM (
    SELECT *, LAG(close) OVER (PARTITION BY symbol ORDER BY day) AS prev_close,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY day DESC) AS rn
    FROM nl_us_stock WHERE source='yahoo_finance'
) t
WHERE rn = 1
ORDER BY "Change %" DESC
"""

INDEXED_TREND = """
SELECT day AS time, symbol AS metric,
       close / first_value(close) OVER (PARTITION BY symbol ORDER BY day) * 100 AS value
FROM nl_us_stock
WHERE source='yahoo_finance' AND $__timeFilter(day)
ORDER BY 1
"""


def _price(symbol: str) -> str:
    return (
        f"SELECT day AS time, close AS value FROM nl_us_stock "
        f"WHERE source='yahoo_finance' AND symbol='{symbol}' AND $__timeFilter(day) ORDER BY 1"
    )


panels = [
    table("Latest session, all 7 companies", 0, 0, 24, 8, LATEST_TABLE, decimals=2,
          sort=("Change %", True),
          description="Dutch-domiciled (N.V.) companies listed on NASDAQ/NYSE — not "
                      "Shell or Unilever, both of which redomiciled to the UK."),

    timeseries("Share price performance, indexed to 100 at range start", 0, 8, 24, 10,
               INDEXED_TREND, decimals=1, colors=SYMBOL_COLORS, fill=0, legend="right",
               description="Every company on one axis regardless of raw price — ASML "
                           "trades around $1,600, Qiagen around $42; a shared price "
                           "axis would flatten the cheaper stocks."),
]

y = 18
for i, (symbol, name) in enumerate(SYMBOLS):
    x = (i % 3) * 8
    if i % 3 == 0 and i:
        y += 8
    panels.append(
        timeseries(f"{name} ({symbol})", x, y, 8, 8, _price(symbol),
                   unit="currencyUSD", decimals=2, colors={"value": SYMBOL_COLORS[symbol]},
                   fill=15)
    )

write(dashboard("nl-stocks", "NL: Companies on US Exchanges", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Daily closes for Dutch-domiciled (N.V.) companies listed "
                            "on NASDAQ/NYSE: ASML, ING, Philips, NXP Semiconductors, "
                            "Stellantis, LyondellBasell and Qiagen, since 2000 where "
                            "the listing goes back that far."),
      "NL/nl-stocks")
