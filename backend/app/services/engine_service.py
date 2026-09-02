"""qwen-tts-webui 引擎进程管理（启动/停止/状态）。"""

import os
import subprocess
import time
from pathlib import Path

import httpx
import psutil


def _port(url: str) -> int:
    return int(url.rstrip("/").rsplit(":", 1)[-1] or "7860")


def _probe(url: str, timeout: float = 2.0) -> bool:
    try:
        r = httpx.get(f"{url}/qwenapi/v1/models", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def status(settings) -> dict:
    return {"running": _probe(settings.tts_api_url, timeout=2.0)}


def start(settings) -> dict:
    """启动 qwen-tts-webui（已运行则直接返回）。"""
    if _probe(settings.tts_api_url):
        return {"ok": True, "already_running": True}
    qdir = Path(settings.qwen_tts_dir)
    if not (qdir / "launch.py").exists():
        raise RuntimeError(f"未找到 qwen-tts-webui: {qdir}（可在 .env 设置 QWEN_TTS_DIR）")
    log_dir = Path(settings.data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_f = open(log_dir / "qwen-engine.out.log", "a", encoding="utf-8")
    err_f = open(log_dir / "qwen-engine.err.log", "a", encoding="utf-8")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [settings.qwen_python, "launch.py", "--nowebui", "--server-name", "0.0.0.0",
         "--server-port", str(_port(settings.tts_api_url)), "--no-inbrowser"],
        cwd=str(qdir), stdout=out_f, stderr=err_f, **kwargs,
    )
    out_f.close()
    err_f.close()
    deadline = time.time() + 180
    while time.time() < deadline:
        if _probe(settings.tts_api_url):
            return {"ok": True, "pid": proc.pid}
        if proc.poll() is not None:
            tail = ""
            p = log_dir / "qwen-engine.err.log"
            if p.exists():
                tail = p.read_text(encoding="utf-8", errors="replace")[-800:]
            raise RuntimeError(f"qwen-tts-webui 启动失败（pid {proc.pid}）：\n{tail}")
        time.sleep(2)
    proc.terminate()
    raise RuntimeError("qwen-tts-webui 启动超时")


def stop(settings) -> dict:
    """停止监听 tts_api_url 端口的 qwen-tts-webui 进程。"""
    port = _port(settings.tts_api_url)
    pids = _listener_pids(port)
    for pid in pids:
        try:
            psutil.Process(pid).terminate()
        except psutil.Error:
            pass
    deadline = time.time() + 30
    while time.time() < deadline:
        if not _probe(settings.tts_api_url, timeout=1.0) and not _listener_pids(port):
            return {"ok": True, "stopped_pids": sorted(pids)}
        time.sleep(1)
    # 兜底强杀
    for pid in _listener_pids(port):
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass
    return {"ok": True, "stopped_pids": sorted(pids)}


def _listener_pids(port: int) -> set[int]:
    pids = set()
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr.port == port and c.pid:
                pids.add(c.pid)
    except psutil.Error:
        pass
    return pids
