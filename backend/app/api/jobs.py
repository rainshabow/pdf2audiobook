from fastapi import APIRouter, HTTPException, Request

from app.models import JobInfo

router = APIRouter()


@router.get("", response_model=list[JobInfo])
async def list_jobs(request: Request):
    return [JobInfo(**j) for j in request.app.state.job_manager.list_jobs()]


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str):
    jm = request.app.state.job_manager
    job = jm.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    jm.cancel(job_id)
    return {"ok": True}


@router.post("/{job_id}/resume", response_model=JobInfo)
async def resume_job(request: Request, job_id: str):
    """失败/已取消的改写、合成、重建任务：从断点创建续跑任务。"""
    jm = request.app.state.job_manager
    job = jm.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    try:
        new_id = jm.resume(job_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return JobInfo(**jm.get_job(new_id))
