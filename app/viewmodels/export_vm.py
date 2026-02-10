from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository
from app.services.export_service import ExportService


@dataclass
class ExportViewModel:
    rooms: list = field(default_factory=list)
    total_items: int = 0
    total_value: float = 0.0

    @classmethod
    async def load(cls, session: AsyncSession) -> "ExportViewModel":
        room_repo = RoomRepository(session)
        item_repo = ItemRepository(session)
        rooms = await room_repo.get_all()
        stats = await item_repo.get_stats()
        return cls(
            rooms=rooms,
            total_items=stats["total_items"],
            total_value=stats["total_value"],
        )

    @classmethod
    async def generate_csv(cls, session: AsyncSession, room_ids: list[int] | None = None) -> str:
        item_repo = ItemRepository(session)
        room_repo = RoomRepository(session)

        items = await item_repo.get_all(limit=10000)
        if room_ids:
            items = [i for i in items if i.room_id in room_ids]

        rooms = await room_repo.get_all()
        room_map = {r.id: r.name for r in rooms}

        service = ExportService()
        return service.export_csv(items, room_map)

    @classmethod
    async def generate_json(cls, session: AsyncSession, room_ids: list[int] | None = None) -> str:
        item_repo = ItemRepository(session)
        room_repo = RoomRepository(session)

        items = await item_repo.get_all(limit=10000)
        if room_ids:
            items = [i for i in items if i.room_id in room_ids]

        rooms = await room_repo.get_all()
        room_map = {r.id: r.name for r in rooms}

        service = ExportService()
        return service.export_json(items, room_map)

    @classmethod
    async def generate_pdf(
        cls,
        session: AsyncSession,
        room_ids: list[int] | None = None,
        insurance_mode: bool = False,
    ) -> bytes:
        item_repo = ItemRepository(session)
        room_repo = RoomRepository(session)

        items = await item_repo.get_all(limit=10000)
        if room_ids:
            items = [i for i in items if i.room_id in room_ids]

        rooms = await room_repo.get_all()
        room_map = {r.id: r.name for r in rooms}

        service = ExportService()
        title = "Insurance Inventory Report" if insurance_mode else "Home Inventory Report"
        return service.export_pdf(items, room_map, title=title, insurance_mode=insurance_mode)
