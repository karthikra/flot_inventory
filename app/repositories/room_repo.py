from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import Item
from app.models.room import Room
from app.repositories.base import BaseRepository


class RoomRepository(BaseRepository[Room]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Room)

    async def get_with_items(self, room_id: int) -> Room | None:
        stmt = select(Room).options(selectinload(Room.items)).where(Room.id == room_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Room | None:
        stmt = select(Room).where(Room.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_with_stats(self) -> list[dict]:
        stmt = (
            select(
                Room,
                func.count(Item.id).label("item_count"),
                func.coalesce(func.sum(Item.estimated_value), 0).label("total_value"),
            )
            .outerjoin(Item, Room.id == Item.room_id)
            .group_by(Room.id)
            .order_by(Room.name)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            {"room": row[0], "item_count": row[1], "total_value": float(row[2])}
            for row in rows
        ]
