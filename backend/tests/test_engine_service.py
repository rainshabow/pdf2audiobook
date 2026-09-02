from app.services import engine_service


class _S:
    tts_api_url = "http://127.0.0.1:7860"
    qwen_tts_dir = r"D:\WorkSpace\qwen-tts-webui"
    qwen_python = "python"
    data_dir = None


def test_port_parsing():
    assert engine_service._port("http://127.0.0.1:7860") == 7860
    assert engine_service._port("http://127.0.0.1:9000/") == 9000


def test_probe_offline_is_false():
    s = _S()
    s.tts_api_url = "http://127.0.0.1:1"  # 未监听端口，立即拒绝
    assert engine_service._probe(s.tts_api_url, timeout=1.0) is False


def test_status_offline():
    s = _S()
    s.tts_api_url = "http://127.0.0.1:1"
    assert engine_service.status(s) == {"running": False}


def test_start_returns_already_when_running(monkeypatch):
    monkeypatch.setattr(engine_service, "_probe", lambda url, timeout=2.0: True)
    r = engine_service.start(_S())
    assert r == {"ok": True, "already_running": True}


def test_stop_without_listener_is_ok(monkeypatch):
    monkeypatch.setattr(engine_service, "_probe", lambda url, timeout=2.0: False)
    monkeypatch.setattr(engine_service, "_listener_pids", lambda port: set())
    r = engine_service.stop(_S())
    assert r == {"ok": True, "stopped_pids": []}
