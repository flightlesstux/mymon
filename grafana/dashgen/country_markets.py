"""One dashboard generator, six countries — main stock market index from
country_indices.py (Yahoo Finance, daily closes)."""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write

COUNTRIES = [
    ("DE", "DAX", "Germany"),
    ("IT", "FTSEMIB", "Italy"),
    ("ES", "IBEX35", "Spain"),
    ("GR", "ASE", "Greece"),
    ("TR", "BIST100", "Turkey"),
    ("FR", "CAC40", "France"),
]


def q(symbol: str) -> str:
    return (
        f"SELECT day AS time, close AS value FROM stock_index WHERE symbol='{symbol}' "
        f"AND $__timeFilter(day) ORDER BY 1"
    )


def q_latest(symbol: str) -> str:
    return f"SELECT close AS value FROM stock_index WHERE symbol='{symbol}' ORDER BY day DESC LIMIT 1"


for code, symbol, name in COUNTRIES:
    _lib._id = 0

    panels = [
        stat(f"{symbol}, latest close", 0, 0, 8, 6, q_latest(symbol), decimals=2, color=CAT[0]),
        timeseries(f"{symbol} daily close", 0, 6, 24, 13, q(symbol), decimals=2,
                   colors={"value": CAT[0]}, fill=15,
                   description=(
                       "Yahoo Finance, no key required."
                       if symbol != "ASE" else
                       "Yahoo Finance only has a single historical data point for the "
                       "Athens Composite (GD.AT) — the latest-close stat works, this "
                       "trend chart will show nothing until more history accumulates "
                       "from this collector's own daily polls."
                   )),
    ]

    write(dashboard(f"{code.lower()}-markets", f"{name}: Markets", panels, [name.lower()],
                    refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}'s main stock market index ({symbol}), daily "
                                f"closes, via Yahoo Finance."),
          f"{code}/{code.lower()}-markets")
