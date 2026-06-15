"""Tests for PPTX temp storage and finalize flow."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest

from services import pptx_template_storage as storage


@pytest.fixture
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "TEMP_ROOT", tmp_path / "pptx-tmp")
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path / "pptx-perm")


def test_save_and_get_temp_path(isolated_storage: None) -> None:
    uid = str(uuid.uuid4())
    data = b"PPTX\x00\x01fake"
    path = storage.save_pptx_temp(uid, data)
    assert path.is_file()
    got = storage.get_pptx_temp_path(uid)
    assert got == path
    assert got is not None
    assert got.read_bytes() == data


def test_finalize_moves_to_permanent(isolated_storage: None) -> None:
    uid = str(uuid.uuid4())
    tid = str(uuid.uuid4())
    storage.save_pptx_temp(uid, b"hello pptx")
    perm = storage.finalize_pptx_for_template(uid, tid)
    assert perm is not None
    assert os.path.isfile(perm)
    assert storage.get_pptx_temp_path(uid) is None
    with open(perm, "rb") as f:
        assert f.read() == b"hello pptx"


def test_cleanup_old_temp_files(isolated_storage: None) -> None:
    storage.TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    stale = storage.TEMP_ROOT / "old.pptx"
    fresh = storage.TEMP_ROOT / "new.pptx"
    stale.write_bytes(b"old")
    fresh.write_bytes(b"new")
    old_at = time.time() - 7200
    os.utime(stale, (old_at, old_at))

    storage.cleanup_old_temp_files(max_age_seconds=3600)
    assert not stale.exists()
    assert fresh.is_file()
