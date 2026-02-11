from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.viewmodels.insurance_vm import InsuranceViewModel

router = APIRouter(prefix="/insurance")


@router.get("/")
async def insurance_summary(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await InsuranceViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "insurance/summary.html",
        {"request": request, "vm": vm},
    )
