import asyncio
import json
import os
import tempfile

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_session
from app.schemas.capture import CaptureConfirmItem, CaptureConfirmRequest
from app.services.local_vision import LocalVisionService
from app.viewmodels.capture_vm import CaptureViewModel

router = APIRouter(prefix="/capture")

# in-memory storage for SSE progress (per session)
_progress_queues: dict[int, asyncio.Queue] = {}


@router.post("/detect")
async def detect_objects(file: UploadFile):
    """Lightweight endpoint: accept an image, return detected objects as JSON."""
    image_data = await file.read()
    suffix = ".jpg" if "jpeg" in (file.content_type or "") else ".png"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image_data)
        tmp_path = tmp.name

    vision = LocalVisionService()
    detected = await vision.analyze_frame(tmp_path)

    os.unlink(tmp_path)

    return JSONResponse([obj.model_dump() for obj in detected])


@router.get("/")
async def capture_page(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await CaptureViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "capture/session.html",
        {"request": request, "vm": vm},
    )


@router.post("/start")
async def start_session(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    room_id = int(form["room_id"])
    mode = form.get("mode", "video")
    capture = await CaptureViewModel.start_session(session, room_id, mode)
    return HTMLResponse(
        f'<div id="session-info" data-session-id="{capture.id}" data-room-id="{room_id}" data-mode="{mode}">'
        f"Session started (#{capture.id})</div>"
    )


@router.post("/video")
async def upload_video(
    request: Request,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    session_id = int(form["session_id"])
    room_id = int(form["room_id"])

    video_data = await file.read()

    # set up progress queue for SSE
    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[session_id] = queue

    async def progress_callback(status, progress, message, data):
        await queue.put({
            "status": status,
            "progress": progress,
            "message": message,
            **data,
        })

    detected, mode_switch, room_mentions = await CaptureViewModel.process_video(
        session, session_id, video_data, progress_callback
    )

    # clean up queue
    _progress_queues.pop(session_id, None)

    # render review template
    return request.app.state.templates.TemplateResponse(
        "capture/review.html",
        {
            "request": request,
            "items": [obj.model_dump() for obj in detected],
            "mode_switch": mode_switch.model_dump() if mode_switch else None,
            "session_id": session_id,
            "room_id": room_id,
            "room_mentions": [m.model_dump() for m in room_mentions],
        },
    )


@router.post("/image")
async def upload_image(
    request: Request,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    session_id = int(form.get("session_id", 0))
    room_id = int(form["room_id"])

    from app.repositories.room_repo import RoomRepository
    room_repo = RoomRepository(session)
    room = await room_repo.get(room_id)
    room_name = room.name if room else "unsorted"

    image_data = await file.read()
    detected, image_path, thumb_path = await CaptureViewModel.process_image(
        session, session_id, image_data, room_name
    )

    return request.app.state.templates.TemplateResponse(
        "capture/review.html",
        {
            "request": request,
            "items": [obj.model_dump() for obj in detected],
            "mode_switch": None,
            "session_id": session_id,
            "room_id": room_id,
            "source_image": image_path,
        },
    )


@router.post("/rapid")
async def upload_rapid_capture(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    session_id = int(form["session_id"])
    room_id = int(form["room_id"])

    # Collect snap images: snaps[0], snaps[1], ...
    snap_images: list[bytes] = []
    idx = 0
    while True:
        snap_file = form.get(f"snaps[{idx}]")
        if snap_file is None:
            break
        snap_images.append(await snap_file.read())
        idx += 1

    # Parse timestamps JSON
    timestamps_raw = form.get("timestamps", "[]")
    timestamps: list[float] = json.loads(timestamps_raw)

    # Optional audio blob
    audio_data = None
    audio_file = form.get("audio")
    if audio_file and hasattr(audio_file, "read"):
        audio_data = await audio_file.read()

    # Get room name for context
    from app.repositories.room_repo import RoomRepository
    room_repo = RoomRepository(session)
    room = await room_repo.get(room_id)
    room_name = room.name if room else "unsorted"

    # Set up progress queue for SSE
    queue: asyncio.Queue = asyncio.Queue()
    _progress_queues[session_id] = queue

    async def progress_callback(status, progress, message, data):
        await queue.put({
            "status": status,
            "progress": progress,
            "message": message,
            **data,
        })

    detected, room_mentions = await CaptureViewModel.process_rapid_capture(
        session, session_id, snap_images, timestamps,
        audio_data=audio_data, room_name=room_name,
        progress_callback=progress_callback,
    )

    _progress_queues.pop(session_id, None)

    return request.app.state.templates.TemplateResponse(
        "capture/review.html",
        {
            "request": request,
            "items": [obj.model_dump() for obj in detected],
            "mode_switch": None,
            "session_id": session_id,
            "room_id": room_id,
            "room_mentions": [m.model_dump() for m in room_mentions],
        },
    )


@router.get("/stream/{session_id}")
async def stream_progress(session_id: int):
    """SSE endpoint for real-time video processing progress."""

    async def event_generator():
        queue = _progress_queues.get(session_id)
        if not queue:
            yield {"data": json.dumps({"status": "error", "message": "No active session"})}
            return

        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                yield {"data": json.dumps(data)}
                if data.get("status") == "done":
                    break
            except asyncio.TimeoutError:
                yield {"data": json.dumps({"status": "heartbeat"})}

    return EventSourceResponse(event_generator())


@router.post("/confirm")
async def confirm_items(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    session_id = int(form.get("session_id", 0))
    room_id = int(form["room_id"])

    # parse items from form
    items = []
    idx = 0
    while f"items[{idx}][name]" in form:
        prefix = f"items[{idx}]"
        item = CaptureConfirmItem(
            name=form[f"{prefix}[name]"],
            description=form.get(f"{prefix}[description]"),
            category=form.get(f"{prefix}[category]", "other"),
            is_book=form.get(f"{prefix}[is_book]") == "true",
            confidence_score=float(form.get(f"{prefix}[confidence_score]", 0)),
            estimated_value=float(v) if (v := form.get(f"{prefix}[estimated_value]")) else None,
            condition=form.get(f"{prefix}[condition]"),
            frame_path=form.get(f"{prefix}[frame_path]"),
            voice_context=form.get(f"{prefix}[voice_context]") or None,
            title=form.get(f"{prefix}[title]"),
            author=form.get(f"{prefix}[author]"),
            isbn=form.get(f"{prefix}[isbn]"),
            publisher=form.get(f"{prefix}[publisher]"),
            genre=form.get(f"{prefix}[genre]"),
        )
        items.append(item)
        idx += 1

    saved = await CaptureViewModel.confirm_items(session, room_id, session_id, items)

    return HTMLResponse(
        f'<div class="success-message" hx-swap-oob="true">'
        f"Saved {len(saved)} items to inventory!"
        f'<a href="/rooms/{room_id}">View Room</a></div>'
    )
