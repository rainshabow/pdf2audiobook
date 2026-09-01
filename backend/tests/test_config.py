from pathlib import Path

from app.config import Settings, _env_file_path


def test_env_file_path_points_to_repo_root():
    path = _env_file_path()
    assert path.name == ".env"
    # backend/app/config.py 的 parents[2] 即仓库根
    assert path.parent == Path(__file__).resolve().parents[2]
    assert (path.parent / ".env.example").exists()


def test_settings_reads_openai_api_key_from_env(monkeypatch):
    # 不写真实 .env：直接通过环境变量验证 Settings 可读到 OPENAI_API_KEY
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    assert Settings().openai_api_key == "sk-test-key"
