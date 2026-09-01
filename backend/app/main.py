from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import store
from app.api import books, chapters, jobs, settings as settings_api
from app.config import Settings, SettingsStore
from app.services.job_manager import JobManager


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings_store = SettingsStore(settings.data_dir)  # 无副作用，仅计算路径

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 副作用（建目录、构造 JobManager/SQLite、state 赋值）全部推迟到 lifespan，
        # 使 create_app() 与模块级 app 导入无副作用（测试/工具链导入安全）。
        store.init_store(settings.data_dir)
        jm = JobManager(settings.data_dir, settings_store, settings=settings)
        app.state.data_dir = settings.data_dir
        app.state.settings = settings
        app.state.settings_store = settings_store
        app.state.job_manager = jm

        from app.services.job_manager import _default_tts_factory
        app.state.build_tts_adapter = lambda: _default_tts_factory(
            settings_store.load(), settings)

        jm.start_worker()
        try:
            yield
        finally:
            await jm.shutdown()

    app = FastAPI(title="PDF 转语音", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(books.router, prefix="/api/books", tags=["books"])
    app.include_router(chapters.router, prefix="/api/books/{book_id}/chapters", tags=["chapters"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(settings_api.router, prefix="/api", tags=["settings"])
    return app


app = create_app()
