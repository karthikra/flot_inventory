from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.viewmodels.search_vm import SearchViewModel

router = APIRouter(prefix="/search")


@router.get("/")
async def search_page(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await SearchViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "search/results.html",
        {"request": request, "vm": vm},
    )


@router.get("/results")
async def search_results(
    request: Request,
    q: str = "",
    room_id: int | None = None,
    category: str | None = None,
    condition: str | None = None,
    status: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    session: AsyncSession = Depends(get_session),
):
    vm = await SearchViewModel.search(
        session,
        query=q,
        room_id=room_id,
        category=category,
        condition=condition,
        status=status,
        min_value=min_value,
        max_value=max_value,
    )
    return request.app.state.templates.TemplateResponse(
        "search/results.html",
        {"request": request, "vm": vm},
    )
