import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from alofoke_clips import diagnostics
from alofoke_clips.errors import ProviderError
from alofoke_clips.observability import EventLog
from alofoke_clips.providers.http import JsonHTTP


def test_http_json_transport_and_error_body_redaction():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/error":
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"sensitive-response-body")
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert JsonHTTP().request(base, {"text": "español"}, 2) == {"text": "español"}
        with pytest.raises(ProviderError, match="response body omitted") as caught:
            JsonHTTP().request(base + "/error", {}, 2)
        assert "sensitive-response-body" not in str(caught.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_gpu_absence_is_reported_without_assumptions(monkeypatch):
    monkeypatch.setattr(diagnostics, "nvidia_smi_path", lambda: None)
    assert diagnostics.gpu_snapshot()["available"] is False


def test_log_redacts_runpod_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-secret")
    path = tmp_path / "events.jsonl"
    EventLog(path).emit("test", message="test-secret")
    assert "test-secret" not in path.read_text()
    assert "[REDACTED]" in path.read_text()
