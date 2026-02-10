from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.viewmodels.export_vm import ExportViewModel

router = APIRouter(prefix="/export")


@router.get("/")
async def export_page(request: Request, session: AsyncSession = Depends(get_session)):
    vm = await ExportViewModel.load(session)
    return request.app.state.templates.TemplateResponse(
        "export/options.html",
        {"request": request, "vm": vm},
    )


@router.get("/csv")
async def export_csv(
    session: AsyncSession = Depends(get_session),
    room_ids: str | None = None,
):
    ids = [int(x) for x in room_ids.split(",")] if room_ids else None
    csv_data = await ExportViewModel.generate_csv(session, ids)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory.csv"},
    )


@router.get("/json")
async def export_json(
    session: AsyncSession = Depends(get_session),
    room_ids: str | None = None,
):
    ids = [int(x) for x in room_ids.split(",")] if room_ids else None
    json_data = await ExportViewModel.generate_json(session, ids)
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=inventory.json"},
    )


@router.get("/pdf")
async def export_pdf(
    session: AsyncSession = Depends(get_session),
    room_ids: str | None = None,
    insurance: bool = False,
):
    ids = [int(x) for x in room_ids.split(",")] if room_ids else None
    pdf_bytes = await ExportViewModel.generate_pdf(session, ids, insurance_mode=insurance)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=inventory_report.pdf"},
    )
