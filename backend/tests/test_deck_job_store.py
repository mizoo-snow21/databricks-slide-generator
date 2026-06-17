from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from services.deck_job_store import DeckJobStore


def test_create_returns_running_job_with_id_and_created_at() -> None:
    store = DeckJobStore()
    job = store.create(now=42.0)
    assert job.status == "running"
    assert job.id
    assert job.created_at == 42.0


def test_get_unknown_id_returns_none() -> None:
    store = DeckJobStore()
    assert store.get("missing") is None


def test_set_done_updates_status_and_deck_id() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    store.set_done(job.id, "deck-abc")
    result = store.get(job.id)
    assert result is not None
    assert result.status == "done"
    assert result.deck_id == "deck-abc"


def test_set_error_updates_status_error_and_status_code() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    store.set_error(job.id, "genie failed", 502)
    result = store.get(job.id)
    assert result is not None
    assert result.status == "error"
    assert result.error == "genie failed"
    assert result.status_code == 502


def test_get_returns_snapshot_copy() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    snapshot = store.get(job.id)
    assert snapshot is not None
    snapshot.status = "done"
    stored = store.get(job.id)
    assert stored is not None
    assert stored.status == "running"


def test_prune_keeps_newest_jobs_by_created_at() -> None:
    store = DeckJobStore(max_jobs=3)
    j1 = store.create(now=1.0)
    store.create(now=2.0)
    store.create(now=3.0)
    j4 = store.create(now=4.0)
    assert store.get(j1.id) is None
    assert store.get(j4.id) is not None
    assert store.get(j4.id).status == "running"


def test_wait_returns_done_job_when_future_completes() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    executor = ThreadPoolExecutor(max_workers=1)

    def work() -> None:
        store.set_done(job.id, "deck-123")

    future = executor.submit(work)
    store.attach_future(job.id, future)
    result = store.wait(job.id, timeout=5.0)
    executor.shutdown(wait=True)
    assert result is not None
    assert result.status == "done"
    assert result.deck_id == "deck-123"


def test_wait_swallows_future_exception_and_returns_error_job() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    executor = ThreadPoolExecutor(max_workers=1)

    def work() -> None:
        store.set_error(job.id, "boom", 500)
        raise RuntimeError("boom")

    future = executor.submit(work)
    store.attach_future(job.id, future)
    result = store.wait(job.id, timeout=5.0)
    executor.shutdown(wait=True)
    assert result is not None
    assert result.status == "error"
    assert result.error == "boom"
    assert result.status_code == 500


def test_clear_empties_store() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    store.clear()
    assert store.get(job.id) is None


def test_set_done_with_result_round_trips_slides() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    slides = [{"layout": "title", "title": "Intro", "summary": "Open", "notes": ""}]
    store.set_done(job.id, result=slides)
    result = store.get(job.id)
    assert result is not None
    assert result.status == "done"
    assert result.result == slides


def test_set_done_positional_deck_id_still_sets_deck_id() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    store.set_done(job.id, "deck-123")
    result = store.get(job.id)
    assert result is not None
    assert result.status == "done"
    assert result.deck_id == "deck-123"


def test_create_kind_outline_and_default_deck() -> None:
    store = DeckJobStore()
    outline_job = store.create(now=1.0, kind="outline")
    deck_job = store.create(now=2.0)
    assert outline_job.kind == "outline"
    assert deck_job.kind == "deck"


def test_get_deep_copies_result_so_mutations_do_not_affect_stored_state() -> None:
    store = DeckJobStore()
    job = store.create(now=1.0)
    slides = [{"layout": "title", "title": "A", "summary": "B", "notes": ""}]
    store.set_done(job.id, result=slides)
    snapshot = store.get(job.id)
    assert snapshot is not None
    assert snapshot.result is not None
    snapshot.result[0]["title"] = "mutated"
    snapshot.result.append(
        {"layout": "closing", "title": "X", "summary": "Y", "notes": ""}
    )
    stored = store.get(job.id)
    assert stored is not None
    assert stored.result == slides
    assert len(stored.result) == 1
    assert stored.result[0]["title"] == "A"


def test_thread_safety_concurrent_create_and_set_done() -> None:
    store = DeckJobStore(max_jobs=50)
    job_ids: list[str] = []
    ids_lock = threading.Lock()

    def worker(i: int) -> None:
        job = store.create(now=float(i))
        store.set_done(job.id, f"deck-{i}")
        with ids_lock:
            job_ids.append(job.id)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(job_ids) == 20
    for job_id in job_ids:
        job = store.get(job_id)
        assert job is not None
        assert job.status == "done"
        assert job.deck_id is not None
