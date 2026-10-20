from concurrent.futures import ThreadPoolExecutor

import pytest

from alofoke_clips.errors import PipelineError
from alofoke_clips.storage import Database


def test_queue_persists_while_offline_and_claim_is_exclusive(tmp_path):
    path = tmp_path / "queue.sqlite3"
    db = Database(path)
    first = db.enqueue({"source": "a"})
    second = db.enqueue({"source": "b"})
    reopened = Database(path)
    assert [job["status"] for job in reopened.list_jobs()] == ["queued", "queued"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: Database(path).claim(), range(4)))
    assert sum(claim is not None for claim in claims) == 1
    claimed = next(claim for claim in claims if claim)
    assert claimed["id"] == first
    db.finish(first, "completed", tmp_path / "report.json")
    assert reopened.claim()["id"] == second


def test_pause_resume_is_persistent(tmp_path):
    db = Database(tmp_path / "queue.sqlite3")
    job = db.enqueue({})
    db.set_paused(True)
    assert Database(db.path).is_paused()
    assert db.claim() is None
    db.set_paused(False)
    assert db.claim()["id"] == job


def test_failed_and_crashed_jobs_can_be_recovered(tmp_path):
    db = Database(tmp_path / "queue.sqlite3")
    identity = db.enqueue({"source": "a", "allow_paid_gpu": True})
    db.claim()
    db.recover(identity)
    assert db.claim()["id"] == identity
    db.finish(identity, "failed", tmp_path / "report.json", "render failed")
    db.recover(identity)
    assert db.claim()["id"] == identity
    assert db.list_jobs()[0]["attempts"] == 3
    with db.connect() as connection:
        assert (
            '"allow_paid_gpu": false'
            in connection.execute("SELECT request_json FROM jobs").fetchone()[0]
        )


def test_idempotency_key_and_conflict(tmp_path):
    db = Database(tmp_path / "queue.sqlite3")
    identity = db.enqueue({"source": "a"}, "recording-1")
    assert db.enqueue({"source": "a"}, "recording-1") == identity
    with pytest.raises(PipelineError, match="different request"):
        db.enqueue({"source": "b"}, "recording-1")


def test_budget_reservations_prevent_overspending_concurrently(tmp_path):
    db = Database(tmp_path / "queue.sqlite3")
    job = db.enqueue({})

    def reserve(_):
        try:
            return db.reserve_cloud(job, 0.6, monthly_limit=1, job_limit=1)
        except PipelineError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        reservations = list(pool.map(reserve, range(4)))
    assert sum(item is not None for item in reservations) == 1


def test_budget_limits_monthly_and_per_job(tmp_path):
    db = Database(tmp_path / "queue.sqlite3")
    a, b = db.enqueue({}), db.enqueue({})
    db.reserve_cloud(a, 1, 3, 1)
    with pytest.raises(PipelineError, match="budget"):
        db.reserve_cloud(a, 0.1, 3, 1)
    db.reserve_cloud(b, 2, 3, 2)
    with pytest.raises(PipelineError, match="budget"):
        db.reserve_cloud(b, 0.1, 3, 3)


@pytest.mark.parametrize("amount", [0, -1, float("inf"), float("nan")])
def test_invalid_budget_values_rejected(tmp_path, amount):
    db = Database(tmp_path / "queue.sqlite3")
    job = db.enqueue({})
    with pytest.raises(PipelineError):
        db.reserve_cloud(job, amount, 50, 2)
