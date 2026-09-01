from fastapi import APIRouter, Request

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


@router.get("/tts/models", response_model=list[TTSModelInfo])
async def list_tts_models(request: Request):
    adapter = request.app.state.build_tts_adapter()
    try:
        return [TTSModelInfo(**m) for m in await adapter.list_models()]
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()


@router.get("/tts/speakers", response_model=list[TTSSpeakerInfo])
async def list_tts_speakers(request: Request):
    adapter = request.app.state.build_tts_adapter()
    try:
        speakers = await adapter.list_speakers()
        if speakers and isinstance(speakers[0], str):
            return [TTSSpeakerInfo(name=s) for s in speakers]
        return [TTSSpeakerInfo(**s) for s in speakers]
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()
