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
