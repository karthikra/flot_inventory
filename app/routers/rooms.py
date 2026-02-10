from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.room import RoomCreate, RoomUpdate
from app.viewmodels.room_vm import RoomDetailViewModel, RoomListViewModel

router = APIRouter(prefix="/rooms")


@router.get("/")
async def list_rooms(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await RoomListViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "rooms/list.html",
        {"request": request, "vm": vm},
    )


@router.post("/")
async def create_room(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    data = RoomCreate(
        name=form["name"],
        description=form.get("description", ""),
        floor=int(form.get("floor", 1)),
    )
    await RoomDetailViewModel.create_room(session, data)
    return RedirectResponse("/rooms", status_code=303)


@router.get("/{room_id}")
async def room_detail(room_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    vm = await RoomDetailViewModel.load(session, room_id)
    if not vm.room:
        return HTMLResponse("Room not found", status_code=404)
    return request.app.state.templates.TemplateResponse(
        "rooms/detail.html",
        {"request": request, "vm": vm},
    )


@router.put("/{room_id}")
async def update_room(room_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    data = RoomUpdate(**{k: v for k, v in form.items() if v})
    room = await RoomDetailViewModel.update_room(session, room_id, data)
    if not room:
        return HTMLResponse("Room not found", status_code=404)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


@router.delete("/{room_id}")
async def delete_room(room_id: int, session: AsyncSession = Depends(get_session)):
    await RoomDetailViewModel.delete_room(session, room_id)
    return HTMLResponse(headers={"HX-Redirect": "/rooms"})
