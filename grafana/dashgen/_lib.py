"""Grafana dashboard JSON generator. `make dashboards` runs generate_all.py, which runs
every sibling script in this directory; each one builds a dashboard dict with the helpers
below and calls write(). The committed JSON under grafana/dashboards/ is generated output —
edit the scripts here, not the JSON, and regenerate."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "dashboards"
DS = {"type": "grafana-postgresql-datasource", "uid": "mymon-pg"}
PROM_DS = {"type": "prometheus", "uid": "mymon-prom"}

# dark-mode categorical palette (fixed order) + sequential blue ramp + diverging
CAT = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
MUTED = "#898781"

_id = 0


def nid() -> int:
    global _id
    _id += 1
    return _id


def target(sql: str, ref: str = "A", fmt: str = "time_series") -> dict:
    return {"datasource": DS, "refId": ref, "rawQuery": True, "rawSql": sql, "format": fmt,
            "editorMode": "code"}


def prom_target(expr: str, ref: str = "A", legend: str | None = None, instant: bool = False) -> dict:
    t = {"datasource": PROM_DS, "refId": ref, "expr": expr, "range": not instant, "instant": instant}
    if legend:
        t["legendFormat"] = legend
    return t


def panel(kind: str, title: str, x: int, y: int, w: int, h: int, targets: list[dict],
          unit: str | None = None, decimals: int | None = None, options: dict | None = None,
          defaults: dict | None = None, overrides: list | None = None, description: str = "",
          transformations: list | None = None, links: list | None = None,
          datasource: dict | None = None) -> dict:
    d = {"color": {"mode": "palette-classic"}, "custom": {}}
    if unit:
        d["unit"] = unit
    if decimals is not None:
        d["decimals"] = decimals
    if defaults:
        deep_merge(d, defaults)
    p = {
        "id": nid(), "type": kind, "title": title, "description": description,
        "datasource": datasource or DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets, "options": options or {},
        "fieldConfig": {"defaults": d, "overrides": overrides or []},
    }
    if transformations:
        p["transformations"] = transformations
    if links:
        p["links"] = links
    return p


def _name_color_overrides(mapping: dict[str, str]) -> list[dict]:
    """Fixed colors keyed by exact series/field display name.

    Grafana's fieldConfig overrides only match by name, type, regexp, frame ref id, or
    value — there is no "byIndex" matcher (a nonexistent id crashes the panel with
    'byIndex not found in: ...'), so a series can only get a specific color if we know
    its literal display name in advance (the SQL alias, or a literal string a query
    selects as the grouping column).
    """
    return [
        {"matcher": {"id": "byName", "options": name},
         "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}
        for name, color in mapping.items()
    ]


def deep_merge(a: dict, b: dict) -> dict:
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            deep_merge(a[k], v)
        else:
            a[k] = v
    return a


def timeseries(title, x, y, w, h, sql=None, unit=None, decimals=None, fill=8, colors=None,
               legend="bottom", stack=False, points=False, description="", min_=None, max_=None,
               thresholds_line=None, lw=2, targets=None, datasource=None):
    d = {
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": "line", "lineInterpolation": "linear", "lineWidth": lw,
            "fillOpacity": fill, "gradientMode": "opacity", "showPoints": "auto" if points else "never",
            "pointSize": 5, "spanNulls": 3600000, "axisBorderShow": False,
            "stacking": {"mode": "normal" if stack else "none", "group": "A"},
            "thresholdsStyle": {"mode": "off"},
        },
    }
    if min_ is not None:
        d["min"] = min_
    if max_ is not None:
        d["max"] = max_
    overrides = _name_color_overrides(colors) if isinstance(colors, dict) else []
    opts = {"legend": {"displayMode": "list", "placement": legend, "showLegend": legend != "hidden",
                       "calcs": []},
            "tooltip": {"mode": "multi", "sort": "desc"}}
    return panel("timeseries", title, x, y, w, h, targets or [target(sql)], unit, decimals, opts, d,
                 overrides, description, datasource=datasource)


def stat(title, x, y, w, h, sql=None, unit=None, decimals=None, color=CAT[0], sparkline=True,
         description="", thresholds=None, text_mode="value", color_mode="value",
         targets=None, datasource=None, text_value=False):
    """`text_value=True` for a panel whose query returns a string, not a number.

    The Stat panel's default field matcher (an empty `fields` string, meaning "Numeric
    Fields") silently excludes text-typed fields, so a query like `SELECT city || ...`
    shows "No data" even though it returned a row. `"/.*/"` matches any field regardless
    of type; safe here because these queries return exactly one field, so there's no
    risk of it also picking up a stray time column from a multi-field time series.
    """
    d = {"color": {"mode": "fixed", "fixedColor": color},
         "thresholds": {"mode": "absolute", "steps": [{"color": color, "value": None}]}}
    if thresholds:
        d["color"] = {"mode": "thresholds"}
        d["thresholds"] = {"mode": "absolute", "steps": thresholds}
    fields = "/.*/" if text_value else ""
    opts = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": fields, "values": False},
            "graphMode": "area" if sparkline else "none", "colorMode": color_mode,
            "textMode": text_mode, "justifyMode": "auto", "orientation": "auto",
            "wideLayout": True, "showPercentChange": False}
    return panel("stat", title, x, y, w, h, targets or [target(sql, fmt="table")], unit, decimals, opts, d,
                 description=description, datasource=datasource)


def gauge(title, x, y, w, h, sql, unit=None, min_=0, max_=100, steps=None, decimals=None,
          description=""):
    steps = steps or [{"color": STATUS["good"], "value": None}]
    d = {"color": {"mode": "thresholds"}, "min": min_, "max": max_,
         "thresholds": {"mode": "absolute", "steps": steps}}
    opts = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showThresholdLabels": False, "showThresholdMarkers": True, "orientation": "auto"}
    return panel("gauge", title, x, y, w, h, [target(sql, fmt="table")], unit, decimals, opts, d,
                 description=description)


def table(title, x, y, w, h, sql, unit=None, overrides=None, description="", sort=None,
          transformations=None, decimals=None):
    opts = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    if sort:
        opts["sortBy"] = [{"displayName": sort[0], "desc": sort[1]}]
    d = {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": False}}
    return panel("table", title, x, y, w, h, [target(sql, fmt="table")], unit, decimals, opts, d,
                 overrides or [], description, transformations)


def barchart(title, x, y, w, h, sql, unit=None, color=CAT[0], horizontal=True, decimals=None,
             description="", colors_by_field=None, stack=False, legend="hidden"):
    d = {"color": {"mode": "fixed", "fixedColor": color},
         "custom": {"fillOpacity": 85, "lineWidth": 0, "gradientMode": "none", "axisBorderShow": False}}
    if colors_by_field:
        d["color"] = {"mode": "palette-classic"}
    opts = {"orientation": "horizontal" if horizontal else "vertical", "xTickLabelRotation": 0,
            "showValue": "auto", "barWidth": 0.8, "groupWidth": 0.7, "barRadius": 0.1,
            "stacking": "normal" if stack else "none",
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": legend != "hidden"},
            "tooltip": {"mode": "single", "sort": "none"}}
    overrides = _name_color_overrides(colors_by_field) if isinstance(colors_by_field, dict) else []
    return panel("barchart", title, x, y, w, h, [target(sql, fmt="table")], unit, decimals, opts, d,
                 overrides, description)


def geomap(title, x, y, w, h, layers: list[dict], view: dict | None = None, description="",
           targets: list[dict] | None = None, basemap_dark=True):
    # Carto's free raster tile CDN (the "carto" basemap type) Referer-gates unrecognized
    # domains and serves an "API KEY REQUIRED" placeholder image instead of a 4xx, so it
    # looks fine in isolation (curl, no Referer) but breaks silently in a real browser.
    # OpenStreetMap's standard tiles have no such gate and need no key or config.
    opts = {
        "view": view or {"id": "zero", "lat": 20, "lon": 10, "zoom": 1.6, "allLayers": True},
        "controls": {"showZoom": True, "mouseWheelZoom": False, "showAttribution": True,
                     "showScale": False, "showMeasure": False, "showDebug": False},
        "basemap": {"type": "osm-standard", "name": "Basemap"},
        "layers": layers,
        "tooltip": {"mode": "details"},
    }
    return panel("geomap", title, x, y, w, h, targets or [], options=opts, description=description)


def marker_layer(name, ref, size_field=None, color_field=None, size=(4, 14), fixed_color=CAT[0],
                 color_scheme=None, min_=None, max_=None, opacity=0.8, text_field=None, symbol=None):
    style = {
        "size": {"fixed": size[0], "min": size[0], "max": size[1]},
        "color": {"fixed": fixed_color},
        "opacity": opacity,
        "symbol": {"mode": "fixed", "fixed": symbol or "img/icons/marker/circle.svg"},
        "symbolAlign": {"horizontal": "center", "vertical": "center"},
        "rotation": {"fixed": 0, "mode": "mod", "min": -360, "max": 360},
        "textConfig": {"fontSize": 11, "offsetX": 0, "offsetY": 12, "textAlign": "center", "textBaseline": "middle"},
    }
    if size_field:
        style["size"]["field"] = size_field
    if color_field:
        style["color"] = {"field": color_field, "fixed": fixed_color}
    if text_field:
        style["text"] = {"field": text_field, "fixed": "", "mode": "field"}
    layer = {
        "type": "markers", "name": name,
        "config": {"style": style, "showLegend": False},
        "location": {"mode": "auto"},
        "filterData": {"id": "byRefId", "options": ref},
        "tooltip": True,
    }
    if color_field:
        fc = {"color": {"mode": color_scheme or "continuous-BlYlRd"}}
        if min_ is not None:
            fc["min"] = min_
        if max_ is not None:
            fc["max"] = max_
        layer["fieldConfig"] = {"defaults": fc, "overrides": []}
    return layer


def row(title, y):
    return {"id": nid(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


def text(title, x, y, w, h, md):
    return panel("text", title, x, y, w, h, [], options={"mode": "markdown", "content": md})


def dashboard(uid, title, panels, tags, refresh="5m", time_from="now-7d", templating=None,
              description="", links=None):
    return {
        "uid": uid, "title": title, "description": description, "tags": tags,
        "timezone": "utc", "editable": False, "graphTooltip": 1, "schemaVersion": 41,
        "version": 1, "refresh": refresh, "style": "dark",
        "time": {"from": time_from, "to": "now"},
        "timepicker": {"refresh_intervals": ["1m", "5m", "15m", "1h"]},
        "templating": {"list": templating or []},
        "annotations": {"list": []},
        "links": links or NAV_LINKS,
        "panels": panels,
    }


NAV_LINKS = [{"type": "dashboards", "title": "lyraqpi", "tags": [], "asDropdown": True,
              "icon": "external link", "includeVars": False, "keepTime": True, "targetBlank": False}]


def write(dash: dict, name: str):
    """``name`` may include a subdirectory (e.g. ``"NL/nl-economy"``), which becomes a
    Grafana folder — see foldersFromFilesStructure in provisioning/dashboards/dashboards.yml.
    """
    path = OUT / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dash, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", name, "panels:", len(dash["panels"]))
