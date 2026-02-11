from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.viewmodels.dashboard_vm import DashboardViewModel

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await DashboardViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "vm": vm},
    )
