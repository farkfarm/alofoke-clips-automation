import json

from alofoke_clips import cli
from alofoke_clips.storage import Database


def test_cli_queue_controls_and_offline_submission(tmp_path, fixture_paths, monkeypatch, capsys):
    config = tmp_path / "config.toml"
    config.write_text('mode="mock"\ndata_dir="work"\n', encoding="utf-8")
    common = ["--config", str(config)]
    args = [
        "enqueue",
        str(tmp_path / "authorized.mp4"),
        "--authorized-local",
        "--job-key",
        "one",
        "--mock-transcript",
        str(fixture_paths[0]),
        "--mock-analysis",
        str(fixture_paths[1]),
    ]
    assert cli.main(common + args) == 0
    job_id = json.loads(capsys.readouterr().out)["job_id"]
    assert cli.main(common + args) == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == job_id
    assert cli.main(common + ["queue", "pause"]) == 0
    capsys.readouterr()
    assert cli.main(common + ["worker", "--once"]) == 0
    assert json.loads(capsys.readouterr().out)["paused"]
    assert cli.main(common + ["queue", "resume"]) == 0
    capsys.readouterr()
    calls = []

    def process(db, job):
        calls.append(job["id"])
        db.finish(job["id"], "completed", tmp_path / "report.json")
        return {"status": "completed"}

    monkeypatch.setattr(cli, "run_claimed", process)
    assert cli.main(common + ["worker", "--once"]) == 0
    assert calls == [job_id]
    assert cli.main(common + ["queue", "list"]) == 0
    assert Database(tmp_path / "work/queue.sqlite3").list_jobs()[0]["status"] == "completed"


def test_cli_mock_requires_explicit_fixtures(tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text('data_dir="work"\n')
    assert cli.main(["--config", str(config), "process", "test.mp4", "--authorized-local"]) == 1
    assert "MOCK requires" in capsys.readouterr().err


def test_cli_does_not_reveal_bad_config_credentials(tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text('[analysis]\nbase_url="http://user:do-not-print@localhost:11434"\n')
    assert cli.main(["--config", str(config), "doctor"]) == 1
    assert "do-not-print" not in capsys.readouterr().err


def test_cli_doctor_works_without_gpu(monkeypatch, tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text('data_dir="work"\n')
    monkeypatch.setattr(
        cli, "diagnose", lambda _: {"ffmpeg": {"ready": True}, "nvidia": {"available": False}}
    )
    assert cli.main(["--config", str(config), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["nvidia"]["available"] is False
