"""osd-comment marker insert/parse/remove on an HTML deck document."""

from __future__ import annotations

import re
import secrets
import urllib.parse
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment

OSD_COMMENT_RE = re.compile(
    r'osd-comment\s+id="(c-[a-f0-9]{4,8})"\s+target="([^"]+)"\s+ts="([^"]+)"\s+note="([^"]*)"'
)


@dataclass
class Marker:
    id: str
    target_id: str
    ts: str
    note: str  # decoded


def generate_comment_id() -> str:
    return "c-" + secrets.token_hex(4)


def generate_element_id() -> str:
    return "el-" + secrets.token_hex(4)


def encode_note(note: str) -> str:
    """Percent-encode UTF-8. Strips quotes and `-->` so the marker stays valid HTML."""
    return urllib.parse.quote(note, safe="")


def decode_note(encoded: str) -> str:
    return urllib.parse.unquote(encoded)


def _build_marker_text(
    comment_id: str, target_id: str, ts: str, encoded_note: str
) -> str:
    return f'osd-comment id="{comment_id}" target="{target_id}" ts="{ts}" note="{encoded_note}"'


def insert_marker(
    html_doc: str, target_id: str, note: str, ts: str
) -> tuple[str, Marker]:
    soup = BeautifulSoup(html_doc, "html.parser")
    target = soup.find(attrs={"data-osd-id": target_id})
    if target is None:
        raise ValueError(f"Target element data-osd-id={target_id!r} not found")

    cid = generate_comment_id()
    encoded = encode_note(note)
    text = _build_marker_text(cid, target_id, ts, encoded)
    target.insert(0, Comment(text))
    return str(soup), Marker(id=cid, target_id=target_id, ts=ts, note=note)


def list_markers(html_doc: str) -> list[Marker]:
    soup = BeautifulSoup(html_doc, "html.parser")
    out: list[Marker] = []
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        m = OSD_COMMENT_RE.fullmatch(str(c).strip())
        if m:
            out.append(
                Marker(
                    id=m.group(1),
                    target_id=m.group(2),
                    ts=m.group(3),
                    note=decode_note(m.group(4)),
                )
            )
    return out


def find_marker(html_doc: str, comment_id: str) -> Marker | None:
    for m in list_markers(html_doc):
        if m.id == comment_id:
            return m
    return None


def remove_marker(html_doc: str, comment_id: str) -> str:
    soup = BeautifulSoup(html_doc, "html.parser")
    for c in list(soup.find_all(string=lambda s: isinstance(s, Comment))):
        m = OSD_COMMENT_RE.fullmatch(str(c).strip())
        if m and m.group(1) == comment_id:
            c.extract()
    return str(soup)
