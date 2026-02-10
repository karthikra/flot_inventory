from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository
from app.schemas.room import RoomCreate, RoomUpdate


@dataclass
class RoomListViewModel:
    rooms: list[dict] = field(default_factory=list)

    @classmethod
    async def load(cls, session: AsyncSession) -> "RoomListViewModel":
        repo = RoomRepository(session)
        rooms = await repo.get_all_with_stats()
        return cls(rooms=rooms)


@dataclass
class RoomDetailViewModel:
    room: Room | None = None
    items: list = field(default_factory=list)
    item_count: int = 0
    total_value: float = 0.0

    @classmethod
    async def load(cls, session: AsyncSession, room_id: int) -> "RoomDetailViewModel":
        room_repo = RoomRepository(session)
        item_repo = ItemRepository(session)

        room = await room_repo.get_with_items(room_id)
        if not room:
            return cls()

        items = await item_repo.get_by_room(room_id)
        total_value = sum(i.estimated_value or 0 for i in items)

        return cls(
            room=room,
            items=items,
            item_count=len(items),
            total_value=total_value,
        )

    @classmethod
    async def create_room(cls, session: AsyncSession, data: RoomCreate) -> Room:
        repo = RoomRepository(session)
        room = await repo.create(
            name=data.name,
            description=data.description,
            floor=data.floor,
        )
        await session.commit()
        return room

    @classmethod
    async def update_room(cls, session: AsyncSession, room_id: int, data: RoomUpdate) -> Room | None:
        repo = RoomRepository(session)
        updates = data.model_dump(exclude_unset=True)
        room = await repo.update(room_id, **updates)
        await session.commit()
        return room

    @classmethod
    async def delete_room(cls, session: AsyncSession, room_id: int) -> bool:
        repo = RoomRepository(session)
        result = await repo.delete(room_id)
        await session.commit()
        return result
