"""Validate the committed, output-free notebook without models or Colab services."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/02_colab_real_benchmark.ipynb"


def code_cells():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def test_notebook_is_output_free_and_all_python_compiles():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            compile("".join(cell["source"]), "notebook-cell", "exec")


def test_initialization_resets_previous_approvals(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    scope = {"APPROVALS": {"downloads": "old", "real inference": "old"}}
    exec(code_cells()[0], scope)
    assert scope["APPROVALS"] == {}


@pytest.mark.parametrize("kind", ["downloads", "real inference"])
def test_unapproved_model_stages_fail_before_any_execution(tmp_path, kind):
    source = tmp_path / "source.mp4"
    source.touch()
    stages = code_cells()
    stage = next(s for s in stages if f'APPROVALS.pop("{kind}"' in s)
    scope = {
        "APPROVALS": {},
        "LOCAL_SOURCE": source,
        "hardware": {"nvidia": {"available": True}},
        "shutil": SimpleNamespace(which=lambda _: "existing-ollama"),
        "proposal_key": lambda: "fresh-context",
        "real_key": lambda: "fresh-source-context",
    }
    with pytest.raises(AssertionError, match="Click Approve"):
        exec(stage, scope)


@pytest.mark.integration
def test_notebook_actual_mock_cell_runs_existing_cli(monkeypatch):
    from alofoke_clips.config import load_settings

    monkeypatch.chdir(ROOT)
    settings = load_settings()
    monkeypatch.setenv("ALOFOKE_FFMPEG", settings.media.ffmpeg)
    monkeypatch.setenv("ALOFOKE_FFPROBE", settings.media.ffprobe)
    import shutil

    if not all(shutil.which(p) for p in (settings.media.ffmpeg, settings.media.ffprobe)):
        pytest.skip("FFmpeg/FFprobe unavailable")
    scope = {}
    exec(code_cells()[0], scope)
    scope.update(REPO=ROOT, FFMPEG=settings.media.ffmpeg, FFPROBE=settings.media.ffprobe)
    smoke = next(s for s in code_cells() if "def write_config" in s)
    exec(smoke, scope)
    assert len(scope["mock"]["clips"]) == 1
    assert scope["mock"]["mode"] == "mock"
    assert scope["mock"]["publication_status"] == "disabled"


def test_summary_can_preserve_setup_failure_without_real_inference(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    scope = {}
    exec(code_cells()[0], scope)
    source = tmp_path / "permitted.mp4"
    source.write_bytes(b"fixture")
    scope.update(
        COMMIT="test-revision",
        PROPOSAL={"model": "proposed-only"},
        info=SimpleNamespace(duration=600),
        source=source,
        SOURCE_SHA=hashlib.sha256(b"fixture").hexdigest(),
        SOURCE_ORIGINAL_SHA=hashlib.sha256(b"fixture").hexdigest(),
        ERRORS=[{"stage": "model_setup", "error": "not executed"}],
    )
    with pytest.raises(RuntimeError, match="setup fixture"):
        with scope["setup_time"]("failing_setup"):
            raise RuntimeError("setup fixture")
    assert scope["ERRORS"][-1] == {
        "stage": "failing_setup",
        "error_type": "RuntimeError",
    }
    assert scope["SETUP"]["failing_setup"] >= 0
    export = next(s for s in code_cells() if '"benchmark-summary.json", summary' in s)
    exec(export.split("# Export an explicit whitelist")[0], scope)
    summary = json.loads((scope["RESULTS"] / "benchmark-summary.json").read_text())
    assert summary["status"] == "not_run"
    assert summary["cli_wall_seconds"] is None
    assert summary["model_versions"] == {"proposal": {"model": "proposed-only"}}
    assert summary["errors"] == scope["ERRORS"]
