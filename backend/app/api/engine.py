"""qwen 引擎服务管理端点。"""

from fastapi import APIRouter, Request

from app.services import engine_service

router = APIRouter()


@router.get("/status")
def engine_status(request: Request):
    return engine_service.status(request.app.state.settings)


@router.post("/start")
def engine_start(request: Request):
    return engine_service.start(request.app.state.settings)


@router.post("/stop")
def engine_stop(request: Request):
    return engine_service.stop(request.app.state.settings)
