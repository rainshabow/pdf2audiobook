from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app


def test_create_app_has_no_side_effects_before_lifespan(tmp_path: Path):
    # 未进入 lifespan 时不得建目录 / 创建 jobs.db（模块级 app 导入安全）
    app = create_app(Settings(data_dir=tmp_path))
    assert app.title == "PDF 转语音"
    assert not (tmp_path / "books").exists()
    assert not (tmp_path / "tmp").exists()
    assert not (tmp_path / "jobs.db").exists()


@pytest.mark.asyncio
async def test_create_app_lifespan_initializes_state(tmp_path: Path):
    app = create_app(Settings(data_dir=tmp_path))
    async with app.router.lifespan_context(app):
        assert (tmp_path / "books").is_dir()
        assert (tmp_path / "tmp").is_dir()
        assert (tmp_path / "jobs.db").exists()
        assert app.state.data_dir == tmp_path
        assert app.state.job_manager is not None
        assert app.state.settings_store is not None
        assert callable(app.state.build_tts_adapter)
