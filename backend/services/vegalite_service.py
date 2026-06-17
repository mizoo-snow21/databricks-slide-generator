"""Convert Lakeview widget specs to Vega-Lite for HTML slide embedding."""

from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from models import ChartAugmentation, ChartDesign


_AGG_FN_RE = re.compile(
    r"^(?P<fn>sum|avg|count|min|max|median)\((?P<inner>.+)\)$",
    re.IGNORECASE,
)

_VEGA_AGG: dict[str, str] = {
    "sum": "sum",
    "avg": "mean",
    "count": "count",
    "min": "min",
    "max": "max",
    "median": "median",
}

_SUPPRESS = object()


def _is_ascii_only(s: str | None) -> bool:
    """True if s is None / empty / contains only ASCII (incl. punctuation)."""
    if not s:
        return True
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _sanitize_title(s: str | None) -> str | None | object:
    """Keep ASCII titles; non-ASCII display titles use _SUPPRESS for explicit null."""
    if not s:
        return s
    if not _is_ascii_only(s):
        return _SUPPRESS
    return s


_CATEGORY_PALETTE = [
    "#4C78A8",
    "#F58518",
    "#E45756",
    "#72B7B2",
    "#54A24B",
    "#EECA3B",
    "#B279A2",
    "#FF9DA6",
]


_FONT_STACK = (
    "Inter, 'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif"
)


def _vega_lite_config(
    tone: str = "light", palette: list[str] | None = None
) -> dict[str, Any]:
    """Vega-Lite config adapted to slide background tone.

    `tone='light'` → dark text on white-ish chart canvas (standard).
    `tone='dark'`  → light text on transparent chart canvas (for dark slides).
    The chart background stays transparent in both cases so the slide
    background shows through; axis, legend, title, and `text` mark colors
    follow `tone`. Optional `palette` overrides the default categorical range.
    """
    if tone == "dark":
        text_color = "rgba(255,255,255,0.98)"
        grid_color = "rgba(255,255,255,0.12)"
        arc_stroke = "rgba(15,30,40,0.55)"  # darken between slices for depth
    else:
        text_color = "rgba(15,15,15,0.95)"
        grid_color = "rgba(15,15,15,0.10)"
        arc_stroke = "rgba(255,255,255,0.85)"  # bright stroke for slice definition
    cat_palette = palette if palette is not None else _CATEGORY_PALETTE
    return {
        "background": "transparent",
        "padding": {"left": 16, "right": 16, "top": 14, "bottom": 14},
        "axis": {
            "grid": False,
            "domain": False,
            "ticks": False,
            "labelColor": text_color,
            "titleColor": text_color,
            "labelFont": _FONT_STACK,
            "labelFontSize": 18,
            "labelFontWeight": 500,
            "labelPadding": 6,
            "labelLimit": 240,
            # Field-name-derived axis titles ("Sum of total_amount") are
            # redundant with the slot title above the chart card. Suppress
            # them globally; the chart's primary label is the card heading.
            "title": None,
            "tickCount": 6,
            "labelOverlap": "greedy",
        },
        "axisX": {
            # Don't draw horizontal gridline at zero for category axes
            "grid": False,
            # Rotate nominal labels so Japanese category names (関東, 中部, …)
            # render horizontally with enough room. Vega-Lite only applies
            # this when no per-encoding override is set.
            "labelAngle": -30,
            "labelAlign": "right",
            "labelBaseline": "top",
        },
        "axisQuantitative": {
            "format": ".2s",
            "grid": True,
            "gridColor": grid_color,
            "gridDash": [2, 4],
            "gridWidth": 1,
            "domain": False,
            "ticks": False,
        },
        "legend": {
            "title": None,
            "labelColor": text_color,
            "titleColor": text_color,
            "labelFont": _FONT_STACK,
            "labelFontSize": 18,
            "labelFontWeight": 500,
            "titleFont": _FONT_STACK,
            "orient": "bottom",
            "direction": "horizontal",
            "symbolSize": 180,
            "symbolStrokeWidth": 0,
            "labelOffset": 8,
            "columnPadding": 20,
            "padding": 8,
        },
        "title": {
            "color": text_color,
            "font": _FONT_STACK,
            "fontWeight": 600,
            "fontSize": 22,
            "anchor": "start",
            "offset": 12,
        },
        "text": {
            "color": text_color,
            "font": _FONT_STACK,
            "fontWeight": 600,
            "fontSize": 18,
        },
        "bar": {
            "cornerRadiusEnd": 6,
            "stroke": None,
            "strokeWidth": 0,
            "continuousBandSize": 56,
            "discreteBandSize": {"band": 0.78},
        },
        "line": {
            "interpolate": "monotone",
            "strokeWidth": 6,
            "point": {"filled": True, "size": 220, "stroke": None},
            "strokeCap": "round",
            "strokeJoin": "round",
        },
        "point": {"size": 220, "filled": True, "strokeWidth": 0},
        "area": {
            "interpolate": "monotone",
            "line": {"strokeWidth": 4, "strokeCap": "round"},
            "opacity": 0.55,
        },
        "arc": {
            "innerRadius": 110,
            "stroke": arc_stroke,
            "strokeWidth": 5,
        },
        "view": {"stroke": None},
        "range": {"category": cat_palette},
    }


def _chart_base(
    query_data: list[dict[str, Any]],
    title: str | None,
    tone: str = "light",
    palette: list[str] | None = None,
) -> dict[str, Any]:
    # Native canvas 720x460 (~1.56:1, between 16:9 and 4:3) — matches the
    # aspect of the chart slot in two-column / card-left / three-column
    # layouts so the PNG fills the slot without letterbox padding.
    # scale=2 in _render_chart_to_png → 1440x920 PNG. Source fonts at
    # 18-22px render as readable ~13-16px in a 2-col slide layout.
    base: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": query_data},
        "width": 720,
        "height": 460,
        "config": _vega_lite_config(tone, palette=palette),
    }
    if title and _is_ascii_only(title):
        base["title"] = title
    return base


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_number(v: Any) -> bool:
    if _is_bool(v):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str) and v.strip():
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _is_temporal(v: Any) -> bool:
    if isinstance(v, (datetime, date)):
        return True
    if not isinstance(v, str) or not v.strip():
        return False
    s = v.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return True
    if "T" in s and re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return True
    return False


def _column_values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row.get(field) for row in rows if field in row]


def infer_vega_type(values: list[Any]) -> str:
    """Return a Vega-Lite type string: quantitative, temporal, or nominal."""
    vals = [v for v in values if v is not None and v != ""]
    if not vals:
        return "nominal"
    if all(_is_number(v) for v in vals):
        return "quantitative"
    if all(_is_temporal(v) for v in vals):
        return "temporal"
    return "nominal"


def widget_spec_from_columns(
    title: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Synthesize a Lakeview-shaped widget spec from Genie result columns."""
    if not columns:
        return {"widgetType": "bar", "title": title, "encodings": {}}

    col_types = {col: infer_vega_type(_column_values(rows, col)) for col in columns}

    x: str | None = None
    for col in columns:
        if col_types[col] == "temporal":
            x = col
            break
    if x is None:
        for col in columns:
            if col_types[col] == "nominal":
                x = col
                break
    if x is None:
        x = columns[0]

    y: str | None = None
    for col in columns:
        if col != x and col_types[col] == "quantitative":
            y = col
            break

    color: str | None = None
    for col in columns:
        if col != x and col != y and col_types[col] == "nominal":
            color = col
            break

    widget_type = "bar"
    x_type = col_types[x]
    if y is None:
        widget_type = "table"
    elif x_type == "temporal":
        widget_type = "line"

    encodings: dict[str, Any] = {}
    if x is not None:
        encodings["x"] = {"fieldName": x}
    if y is not None:
        encodings["y"] = {"fieldName": y}
    if color is not None:
        encodings["color"] = {"fieldName": color}

    return {"widgetType": widget_type, "title": title, "encodings": encodings}


def _truncate_top_n_with_other(
    rows: list[dict[str, Any]],
    color_field: str,
    value_field: str,
    n: int = 7,
) -> list[dict[str, Any]]:
    """Keep the top *n* categories by summed *value_field*; map the rest to ``Other``."""
    if not rows or n < 1:
        return rows
    totals: dict[Any, float] = defaultdict(float)
    for row in rows:
        cat = row.get(color_field)
        raw = row.get(value_field)
        if _is_number(raw):
            totals[cat] += float(raw)
        elif raw is not None and str(raw).strip():
            try:
                totals[cat] += float(raw)
            except (TypeError, ValueError):
                pass
    if len(totals) <= n:
        return rows
    ordered = sorted(totals.keys(), key=lambda c: (totals[c], str(c)), reverse=True)
    keep = set(ordered[:n])
    out: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        cat = new_row.get(color_field)
        if cat not in keep:
            new_row[color_field] = "Other"
        out.append(new_row)
    return out


def _maybe_roll_up_nominal_color(
    rows: list[dict[str, Any]],
    color_field: str | None,
    value_field: str | None,
    *,
    n: int = 7,
) -> list[dict[str, Any]]:
    if not rows or not color_field or not value_field:
        return rows
    if infer_vega_type(_column_values(rows, color_field)) != "nominal":
        return rows
    distinct = {row.get(color_field) for row in rows}
    if len(distinct) <= n:
        return rows
    return _truncate_top_n_with_other(rows, color_field, value_field, n=n)


def _row_measure(row: dict[str, Any], field: str | None) -> float:
    if not field:
        return 1.0
    if field not in row:
        return 0.0
    v = row[field]
    if _is_number(v):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v)
        except ValueError:
            pass
    return 0.0


def _effective_sort_and_top_n(
    design: ChartDesign,
    category_field: str,
    rows: list[dict[str, Any]],
) -> tuple[str, int | None]:
    wtype = design.chart_type or "bar"
    sort = design.sort
    top_n = design.top_n

    if wtype in ("line", "area"):
        top_n = None
        if infer_vega_type(_column_values(rows, category_field)) == "temporal":
            sort = "none"

    if wtype == "bar" and top_n is not None and sort == "none":
        sort = "value_desc"

    if top_n is not None:
        top_n = min(top_n, 20)

    return sort, top_n


def _aggregate_sort_top_n_rows(
    rows: list[dict[str, Any]],
    category: str,
    value: str | None,
    series: str | None,
    aggregate: Literal["sum", "avg", "count", "none"],
    sort: Literal["value_desc", "value_asc", "category", "none"],
    top_n: int | None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Aggregate, sort categories, and keep top-N. Returns (rendered_rows, ordered_categories)."""
    if not rows or not category:
        return [], []

    measure_field = value
    if aggregate == "count" and not measure_field:
        measure_field = "__count"

    filtered: list[dict[str, Any]] = []
    for row in rows:
        cat = row.get(category)
        if cat is None or cat == "":
            continue
        if series:
            ser = row.get(series)
            if ser is None or ser == "":
                continue
        filtered.append(row)

    if aggregate in ("sum", "avg", "count"):
        grouped: dict[tuple[Any, Any | None], list[dict[str, Any]]] = defaultdict(list)
        for row in filtered:
            key = (row[category], row.get(series) if series else None)
            grouped[key].append(row)

        rendered: list[dict[str, Any]] = []
        for (cat, ser), group_rows in grouped.items():
            out: dict[str, Any] = {category: cat}
            if series:
                out[series] = ser
            if aggregate == "count":
                out[measure_field] = len(group_rows)
            elif aggregate == "sum":
                out[measure_field] = sum(_row_measure(r, value) for r in group_rows)
            else:
                vals = [_row_measure(r, value) for r in group_rows]
                out[measure_field] = (sum(vals) / len(vals)) if vals else 0.0
            rendered.append(out)
    else:
        rendered = [dict(r) for r in filtered]

    cat_totals: dict[Any, float] = defaultdict(float)
    for row in rendered:
        cat = row.get(category)
        if cat is None:
            continue
        cat_totals[cat] += _row_measure(row, measure_field)

    seen: set[Any] = set()
    all_cats: list[Any] = []
    for row in rendered:
        cat = row.get(category)
        if cat is not None and cat not in seen:
            seen.add(cat)
            all_cats.append(cat)

    if sort == "value_desc":
        ordered = sorted(all_cats, key=lambda c: (cat_totals[c], str(c)), reverse=True)
    elif sort == "value_asc":
        ordered = sorted(all_cats, key=lambda c: (cat_totals[c], str(c)))
    elif sort == "category":
        ordered = sorted(all_cats, key=str)
    else:
        ordered = all_cats

    if top_n is not None:
        ordered = ordered[:top_n]
        keep = set(ordered)
        rendered = [r for r in rendered if r.get(category) in keep]

    return rendered, ordered


def _design_is_usable(design: ChartDesign | None, columns: list[str]) -> bool:
    if design is None or not design.chart_type:
        return False
    if design.chart_type not in ("bar", "line", "area", "pie", "scatter"):
        return False
    cat = design.category_field
    if not cat or cat not in columns:
        return False
    if design.series_field and design.series_field not in columns:
        return False
    val = design.value_field
    if design.chart_type == "scatter":
        return bool(val and val in columns)
    if design.aggregate == "count":
        return not val or val in columns
    return bool(val and val in columns)


def _is_value_label_layer(layer: Any) -> bool:
    return (
        isinstance(layer, dict)
        and isinstance(layer.get("mark"), dict)
        and layer["mark"].get("type") == "text"
        and isinstance(layer.get("encoding"), dict)
        and isinstance(layer["encoding"].get("text"), dict)
        and layer["encoding"]["text"].get("format") == ".2s"
    )


def _max_aggregated_measure(
    rows: list[dict[str, Any]],
    cat_field: str,
    measure_field: str,
    aggregate: str | None,
) -> float | None:
    """Max per-category aggregated measure (matches bar height semantics)."""
    if not rows:
        return None
    by_cat: dict[Any, list[float]] = defaultdict(list)
    for row in rows:
        cat = row.get(cat_field)
        if cat is None or cat == "":
            continue
        by_cat[cat].append(_row_measure(row, measure_field))
    if not by_cat:
        return None

    per_cat: list[float] = []
    agg = (aggregate or "").lower()
    for vals in by_cat.values():
        if not vals:
            continue
        if agg in ("", "none"):
            per_cat.append(max(vals))
        elif agg == "sum":
            per_cat.append(sum(vals))
        elif agg in ("avg", "mean"):
            per_cat.append(sum(vals) / len(vals))
        elif agg == "count":
            per_cat.append(float(len(vals)))
        elif agg == "max":
            per_cat.append(max(vals))
        elif agg == "min":
            per_cat.append(min(vals))
        else:
            per_cat.append(max(vals))
    if not per_cat:
        return None
    mx = max(per_cat)
    if mx <= 0:
        return None
    return mx


def _bar_with_value_labels(
    bar_mark: dict[str, Any],
    enc_out: dict[str, Any],
    *,
    cat_channel: str,
    rows: list[dict[str, Any]],
    measure_field: str,
    aggregate: str | None,
    tone: str,
) -> dict[str, Any]:
    """Return a layered spec: bar (layer 0) + value labels (layer 1)."""
    measure_channel = "y" if cat_channel == "x" else "x"
    text_color = _vega_lite_config(tone)["text"]["color"]

    bar_enc = copy.deepcopy(enc_out)
    text_enc = copy.deepcopy(enc_out)

    cat_part = enc_out.get(cat_channel)
    cat_field = cat_part.get("field") if isinstance(cat_part, dict) else None
    mx: float | None = None
    if isinstance(cat_field, str):
        mx = _max_aggregated_measure(rows, cat_field, measure_field, aggregate)

    for enc in (bar_enc, text_enc):
        meas = enc.get(measure_channel)
        if isinstance(meas, dict):
            meas["axis"] = None
            if mx is not None:
                meas.setdefault("scale", {})["domainMax"] = mx * 1.18

    for ch in list(text_enc):
        if ch not in (cat_channel, measure_channel):
            del text_enc[ch]

    if cat_channel == "y":
        text_mark: dict[str, Any] = {
            "type": "text",
            "align": "left",
            "baseline": "middle",
            "dx": 8,
            "font": _FONT_STACK,
            "fontSize": 15,
            "fontWeight": 700,
            "color": text_color,
        }
    else:
        text_mark = {
            "type": "text",
            "align": "center",
            "baseline": "bottom",
            "dy": -8,
            "font": _FONT_STACK,
            "fontSize": 15,
            "fontWeight": 700,
            "color": text_color,
        }

    measure_enc_raw = enc_out.get(measure_channel)
    if isinstance(measure_enc_raw, dict):
        text_channel = copy.deepcopy(measure_enc_raw)
        text_channel["format"] = ".2s"
        text_channel["type"] = "quantitative"
    else:
        text_channel = {
            "field": measure_field,
            "type": "quantitative",
            "format": ".2s",
        }
        if aggregate:
            text_channel["aggregate"] = aggregate
    text_enc["text"] = text_channel

    return {
        "layer": [
            {"mark": bar_mark, "encoding": bar_enc},
            {"mark": text_mark, "encoding": text_enc},
        ]
    }


def _should_force_horizontal(
    rows: list[dict[str, Any]],
    category_field: str,
    *,
    wtype: str,
) -> bool:
    if wtype != "bar":
        return False
    cat_vals = _column_values(rows, category_field)
    if infer_vega_type(cat_vals) != "nominal":
        return False
    distinct_vals = [v for v in cat_vals if v is not None and v != ""]
    distinct = len(set(distinct_vals))
    if distinct < 6:
        return False
    long_labels = sum(1 for v in distinct_vals if len(str(v)) > 12)
    return long_labels >= max(1, distinct // 2)


def _convert_with_design(
    design: ChartDesign,
    query_data: list[dict[str, Any]],
    title: str | None,
    *,
    bg_tone: str,
    palette: list[str] | None,
    accent_color: str | None,
) -> dict[str, Any] | None:
    wtype = design.chart_type
    assert wtype is not None
    cat = design.category_field
    assert cat is not None
    val = design.value_field
    series = design.series_field

    horizontal = design.orientation == "horizontal"
    if design.orientation is None and _should_force_horizontal(
        query_data, cat, wtype=wtype
    ):
        horizontal = True

    sort_eff, top_n_eff = _effective_sort_and_top_n(design, cat, query_data)

    if wtype == "scatter":
        chart_rows = [
            dict(r)
            for r in query_data
            if cat in r
            and val in r
            and r.get(cat) not in (None, "")
            and r.get(val) not in (None, "")
        ]
        ordered_categories: list[Any] = []
    else:
        chart_rows, ordered_categories = _aggregate_sort_top_n_rows(
            query_data,
            cat,
            val,
            series,
            design.aggregate,
            sort_eff,  # type: ignore[arg-type]
            top_n_eff,
        )

    measure_field = val
    if design.aggregate == "count" and not val:
        measure_field = "__count"

    if wtype != "scatter" and not chart_rows:
        return None

    base = _chart_base(chart_rows, title, tone=bg_tone, palette=palette)

    if wtype == "pie":
        if not measure_field:
            return None
        base["mark"] = {"type": "arc"}
        base["encoding"] = {
            "theta": _encoding_with_sanitized_title(
                measure_field, chart_rows, aggregate=None
            ),
            "color": _encoding_with_sanitized_title(cat, chart_rows, is_color=True),
        }
        return base

    if wtype == "scatter":
        assert val is not None
        enc_out: dict[str, Any] = {
            "x": _encoding_with_sanitized_title(cat, chart_rows),
            "y": _encoding_with_sanitized_title(val, chart_rows, aggregate=None),
        }
        if series:
            enc_out["color"] = _encoding_with_sanitized_title(
                series, chart_rows, is_color=True
            )
        base["mark"] = {"type": "point"}
        base["encoding"] = enc_out
        return base

    if not measure_field:
        return None

    if horizontal:
        enc_out = {
            "x": _encoding_with_sanitized_title(
                measure_field, chart_rows, aggregate=None
            ),
            "y": _encoding_with_sanitized_title(cat, chart_rows),
        }
        cat_channel = "y"
    else:
        enc_out = {
            "x": _encoding_with_sanitized_title(cat, chart_rows),
            "y": _encoding_with_sanitized_title(
                measure_field, chart_rows, aggregate=None
            ),
        }
        cat_channel = "x"

    if series:
        enc_out["color"] = _encoding_with_sanitized_title(
            series, chart_rows, is_color=True
        )
    elif accent_color:
        enc_out["color"] = {"value": accent_color}

    if sort_eff != "none" and ordered_categories:
        enc_out[cat_channel]["sort"] = list(ordered_categories)

    if wtype == "bar":
        base.update(
            _bar_with_value_labels(
                {"type": "bar"},
                enc_out,
                cat_channel=cat_channel,
                rows=chart_rows,
                measure_field=measure_field,
                aggregate=None,
                tone=bg_tone,
            )
        )
    else:
        base["mark"] = {"type": wtype}
        base["encoding"] = enc_out
    return base


def _data_columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                ordered.append(k)
    return ordered


def _normalize_spec_field_name(field_name: str) -> str:
    """Map Lakeview names like sum(booking_count) to booking_count for column lookup."""
    m = _AGG_FN_RE.match(field_name.strip())
    if m:
        return m.group("inner").strip()
    return field_name.strip()


def _aggregate_from_spec_field_name(field_name: str | None) -> str | None:
    if not field_name:
        return None
    m = _AGG_FN_RE.match(field_name.strip())
    if not m:
        return None
    return _VEGA_AGG.get(m.group("fn").lower())


def _filter_nulls_for_chart(
    widget_spec: dict[str, Any],
    rows: list[dict[str, Any]],
    design: ChartDesign | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Drop rows with NULL in chart key fields. Returns (cleaned_rows, n_dropped)."""
    keys: set[str] = set()
    if design is not None:
        for fn in (design.category_field, design.value_field, design.series_field):
            if fn and str(fn).strip():
                keys.add(str(fn).strip())
    elif isinstance(widget_spec, dict):
        encodings = widget_spec.get("encodings") or {}
        if not isinstance(encodings, dict):
            encodings = {}
        for ch in ("x", "y", "color"):
            raw = encodings.get(ch)
            if not isinstance(raw, dict):
                continue
            fn, _t = _extract_field_and_title(raw)
            if fn and str(fn).strip():
                s = str(fn).strip()
                keys.add(s)
                inner = _normalize_spec_field_name(s)
                if inner:
                    keys.add(inner)
    keys.discard("")
    if not keys:
        return list(rows), 0

    cleaned: list[dict[str, Any]] = []
    dropped = 0
    for row in rows:
        bad = False
        for k in keys:
            if k not in row:
                continue
            val = row[k]
            if val is None or val == "":
                bad = True
                break
        if bad:
            dropped += 1
        else:
            cleaned.append(row)
    return cleaned, dropped


def _extract_field_and_title(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    fn = raw.get("fieldName")
    if fn is not None and str(fn).strip():
        disp = raw.get("displayName")
        title = str(disp) if disp is not None and str(disp) else None
        return str(fn).strip(), title
    fields = raw.get("fields")
    if isinstance(fields, list) and fields:
        first = fields[0]
        if isinstance(first, dict):
            fn2 = first.get("fieldName")
            if fn2 is not None and str(fn2).strip():
                disp = first.get("displayName")
                if disp is None or not str(disp):
                    disp = raw.get("displayName")
                title = str(disp) if disp is not None and str(disp) else None
                return str(fn2).strip(), title
    return None, None


def _encoding_matches_resolved(spec_field: str | None, resolved: str | None) -> bool:
    if not spec_field or not resolved:
        return False
    s = spec_field.strip()
    if s == resolved:
        return True
    return _normalize_spec_field_name(s) == resolved


def _read_stages_pair(
    encodings: dict[str, Any],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Source/target field names and titles from Lakeview sankey `stages` array."""
    raw_stages = encodings.get("stages")
    if not isinstance(raw_stages, list) or len(raw_stages) < 2:
        return None, None, None, None
    s0, s1 = raw_stages[0], raw_stages[1]
    if not isinstance(s0, dict) or not isinstance(s1, dict):
        return None, None, None, None
    f0, t0 = _extract_field_and_title(s0)
    f1, t1 = _extract_field_and_title(s1)
    return f0, f1, t0, t1


def _first_column_matching_types(
    columns: list[str],
    rows: list[dict[str, Any]],
    types: tuple[str, ...],
) -> str | None:
    for t in types:
        for col in columns:
            if infer_vega_type(_column_values(rows, col)) == t:
                return col
    return None


def _resolve_field(
    field_name: str | None,
    rows: list[dict[str, Any]],
    columns: list[str],
    role: Literal["x", "y", "color", "theta"],
) -> str | None:
    if field_name:
        fn = field_name.strip()
        if fn in columns:
            return fn
        stripped = _normalize_spec_field_name(fn)
        if stripped != fn and stripped in columns:
            return stripped
    if not columns:
        return None
    if role == "x":
        return (
            _first_column_matching_types(columns, rows, ("nominal",))
            or _first_column_matching_types(columns, rows, ("temporal",))
            or _first_column_matching_types(columns, rows, ("quantitative",))
            or columns[0]
        )
    if role == "color":
        return (
            _first_column_matching_types(columns, rows, ("nominal",))
            or _first_column_matching_types(columns, rows, ("temporal",))
            or _first_column_matching_types(columns, rows, ("quantitative",))
            or columns[0]
        )
    if role in ("y", "theta"):
        return (
            _first_column_matching_types(columns, rows, ("quantitative",))
            or _first_column_matching_types(columns, rows, ("temporal",))
            or columns[-1]
        )
    return columns[0]


def _encoding_field(
    field: str,
    rows: list[dict[str, Any]],
    *,
    aggregate: str | None = None,
    title: str | None = None,
    tooltip: bool = True,
    suppress_title: bool = False,
    is_color: bool = False,
) -> dict[str, Any]:
    t = infer_vega_type(_column_values(rows, field))
    ch: dict[str, Any] = {"field": field, "type": t, "tooltip": tooltip}
    if aggregate:
        ch["aggregate"] = aggregate
    if suppress_title:
        ch["title"] = None
    elif title:
        ch["title"] = title
    if is_color:
        ch["legend"] = {"title": None}
    return ch


def _encoding_with_sanitized_title(
    field: str,
    rows: list[dict[str, Any]],
    *,
    display_title: str | None = None,
    aggregate: str | None = None,
    is_color: bool = False,
) -> dict[str, Any]:
    clean = _sanitize_title(display_title)
    if clean is _SUPPRESS:
        return _encoding_field(
            field,
            rows,
            aggregate=aggregate,
            title=None,
            suppress_title=True,
            is_color=is_color,
        )
    return _encoding_field(
        field,
        rows,
        aggregate=aggregate,
        title=clean if clean else None,
        is_color=is_color,
    )


def _read_encoding(
    encodings: dict[str, Any],
    channel: str,
) -> tuple[str | None, str | None]:
    raw = encodings.get(channel)
    if not isinstance(raw, dict):
        return None, None
    return _extract_field_and_title(raw)


def _read_encoding_optional_field(
    encodings: dict[str, Any], channel: str
) -> str | None:
    fn, _t = _read_encoding(encodings, channel)
    return fn


def convert_widget_to_vegalite(
    widget_spec: dict[str, Any],
    query_data: list[dict[str, Any]],
    bg_tone: str = "light",
    palette: list[str] | None = None,
    design: ChartDesign | None = None,
    accent_color: str | None = None,
) -> dict[str, Any] | None:
    """
    Map a Lakeview widget spec and SQL rows to a Vega-Lite v5 spec dict.
    Returns None for unsupported types (counter, table) or empty data.

    `bg_tone` controls axis/legend/title text color in the rendered chart:
    pass 'dark' when the chart will sit on a dark slide background.

    `palette` overrides the default categorical color range (e.g. brand presets).

    When `design` is present and valid, it overrides heuristic chart construction.
    """
    if not query_data or not isinstance(widget_spec, dict):
        return None

    columns = _data_columns(query_data)
    if not columns:
        return None

    title_raw = widget_spec.get("title")
    title = (
        title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else None
    )

    if _design_is_usable(design, columns):
        assert design is not None
        return _convert_with_design(
            design,
            query_data,
            title,
            bg_tone=bg_tone,
            palette=palette,
            accent_color=accent_color,
        )

    wtype = str(widget_spec.get("widgetType") or "").strip().lower()
    if wtype in ("counter", "table"):
        return None

    encodings = widget_spec.get("encodings") or {}
    if not isinstance(encodings, dict):
        encodings = {}

    def _chart(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return _chart_base(rows, title, tone=bg_tone, palette=palette)

    x_field_raw, x_title = _read_encoding(encodings, "x")
    y_field_raw, y_title = _read_encoding(encodings, "y")
    c_field_raw, c_title = _read_encoding(encodings, "color")

    if wtype == "pie":
        angle_field_raw, angle_title = _read_encoding(encodings, "angle")
        cat_field_raw = c_field_raw or x_field_raw
        val_field_raw = angle_field_raw or y_field_raw
        cat_field = _resolve_field(cat_field_raw, query_data, columns, "color")
        val_field = _resolve_field(val_field_raw, query_data, columns, "theta")
        if not val_field or not cat_field:
            return None
        chart_rows = _maybe_roll_up_nominal_color(query_data, cat_field, val_field)
        base = _chart(chart_rows)
        if c_field_raw and _encoding_matches_resolved(c_field_raw, cat_field):
            cat_title = c_title
        elif x_field_raw and _encoding_matches_resolved(x_field_raw, cat_field):
            cat_title = x_title
        else:
            cat_title = None
        val_title = None
        if angle_field_raw and _encoding_matches_resolved(angle_field_raw, val_field):
            val_title = angle_title
        elif y_field_raw and _encoding_matches_resolved(y_field_raw, val_field):
            val_title = y_title
        theta_agg = _aggregate_from_spec_field_name(val_field_raw) or "sum"
        encoding = {
            "theta": _encoding_with_sanitized_title(
                val_field,
                chart_rows,
                display_title=val_title,
                aggregate=theta_agg,
                is_color=False,
            ),
            "color": _encoding_with_sanitized_title(
                cat_field,
                chart_rows,
                display_title=cat_title,
                is_color=True,
            ),
        }
        base["mark"] = {"type": "arc"}
        base["encoding"] = encoding
        return base

    if wtype == "heatmap":
        x_field = _resolve_field(x_field_raw, query_data, columns, "x")
        y_field = _resolve_field(y_field_raw, query_data, columns, "color")
        if x_field == y_field:
            y_field = _pick_second_nominal(columns, query_data, exclude=x_field)
        color_field = _resolve_field(c_field_raw, query_data, columns, "y")
        if not color_field or color_field in (x_field, y_field):
            color_field = None
            for col in columns:
                if col in (x_field, y_field):
                    continue
                if infer_vega_type(_column_values(query_data, col)) == "quantitative":
                    color_field = col
                    break
        if not x_field or not y_field or not color_field:
            return None
        base = _chart(query_data)
        x_t = x_title if x_field_raw and x_field == x_field_raw else None
        y_t = y_title if y_field_raw and y_field == y_field_raw else None
        c_t = c_title if c_field_raw and color_field == c_field_raw else None
        base["mark"] = {"type": "rect"}
        base["encoding"] = {
            "x": _encoding_with_sanitized_title(x_field, query_data, display_title=x_t),
            "y": _encoding_with_sanitized_title(y_field, query_data, display_title=y_t),
            "color": _encoding_with_sanitized_title(
                color_field, query_data, display_title=c_t, is_color=True
            ),
        }
        return base

    if wtype == "sankey":
        st_src, st_tgt, _st_src_t, _st_tgt_t = _read_stages_pair(encodings)
        val_field_raw, _val_title = _read_encoding(encodings, "value")
        src = st_src or (
            _read_encoding_optional_field(encodings, "source")
            or _read_encoding_optional_field(encodings, "from")
            or x_field_raw
        )
        tgt = st_tgt or (
            _read_encoding_optional_field(encodings, "target")
            or _read_encoding_optional_field(encodings, "to")
            or c_field_raw
        )
        val = val_field_raw or y_field_raw
        src_f = _resolve_field(src, query_data, columns, "x")
        tgt_f = _resolve_field(tgt, query_data, columns, "color")
        val_f = _resolve_field(val, query_data, columns, "y")
        if not src_f or not val_f:
            return None
        if not tgt_f or tgt_f == src_f:
            tgt_f = _pick_second_nominal(columns, query_data, exclude=src_f) or src_f
        chart_rows = _maybe_roll_up_nominal_color(query_data, tgt_f, val_f)
        base = _chart(chart_rows)
        val_agg = _aggregate_from_spec_field_name(val) or "sum"
        base["mark"] = {"type": "bar"}
        base["encoding"] = {
            "x": _encoding_field(src_f, chart_rows, title=None),
            "y": _encoding_field(val_f, chart_rows, aggregate=val_agg, title=None),
            "color": _encoding_field(tgt_f, chart_rows, title=None, is_color=True),
            "xOffset": {
                "field": tgt_f,
                "type": infer_vega_type(_column_values(chart_rows, tgt_f)),
                "tooltip": True,
            },
        }
        return base

    if wtype not in ("bar", "line", "area", "scatter"):
        return None

    x_field = _resolve_field(x_field_raw, query_data, columns, "x")
    y_field = _resolve_field(y_field_raw, query_data, columns, "y")
    if not x_field or not y_field:
        return None
    x_t = x_title if x_field_raw and x_field == x_field_raw else None
    y_t = y_title if y_field_raw and y_field == y_field_raw else None
    c_field = None
    c_t = None
    if c_field_raw:
        c_res = _resolve_field(c_field_raw, query_data, columns, "color")
        if c_res:
            c_field = c_res
            c_t = c_title if c_field == c_field_raw else None

    chart_rows = (
        _maybe_roll_up_nominal_color(query_data, c_field, y_field)
        if c_field
        else query_data
    )
    base = _chart(chart_rows)

    mark = "point" if wtype == "scatter" else wtype
    y_agg = _aggregate_from_spec_field_name(y_field_raw)
    enc_out: dict[str, Any] = {
        "x": _encoding_with_sanitized_title(x_field, chart_rows, display_title=x_t),
        "y": _encoding_with_sanitized_title(
            y_field, chart_rows, display_title=y_t, aggregate=y_agg
        ),
    }
    if c_field:
        enc_out["color"] = _encoding_with_sanitized_title(
            c_field, chart_rows, display_title=c_t, is_color=True
        )

    if wtype == "bar":
        x_type = enc_out["x"].get("type")
        cat_channel = "x" if x_type == "nominal" else "y"
        measure_channel = "y" if cat_channel == "x" else "x"
        measure_part = enc_out.get(measure_channel, {})
        m_field = (
            measure_part.get("field", y_field)
            if isinstance(measure_part, dict)
            else y_field
        )
        m_agg = (
            measure_part.get("aggregate", y_agg)
            if isinstance(measure_part, dict)
            else y_agg
        )
        base.update(
            _bar_with_value_labels(
                {"type": "bar"},
                enc_out,
                cat_channel=cat_channel,
                rows=chart_rows,
                measure_field=str(m_field),
                aggregate=m_agg if isinstance(m_agg, str) else None,
                tone=bg_tone,
            )
        )
    else:
        base["mark"] = {"type": mark}
        base["encoding"] = enc_out
    return base


def _pick_second_nominal(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    exclude: str,
) -> str | None:
    for col in columns:
        if col == exclude:
            continue
        t = infer_vega_type(_column_values(rows, col))
        if t in ("nominal", "temporal"):
            return col
    for col in columns:
        if col != exclude:
            return col
    return None


def _muted_accent_color(*, tone: str) -> str:
    return "rgba(255,255,255,0.45)" if tone == "dark" else "rgba(15,15,15,0.30)"


def _accent_from_palette(palette: list[str] | None) -> str:
    if palette:
        return palette[0]
    return _CATEGORY_PALETTE[0]


def _resolve_encoding_channel_field(enc_part: Any) -> str | None:
    if not isinstance(enc_part, Mapping):
        return None
    fn = enc_part.get("field")
    if isinstance(fn, str) and fn.strip():
        return fn.strip()
    return None


def _quantitative_axis_and_field(enc: dict[str, Any]) -> tuple[str, str | None]:
    """Return the measure axis/field; prefer y when both axes are quantitative."""
    for ch in ("y", "x"):
        part = enc.get(ch)
        if isinstance(part, dict) and part.get("type") == "quantitative":
            fn = _resolve_encoding_channel_field(part)
            if fn:
                return ch, fn
    yf = _resolve_encoding_channel_field(enc.get("y"))
    if yf:
        return "y", yf
    xf = _resolve_encoding_channel_field(enc.get("x"))
    return "x", xf


def _datum_expr_field(field: str) -> str:
    """JavaScript-safe Vega expression path for datum.<col>."""
    if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", field):
        return f"datum.{field}"
    esc = field.replace("\\", "\\\\").replace("'", "\\'")
    return f"datum['{esc}']"


def _highlight_condition_expr(field: str, values: list[str]) -> str:
    dref = _datum_expr_field(field)
    parts: list[str] = []
    for raw in values:
        if raw is None:
            continue
        s = str(raw).replace("\\", "\\\\").replace("'", "\\'")
        parts.append(f"{dref} === '{s}'")
    return " || ".join(parts) if parts else ""


def _row_values_for_field(rows: list[dict[str, Any]], field: str) -> list[Any]:
    out: list[Any] = []
    for row in rows:
        if field not in row:
            continue
        out.append(row[field])
    return out


def _numeric_extent(
    rows: list[dict[str, Any]], field: str
) -> tuple[float, float] | None:
    vals: list[float] = []
    for row in rows:
        if field not in row:
            continue
        v = row[field]
        if _is_number(v):
            vals.append(float(v))
        elif isinstance(v, str) and v.strip():
            try:
                vals.append(float(v))
            except ValueError:
                pass
    if len(vals) < 1:
        return None
    return min(vals), max(vals)


def _ordinal_domain(rows: list[dict[str, Any]], field: str) -> list[Any]:
    seen: set[str] = set()
    domain: list[Any] = []
    for row in rows:
        if field not in row:
            continue
        v = row[field]
        key = json.dumps(v, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        domain.append(v)
    return domain


def _promote_spec_to_layer(spec: dict[str, Any]) -> None:
    if "layer" in spec:
        return
    enc = spec.get("encoding")
    mk = spec.get("mark")
    if not isinstance(enc, dict) or not isinstance(mk, dict):
        return
    del spec["encoding"]
    del spec["mark"]
    spec["layer"] = [{"mark": mk, "encoding": enc}]


def _layer_first_encoding(spec: dict[str, Any]) -> dict[str, Any] | None:
    ly = spec.get("layer")
    if isinstance(ly, list) and ly:
        first = ly[0]
        if isinstance(first, dict):
            enc = first.get("encoding")
            if isinstance(enc, dict):
                return enc
    enc = spec.get("encoding")
    return enc if isinstance(enc, dict) else None


def apply_augmentation_to_spec(
    vl_spec: dict[str, Any],
    rows: list[dict[str, Any]],
    augmentation: ChartAugmentation,
    *,
    tone: str = "light",
    palette: list[str] | None = None,
    tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a new Vega-Lite spec with augmentation applied.

    Uses ``rows`` as authoritative validation data — never ``vl_spec.data``.
    Failures are silent partial no-ops; malformed inputs return an unchanged copy.
    """
    try:
        out = copy.deepcopy(vl_spec)
        if not isinstance(out, dict) or not rows:
            return out

        enc = _layer_first_encoding(out)
        if enc is None:
            return out

        accent = _accent_from_palette(palette)
        muted = _muted_accent_color(tone=tone)
        tok = tokens or {}

        x_field = _resolve_encoding_channel_field(enc.get("x"))
        qty_axis, qty_field = _quantitative_axis_and_field(enc)

        # --- highlight ---
        hl = augmentation.highlight
        if hl is not None and hl.field and hl.values:
            try:
                h_field = str(hl.field).strip()
                # Loose field match: if LLM-supplied field doesn't exist in rows,
                # fall back to the chart's color field then x field. The LLM's
                # intent for a bar chart is almost always "highlight these
                # categories" regardless of whether it guessed the field name.
                if h_field not in (rows[0] if rows else {}):
                    color_enc_probe = enc.get("color")
                    color_f = (
                        _resolve_encoding_channel_field(color_enc_probe)
                        if isinstance(color_enc_probe, Mapping)
                        else None
                    )
                    if color_f and color_f in (rows[0] if rows else {}):
                        h_field = color_f
                    elif x_field and x_field in (rows[0] if rows else {}):
                        h_field = x_field
                if not h_field or not any(h_field in r for r in rows):
                    raise ValueError("missing highlight column")
                valid_vals = []
                col_vals = _row_values_for_field(rows, h_field)
                for candidate in hl.values:
                    candidate_s = str(candidate)
                    # exact or string-equal or substring match (handles "50代"
                    # matching "50代" even if LLM included trailing whitespace)
                    if any(
                        cv == candidate
                        or str(cv).strip() == candidate_s.strip()
                        or candidate_s.strip() in str(cv)
                        for cv in col_vals
                    ):
                        # Use the actual data value, not the LLM-supplied one
                        for cv in col_vals:
                            if (
                                cv == candidate
                                or str(cv).strip() == candidate_s.strip()
                                or candidate_s.strip() in str(cv)
                            ):
                                valid_vals.append(str(cv))
                                break
                if not valid_vals:
                    raise ValueError("no matching highlight values")

                color_enc = enc.get("color")
                color_field = (
                    _resolve_encoding_channel_field(color_enc)
                    if isinstance(color_enc, Mapping)
                    else None
                )
                const_color = (
                    isinstance(color_enc, Mapping)
                    and "field" not in color_enc
                    and "value" in color_enc
                )
                no_real_color = color_enc is None or const_color

                if color_field and not const_color:
                    if h_field != color_field:
                        raise ValueError("highlight field mismatch vs color")
                    domain = _ordinal_domain(rows, color_field)
                    ranges = [
                        accent
                        if any(str(cat) == hv or cat == hv for hv in valid_vals)
                        else muted
                        for cat in domain
                    ]
                    ce = enc.setdefault("color", {})
                    if isinstance(ce, dict):
                        ce["scale"] = {"domain": domain, "range": ranges}
                elif no_real_color:
                    # Use h_field directly (already loose-matched above) — it
                    # might be x_field or any column that exists in rows.
                    if not h_field:
                        raise ValueError("no field for highlight expression")
                    expr = _highlight_condition_expr(h_field, valid_vals)
                    if not expr:
                        raise ValueError("empty expr")
                    enc["color"] = {
                        "condition": {"test": expr, "value": accent},
                        "value": muted,
                    }
            except Exception:
                pass

        # --- y_range ---
        yr = augmentation.y_range
        if yr is not None and len(yr) == 2 and qty_field:
            try:
                lo_a, hi_a = float(yr[0]), float(yr[1])
                ext = _numeric_extent(rows, qty_field)
                if ext is None:
                    raise ValueError("no numeric measure")
                d_lo, d_hi = ext
                if lo_a >= hi_a:
                    raise ValueError("inverted requested range")
                lo_c = max(lo_a, d_lo)
                hi_c = min(hi_a, d_hi)
                if lo_c >= hi_c:
                    raise ValueError("collapsed clamp range")
                qty_enc = enc.setdefault(qty_axis, {})
                if isinstance(qty_enc, dict):
                    qty_enc.setdefault("scale", {})
                    if isinstance(qty_enc["scale"], dict):
                        qty_enc["scale"]["domain"] = [
                            int(lo_c) if lo_c == int(lo_c) else lo_c,
                            int(hi_c) if hi_c == int(hi_c) else hi_c,
                        ]
            except Exception:
                pass

        # --- value_format ---
        vf = augmentation.value_format
        if vf and vf in ("currency", "percent", "count", "duration"):
            try:
                fmt_map = {
                    "percent": ".1%",
                    "count": ",d",
                    "duration": ",.0f",
                }
                if vf == "currency":
                    cur = str(tok.get("currency", "") or "").strip().upper()
                    axis_fmt = "¥,.0f" if cur == "JPY" else "$,.0f"
                else:
                    axis_fmt = fmt_map[vf]
                for ch in ("x", "y"):
                    part = enc.get(ch)
                    if isinstance(part, dict) and part.get("type") == "quantitative":
                        part.setdefault("axis", {})
                        if isinstance(part["axis"], dict):
                            part["axis"]["format"] = axis_fmt
            except Exception:
                pass

        # Reference lines are the only augmentation that promotes the spec
        # to a layered composition. The `caption` field on the augmentation
        # is used by Opus in slide prose instead.
        ref_ln = augmentation.reference_line
        if ref_ln is not None:
            ly_existing = out.get("layer")
            if isinstance(ly_existing, list) and len(ly_existing) > 1:
                out["layer"] = [
                    ly_existing[0],
                    *[ly for ly in ly_existing[1:] if _is_value_label_layer(ly)],
                ]
            _promote_spec_to_layer(out)
            layers = out.get("layer")
            if not isinstance(layers, list) or not layers:
                return out

            base_enc = (
                layers[0].get("encoding") if isinstance(layers[0], dict) else None
            )
            if not isinstance(base_enc, dict):
                return out
            xf = _resolve_encoding_channel_field(base_enc.get("x"))
            yf = _resolve_encoding_channel_field(base_enc.get("y"))
            qty_axis, qty_field = _quantitative_axis_and_field(base_enc)

            try:
                axis = str(ref_ln.axis or "").strip().lower()
                val_raw = ref_ln.value
                axis_part = base_enc.get(axis) if axis in ("x", "y") else None
                if (
                    not isinstance(axis_part, dict)
                    or axis_part.get("type") != "quantitative"
                ):
                    axis = qty_axis
                if axis == "y":
                    field_for_rule = yf or qty_field
                    if not field_for_rule:
                        raise ValueError("missing y")
                    ext = _numeric_extent(rows, field_for_rule)
                    if ext is None:
                        raise ValueError("no numeric extent")
                    v = float(val_raw)
                    v = max(ext[0], min(ext[1], v))
                    v_disp = int(v) if v == int(v) else v
                    layers.append(
                        {
                            "mark": {
                                "type": "rule",
                                "strokeDash": [4, 4],
                                "color": accent,
                                "strokeWidth": 1,
                            },
                            "encoding": {"y": {"datum": v_disp}},
                        }
                    )
                    if xf:
                        layers.append(
                            {
                                "mark": {
                                    "type": "text",
                                    "color": accent,
                                    "fontWeight": 500,
                                    "align": "left",
                                    "baseline": "bottom",
                                    "dx": 6,
                                    "dy": -6,
                                },
                                "encoding": {
                                    "x": {"datum": _ordinal_domain(rows, xf)[-1]},
                                    "y": {"datum": v_disp},
                                    "text": {"value": str(ref_ln.label)},
                                },
                            }
                        )
                elif axis == "x":
                    field_for_rule = xf or qty_field
                    if not field_for_rule:
                        raise ValueError("missing x")
                    domain_x = _ordinal_domain(rows, field_for_rule)
                    if domain_x:
                        try:
                            v_raw_num = float(val_raw)
                            ext_x = _numeric_extent(rows, field_for_rule)
                            if ext_x is None:
                                raise ValueError("non-numeric x band")
                            v = max(ext_x[0], min(ext_x[1], v_raw_num))
                            datum_x: Any = int(v) if v == int(v) else v
                        except Exception:
                            datum_x = val_raw
                    else:
                        ext_x = _numeric_extent(rows, field_for_rule)
                        if ext_x is None:
                            raise ValueError("non-numeric x")
                        v = max(ext_x[0], min(ext_x[1], float(val_raw)))
                        datum_x = int(v) if v == int(v) else v
                    layers.append(
                        {
                            "mark": {
                                "type": "rule",
                                "strokeDash": [4, 4],
                                "color": accent,
                                "strokeWidth": 1,
                            },
                            "encoding": {"x": {"datum": datum_x}},
                        }
                    )
            except Exception:
                pass

        return out
    except Exception:
        return copy.deepcopy(vl_spec)
