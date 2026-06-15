"""Tests for Lakeview → Vega-Lite conversion."""

from __future__ import annotations

import json

from models import (
    ChartAugmentation,
    ChartHighlight,
    ChartReferenceLine,
)
from services.vegalite_service import (
    _chart_base,
    _encoding_field,
    _filter_nulls_for_chart,
    _is_ascii_only,
    _truncate_top_n_with_other,
    _vega_lite_config,
    apply_augmentation_to_spec,
    convert_widget_to_vegalite,
    infer_vega_type,
    widget_spec_from_columns,
)


def test_chart_base_default_width_is_pixels() -> None:
    out = _chart_base([{}], "title")
    assert out["width"] == 720
    assert out["width"] != "container"


def test_infer_vega_type_quantitative() -> None:
    assert infer_vega_type([1, 2, "3"]) == "quantitative"


def test_infer_vega_type_temporal() -> None:
    assert infer_vega_type(["2024-01-01", "2024-02-01"]) == "temporal"


def test_infer_vega_type_nominal() -> None:
    assert infer_vega_type(["east", "west"]) == "nominal"


def test_convert_bar() -> None:
    spec = {
        "version": 3,
        "widgetType": "bar",
        "title": "Rev",
        "encodings": {
            "x": {"fieldName": "month", "displayName": "Month"},
            "y": {"fieldName": "revenue", "displayName": "Revenue"},
        },
    }
    data = [{"month": "Jan", "revenue": 10}, {"month": "Feb", "revenue": 20}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert vl["mark"]["type"] == "bar"
    assert vl["encoding"]["x"]["field"] == "month"
    assert vl["encoding"]["y"]["field"] == "revenue"
    assert vl["title"] == "Rev"


def test_convert_pie() -> None:
    spec = {
        "widgetType": "pie",
        "encodings": {
            "x": {"fieldName": "region", "displayName": "Region"},
            "y": {"fieldName": "rev", "displayName": "Revenue"},
        },
    }
    data = [{"region": "A", "rev": 100}, {"region": "B", "rev": 200}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert vl["mark"]["type"] == "arc"
    assert vl["encoding"]["color"]["field"] == "region"
    assert vl["encoding"]["theta"]["field"] == "rev"


def test_convert_counter_skipped() -> None:
    assert convert_widget_to_vegalite({"widgetType": "counter"}, [{"a": 1}]) is None


def test_convert_empty_data() -> None:
    assert convert_widget_to_vegalite({"widgetType": "bar"}, []) is None


def test_vega_lite_config_text_mark_color_tone() -> None:
    light_cfg = _vega_lite_config("light")
    assert light_cfg["text"]["color"] == "rgba(15,15,15,0.95)"
    dark_cfg = _vega_lite_config("dark")
    assert dark_cfg["text"]["color"] == "rgba(255,255,255,0.98)"


def test_vega_lite_config_suppresses_legend_title() -> None:
    cfg = _vega_lite_config("light")
    assert cfg["legend"]["title"] is None


def test_vega_lite_config_legend_orient_bottom() -> None:
    cfg = _vega_lite_config("light")
    assert cfg["legend"]["orient"] == "bottom"


def test_vega_lite_config_uses_custom_palette_when_provided() -> None:
    custom = ["#111111", "#222222", "#333333"]
    cfg = _vega_lite_config("light", palette=custom)
    assert cfg["range"]["category"] == custom


def test_vega_lite_config_quantitative_axis_format_si() -> None:
    cfg = _vega_lite_config("light")
    fmt = cfg.get("axisQuantitative", {}).get("format")
    if fmt is None:
        fmt = cfg.get("axis", {}).get("format")
    assert fmt is not None and "~s" in str(fmt)


def test_vega_lite_config_axis_tick_density() -> None:
    cfg = _vega_lite_config("light")
    axis = cfg["axis"]
    assert axis["tickCount"] == 6
    assert axis["labelOverlap"] == "greedy"


def test_truncate_top_n_with_other_groups_rest() -> None:
    rows = [{"cat": f"C{i}", "v": float(i)} for i in range(12)]
    out = _truncate_top_n_with_other(rows, "cat", "v", n=7)
    dist_cats = {r["cat"] for r in out}
    assert len(dist_cats) == 8
    assert "Other" in dist_cats
    top7 = {f"C{i}" for i in range(5, 12)}
    assert top7 <= dist_cats
    low5 = {f"C{i}" for i in range(5)}
    assert not (low5 & dist_cats)


def test_truncate_top_n_with_other_no_op_when_under_threshold() -> None:
    rows = [{"cat": f"C{i}", "v": 1.0} for i in range(5)]
    out = _truncate_top_n_with_other(rows, "cat", "v", n=7)
    assert out == rows


def test_convert_widget_to_vegalite_omits_optional_kwargs() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "a"},
            "y": {"fieldName": "b"},
        },
    }
    data = [{"a": "x", "b": 1}]
    assert convert_widget_to_vegalite(spec, data) is not None


def test_filter_nulls_for_chart_drops_null_color() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "a"},
            "y": {"fieldName": "b"},
            "color": {"fieldName": "c"},
        },
    }
    rows = [
        {"a": "x", "b": 1, "c": None},
        {"a": "y", "b": 2, "c": "red"},
    ]
    cleaned, n_dropped = _filter_nulls_for_chart(spec, rows)
    assert n_dropped == 1
    assert cleaned == [rows[1]]


def test_filter_nulls_for_chart_drops_null_x_y() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {"x": {"fieldName": "a"}, "y": {"fieldName": "b"}},
    }
    rows = [
        {"a": None, "b": 1},
        {"a": "z", "b": None},
        {"a": "ok", "b": 3},
    ]
    cleaned, n_dropped = _filter_nulls_for_chart(spec, rows)
    assert n_dropped == 2
    assert cleaned == [rows[2]]


def test_filter_nulls_for_chart_no_op_when_no_nulls() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {"x": {"fieldName": "a"}, "y": {"fieldName": "b"}},
    }
    rows = [{"a": "x", "b": 1}, {"a": "y", "b": 2}]
    cleaned, n_dropped = _filter_nulls_for_chart(spec, rows)
    assert n_dropped == 0
    assert cleaned == rows


def test_is_ascii_only_basic() -> None:
    assert _is_ascii_only(None) is True
    assert _is_ascii_only("") is True
    assert _is_ascii_only("ASCII only") is True
    assert _is_ascii_only("日本語") is False
    assert _is_ascii_only("Mix日本") is False


def test_convert_strips_japanese_chart_title_omits_top_level_title() -> None:
    spec = {
        "widgetType": "bar",
        "title": "セグメント構成比",
        "encodings": {
            "x": {"fieldName": "month", "displayName": "Month"},
            "y": {"fieldName": "revenue", "displayName": "Revenue"},
        },
    }
    data = [{"month": "Jan", "revenue": 10}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert "title" not in vl


def test_convert_strips_japanese_axis_title_x_emits_null() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "age_band", "displayName": "年齢層"},
            "y": {"fieldName": "revenue", "displayName": "Revenue"},
        },
    }
    data = [{"age_band": "20代", "revenue": 10}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert "title" in vl["encoding"]["x"]
    assert vl["encoding"]["x"]["title"] is None


def test_convert_strips_japanese_axis_title_y_emits_null() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "month", "displayName": "Month"},
            "y": {"fieldName": "avg_pay", "displayName": "平均決済額"},
        },
    }
    data = [{"month": "Jan", "avg_pay": 100}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert "title" in vl["encoding"]["y"]
    assert vl["encoding"]["y"]["title"] is None


def test_convert_strips_japanese_color_legend_title_emits_null() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "month", "displayName": "Month"},
            "y": {"fieldName": "revenue", "displayName": "Revenue"},
            "color": {"fieldName": "segment", "displayName": "セグメント"},
        },
    }
    data = [
        {"month": "Jan", "revenue": 10, "segment": "A"},
        {"month": "Feb", "revenue": 20, "segment": "B"},
    ]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    enc_color = vl["encoding"]["color"]
    assert "title" in enc_color
    assert enc_color["title"] is None
    assert "legend" in enc_color
    assert enc_color["legend"]["title"] is None


def test_convert_preserves_ascii_chart_title() -> None:
    spec = {
        "widgetType": "bar",
        "title": "Revenue",
        "encodings": {
            "x": {"fieldName": "month", "displayName": "Month"},
            "y": {"fieldName": "rev", "displayName": "Rev"},
        },
    }
    data = [{"month": "Jan", "rev": 10}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert vl["title"] == "Revenue"


def test_convert_preserves_ascii_axis_titles() -> None:
    spec = {
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "m", "displayName": "Month"},
            "y": {"fieldName": "s", "displayName": "Sales"},
        },
    }
    data = [{"m": "Jan", "s": 1}]
    vl = convert_widget_to_vegalite(spec, data)
    assert vl is not None
    assert vl["encoding"]["x"]["title"] == "Month"
    assert vl["encoding"]["y"]["title"] == "Sales"


def test_encoding_field_suppress_title_emits_explicit_null() -> None:
    rows = [{"col": "a"}]
    result = _encoding_field("col", rows, title=None, suppress_title=True)
    assert "title" in result
    assert result["title"] is None


def test_encoding_field_color_with_japanese_emits_null_legend_title() -> None:
    rows = [{"col": "a"}]
    result = _encoding_field(
        "col", rows, title=None, suppress_title=True, is_color=True
    )
    assert result["legend"]["title"] is None


def test_apply_augmentation_highlight_emits_color_condition() -> None:
    vl = {
        "encoding": {
            "x": {"field": "seg", "type": "nominal"},
            "y": {"field": "v", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"seg": "A", "v": 1}, {"seg": "B", "v": 2}]
    aug = ChartAugmentation(
        widget_id="w1",
        highlight=ChartHighlight(field="seg", values=["A"]),
    )
    out = apply_augmentation_to_spec(vl, rows, aug)
    color = out["encoding"]["color"]
    assert "condition" in color
    assert "test" in color["condition"]
    assert "datum.seg" in color["condition"]["test"]


def test_apply_augmentation_y_range_sets_scale_domain() -> None:
    vl = {
        "encoding": {
            "x": {"field": "seg", "type": "nominal"},
            "y": {"field": "rev", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"seg": "A", "rev": 0}, {"seg": "B", "rev": 200}]
    aug = ChartAugmentation(widget_id="w", y_range=(10, 100))
    out = apply_augmentation_to_spec(vl, rows, aug)
    assert out["encoding"]["y"]["scale"]["domain"] == [10, 100]


def test_apply_augmentation_reference_line_layers_rule() -> None:
    vl = {
        "encoding": {
            "x": {"field": "month", "type": "nominal"},
            "y": {"field": "rev", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"month": "Jan", "rev": 10}, {"month": "Feb", "rev": 90}]
    aug = ChartAugmentation(
        widget_id="w",
        reference_line=ChartReferenceLine(axis="y", value=50, label="Target"),
    )
    out = apply_augmentation_to_spec(vl, rows, aug)
    rules = [
        layer for layer in out["layer"] if layer.get("mark", {}).get("type") == "rule"
    ]
    assert rules
    assert rules[0]["encoding"]["y"]["datum"] == 50


def test_apply_augmentation_value_format_currency_emits_jpy_when_token_says_jpy() -> (
    None
):
    vl = {
        "encoding": {
            "x": {"field": "seg", "type": "nominal"},
            "y": {"field": "amt", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"seg": "A", "amt": 100}]
    aug = ChartAugmentation(widget_id="w", value_format="currency")
    out = apply_augmentation_to_spec(vl, rows, aug, tokens={"currency": "JPY"})
    fmt = out["encoding"]["y"]["axis"]["format"]
    assert "¥" in fmt


def test_apply_augmentation_skips_invalid_highlight_field() -> None:
    vl = {
        "encoding": {
            "x": {"field": "seg", "type": "nominal"},
            "y": {"field": "v", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"seg": "A", "v": 1}]
    aug = ChartAugmentation(
        widget_id="w",
        highlight=ChartHighlight(field="nope", values=["x"]),
    )
    out = apply_augmentation_to_spec(vl, rows, aug)
    assert "color" not in out["encoding"]


def test_apply_augmentation_skips_invalid_y_range() -> None:
    vl = {
        "encoding": {
            "x": {"field": "seg", "type": "nominal"},
            "y": {"field": "rev", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"seg": "A", "rev": 10}]
    aug = ChartAugmentation(widget_id="w", y_range=(100, 10))
    out = apply_augmentation_to_spec(vl, rows, aug)
    assert out["encoding"]["y"].get("scale") is None


def test_widget_spec_temporal_x_is_line() -> None:
    rows = [
        {"month": "2024-01-01", "revenue": 100},
        {"month": "2024-02-01", "revenue": 150},
        {"month": "2024-03-01", "revenue": 120},
    ]
    spec = widget_spec_from_columns("Monthly revenue", ["month", "revenue"], rows)
    assert spec["widgetType"] == "line"
    assert spec["title"] == "Monthly revenue"
    assert spec["encodings"]["x"]["fieldName"] == "month"
    assert spec["encodings"]["y"]["fieldName"] == "revenue"


def test_widget_spec_nominal_numeric_is_bar() -> None:
    rows = [
        {"category": "A", "sales": 10},
        {"category": "B", "sales": 20},
        {"category": "C", "sales": 15},
    ]
    spec = widget_spec_from_columns("Sales by category", ["category", "sales"], rows)
    assert spec["widgetType"] == "bar"
    assert spec["encodings"]["x"]["fieldName"] == "category"
    assert spec["encodings"]["y"]["fieldName"] == "sales"


def test_widget_spec_two_numeric_nominal_is_bar() -> None:
    rows = [
        {"region": "East", "q1": 10, "q2": 12},
        {"region": "West", "q1": 8, "q2": 9},
    ]
    spec = widget_spec_from_columns("Regional", ["region", "q1", "q2"], rows)
    assert spec["widgetType"] == "bar"
    assert spec["encodings"]["x"]["fieldName"] == "region"
    assert spec["encodings"]["y"]["fieldName"] == "q1"
    assert "color" not in spec["encodings"]


def test_widget_spec_color_added_for_second_nominal() -> None:
    rows = [
        {"region": "East", "segment": "Retail", "sales": 100},
        {"region": "West", "segment": "Wholesale", "sales": 80},
    ]
    spec = widget_spec_from_columns(
        "Sales breakdown", ["region", "segment", "sales"], rows
    )
    assert spec["widgetType"] == "bar"
    assert spec["encodings"]["x"]["fieldName"] == "region"
    assert spec["encodings"]["y"]["fieldName"] == "sales"
    assert spec["encodings"]["color"]["fieldName"] == "segment"


def test_widget_spec_no_numeric_returns_no_y() -> None:
    rows = [{"a": "x", "b": "y"}, {"a": "p", "b": "q"}]
    spec = widget_spec_from_columns("Nominal only", ["a", "b"], rows)
    assert "y" not in spec["encodings"]
    assert convert_widget_to_vegalite(spec, rows) is None


def test_widget_spec_then_convert_renders() -> None:
    rows = [
        {"region": "North", "amount": 50},
        {"region": "South", "amount": 70},
    ]
    spec = widget_spec_from_columns("Amounts", ["region", "amount"], rows)
    vl = convert_widget_to_vegalite(spec, rows)
    assert vl is not None
    assert isinstance(vl, dict)
    assert vl["mark"]["type"] == "bar"
    assert vl["encoding"]["x"]["field"] == "region"
    assert vl["encoding"]["y"]["field"] == "amount"


def test_apply_augmentation_idempotent() -> None:
    vl = {
        "encoding": {
            "x": {"field": "month", "type": "nominal"},
            "y": {"field": "rev", "type": "quantitative"},
        },
        "mark": {"type": "bar"},
    }
    rows = [{"month": "Jan", "rev": 10}, {"month": "Feb", "rev": 40}]
    aug = ChartAugmentation(
        widget_id="w",
        highlight=ChartHighlight(field="month", values=["Feb"]),
    )
    once = apply_augmentation_to_spec(vl, rows, aug)
    twice = apply_augmentation_to_spec(once, rows, aug)
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)
