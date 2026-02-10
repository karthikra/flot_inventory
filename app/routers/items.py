from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.image_service import ImageService
from app.viewmodels.item_vm import ItemDetailViewModel

router = APIRouter(prefix="/items")


@router.get("/")
async def list_items(
    request: Request,
    session: AsyncSession = Depends(get_session),
    room_id: int | None = None,
    category: str | None = None,
):
    from app.repositories.item_repo import ItemRepository

    repo = ItemRepository(session)
    items = await repo.search(room_id=room_id, category=category)

    from app.repositories.room_repo import RoomRepository
    room_repo = RoomRepository(session)
    rooms = await room_repo.get_all()

    return request.app.state.templates.TemplateResponse(
        "items/grid.html",
        {"request": request, "items": items, "rooms": rooms, "room_id": room_id, "category": category},
    )


@router.get("/{item_id}")
async def item_detail(item_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    vm = await ItemDetailViewModel.load(session, item_id)
    if not vm.item:
        return HTMLResponse("Item not found", status_code=404)

    from app.repositories.room_repo import RoomRepository
    room_repo = RoomRepository(session)
    room = await room_repo.get(vm.item.room_id)

    return request.app.state.templates.TemplateResponse(
        "items/detail.html",
        {"request": request, "vm": vm, "room": room},
    )


@router.post("/{item_id}/edit")
async def edit_item(item_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    data = ItemUpdate(**{k: v for k, v in form.items() if v != ""})
    await ItemDetailViewModel.update_item(session, item_id, data)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.delete("/{item_id}")
async def delete_item(item_id: int, session: AsyncSession = Depends(get_session)):
    await ItemDetailViewModel.delete_item(session, item_id)
    return HTMLResponse(headers={"HX-Redirect": "/items"})


@router.put("/{item_id}/status")
async def update_status(item_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    status = form.get("status")
    await ItemDetailViewModel.update_status(session, item_id, status)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/{item_id}/images")
async def add_image(
    item_id: int,
    request: Request,
    file: UploadFile = None,
    session: AsyncSession = Depends(get_session),
):
    if not file:
        return HTMLResponse("No file uploaded", status_code=400)
    form = await request.form()
    image_type = form.get("image_type", "front")

    img_service = ImageService()
    data = await file.read()
    ext = f".{file.filename.rsplit('.', 1)[-1]}" if file.filename and "." in file.filename else ".jpg"
    image_path, _ = await img_service.save_upload(data, ext=ext)

    await ItemDetailViewModel.add_image(session, item_id, image_path, image_type)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@router.post("/{item_id}/tags")
async def add_tag(item_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    tag_name = form.get("tag", "").strip()
    if tag_name:
        await ItemDetailViewModel.add_tag(session, item_id, tag_name)
    return RedirectResponse(f"/items/{item_id}", status_code=303)
