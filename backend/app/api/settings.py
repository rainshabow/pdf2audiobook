from fastapi import APIRouter, Request, UploadFile

from app.config import RuntimeSettings
from app.models import SettingsView, TTSModelInfo, TTSSpeakerInfo

router = APIRouter()


def _rs(request: Request) -> RuntimeSettings:
    return request.app.state.settings_store.load()


@router.get("/settings", response_model=SettingsView)
async def get_settings(request: Request):
    rs = _rs(request)
    return SettingsView(**rs.__dict__)


@router.put("/settings", response_model=SettingsView)
async def put_settings(request: Request, view: SettingsView):
    rs = RuntimeSettings(**view.model_dump())
    request.app.state.settings_store.save(rs)
    return SettingsView(**rs.__dict__)


@router.post("/tts/load")
async def load_tts_model(request: Request):
    """预加载 TTS 引擎模型（qwen：触发一次极短合成；mock：no-op）。"""
    adapter = request.app.state.build_tts_adapter()
    try:
        await adapter.warmup()
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()
    return {"ok": True}


@router.post("/settings/clone-audio")
async def upload_clone_audio(request: Request, file: UploadFile):
    data_dir = request.app.state.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "clone_ref_audio.wav"
    dest.write_bytes(await file.read())
    return {"path": "clone_ref_audio.wav"}


@router.get("/tts/models", response_model=list[TTSModelInfo])
async def list_tts_models(request: Request, engine: str | None = None):
    # engine 用于预览尚未保存的引擎（如切到 mimo 时先看模型列表）
    adapter = request.app.state.build_tts_adapter(engine=engine)
    try:
        return [TTSModelInfo(**m) for m in await adapter.list_models()]
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()


@router.get("/tts/speakers", response_model=list[TTSSpeakerInfo])
async def list_tts_speakers(request: Request, engine: str | None = None):
    adapter = request.app.state.build_tts_adapter(engine=engine)
    try:
        speakers = await adapter.list_speakers()
        if speakers and isinstance(speakers[0], str):
            return [TTSSpeakerInfo(name=s) for s in speakers]
        return [TTSSpeakerInfo(**s) for s in speakers]
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()
