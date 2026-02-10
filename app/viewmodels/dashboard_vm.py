from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository


@dataclass
class DashboardViewModel:
    total_items: int = 0
    total_value: float = 0.0
    total_rooms: int = 0
    rooms: list[dict] = field(default_factory=list)
    recent_items: list = field(default_factory=list)
    by_category: dict[str, int] = field(default_factory=dict)
    needs_attention: list = field(default_factory=list)

    @classmethod
    async def load(cls, session: AsyncSession) -> "DashboardViewModel":
        room_repo = RoomRepository(session)
        item_repo = ItemRepository(session)

        rooms_with_stats = await room_repo.get_all_with_stats()
        stats = await item_repo.get_stats()
        recent = await item_repo.get_recent(limit=8)

        # items with low confidence or needing attention
        needs_attention = [
            item for item in recent
            if item.confidence_score is not None and item.confidence_score < 0.7
        ]

        return cls(
            total_items=stats["total_items"],
            total_value=stats["total_value"],
            total_rooms=len(rooms_with_stats),
            rooms=rooms_with_stats,
            recent_items=recent,
            by_category=stats["by_category"],
            needs_attention=needs_attention,
        )
