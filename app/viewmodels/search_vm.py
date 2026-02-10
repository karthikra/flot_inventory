from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository


@dataclass
class SearchViewModel:
    query: str = ""
    room_id: int | None = None
    category: str | None = None
    condition: str | None = None
    status: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    results: list[Item] = field(default_factory=list)
    rooms: list = field(default_factory=list)
    total_results: int = 0

    @classmethod
    async def load(cls, session: AsyncSession) -> "SearchViewModel":
        room_repo = RoomRepository(session)
        rooms = await room_repo.get_all()
        return cls(rooms=rooms)

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        query: str = "",
        room_id: int | None = None,
        category: str | None = None,
        condition: str | None = None,
        status: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> "SearchViewModel":
        room_repo = RoomRepository(session)
        item_repo = ItemRepository(session)
        rooms = await room_repo.get_all()

        results = await item_repo.search(
            query=query or None,
            room_id=room_id,
            category=category,
            condition=condition,
            status=status,
            min_value=min_value,
            max_value=max_value,
        )

        return cls(
            query=query,
            room_id=room_id,
            category=category,
            condition=condition,
            status=status,
            min_value=min_value,
            max_value=max_value,
            results=results,
            rooms=rooms,
            total_results=len(results),
        )
