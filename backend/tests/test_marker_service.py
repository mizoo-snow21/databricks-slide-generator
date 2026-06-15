from services.marker_service import (
    decode_note,
    encode_note,
    generate_comment_id,
    generate_element_id,
    insert_marker,
    list_markers,
    remove_marker,
)


def test_id_format():
    cid = generate_comment_id()
    assert cid.startswith("c-") and len(cid) >= 6
    eid = generate_element_id()
    assert eid.startswith("el-") and len(eid) >= 7


def test_encode_decode_japanese():
    note = "もっとインパクト強く"
    enc = encode_note(note)
    assert "もっと" not in enc
    assert "-->" not in enc
    assert decode_note(enc) == note


def test_encode_strips_dangerous_sequences():
    enc = encode_note('text with --> and "quotes"')
    assert "-->" not in enc
    assert '"' not in enc


def test_insert_marker_as_first_child():
    html = '<html><body><h1 data-osd-id="el-7a3f">Title</h1></body></html>'
    out, marker = insert_marker(
        html, target_id="el-7a3f", note="redder", ts="2026-05-07T12:00:00Z"
    )
    assert '<h1 data-osd-id="el-7a3f"><!--osd-comment' in out
    assert marker.id.startswith("c-")


def test_list_markers_returns_all():
    html = """<html><body>
      <h1 data-osd-id="el-1aaa"><!--osd-comment id="c-aaaa" target="el-1aaa" ts="2026-01-01T00:00:00Z" note="x"-->A</h1>
      <p data-osd-id="el-2bbb"><!--osd-comment id="c-bbbb" target="el-2bbb" ts="2026-01-02T00:00:00Z" note="y"-->B</p>
    </body></html>"""
    markers = list_markers(html)
    ids = [m.id for m in markers]
    assert "c-aaaa" in ids and "c-bbbb" in ids


def test_remove_marker_by_id():
    html = '<html><body><h1 data-osd-id="el-1aaa"><!--osd-comment id="c-aaaa" target="el-1aaa" ts="2026-01-01T00:00:00Z" note="x"-->A</h1></body></html>'
    out = remove_marker(html, comment_id="c-aaaa")
    assert "osd-comment" not in out
    assert '<h1 data-osd-id="el-1aaa">A</h1>' in out


def test_insert_marker_target_not_found_raises():
    import pytest

    with pytest.raises(ValueError):
        insert_marker(
            "<html><body></body></html>", target_id="el-missing", note="x", ts="now"
        )
