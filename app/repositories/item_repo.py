from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import Item, ItemImage
from app.models.tag import Tag
from app.repositories.base import BaseRepository


class ItemRepository(BaseRepository[Item]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Item)

    async def get_with_relations(self, item_id: int) -> Item | None:
        stmt = (
            select(Item)
            .options(selectinload(Item.images), selectinload(Item.tags))
            .where(Item.id == item_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_room(self, room_id: int, offset: int = 0, limit: int = 100) -> list[Item]:
        stmt = (
            select(Item)
            .options(selectinload(Item.images))
            .where(Item.room_id == room_id)
            .offset(offset)
            .limit(limit)
            .order_by(Item.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        query: str | None = None,
        room_id: int | None = None,
        category: str | None = None,
        condition: str | None = None,
        status: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Item]:
        stmt = select(Item).options(selectinload(Item.images))

        if query:
            stmt = stmt.where(
                or_(
                    Item.name.ilike(f"%{query}%"),
                    Item.description.ilike(f"%{query}%"),
                )
            )
        if room_id:
            stmt = stmt.where(Item.room_id == room_id)
        if category:
            stmt = stmt.where(Item.category == category)
        if condition:
            stmt = stmt.where(Item.condition == condition)
        if status:
            stmt = stmt.where(Item.status == status)
        if min_value is not None:
            stmt = stmt.where(Item.estimated_value >= min_value)
        if max_value is not None:
            stmt = stmt.where(Item.estimated_value <= max_value)

        stmt = stmt.offset(offset).limit(limit).order_by(Item.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        total = await self.count()
        value_stmt = select(func.coalesce(func.sum(Item.estimated_value), 0))
        value_result = await self.session.execute(value_stmt)
        total_value = float(value_result.scalar_one())

        category_stmt = (
            select(Item.category, func.count(Item.id))
            .group_by(Item.category)
            .order_by(func.count(Item.id).desc())
        )
        cat_result = await self.session.execute(category_stmt)

        return {
            "total_items": total,
            "total_value": total_value,
            "by_category": {row[0]: row[1] for row in cat_result.all()},
        }

    async def add_image(self, item_id: int, image_path: str, image_type: str = "front") -> ItemImage:
        img = ItemImage(item_id=item_id, image_path=image_path, image_type=image_type)
        self.session.add(img)
        await self.session.flush()
        await self.session.refresh(img)
        return img

    async def add_tag(self, item_id: int, tag_name: str) -> None:
        item = await self.get_with_relations(item_id)
        if not item:
            return
        stmt = select(Tag).where(Tag.name == tag_name)
        result = await self.session.execute(stmt)
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            self.session.add(tag)
            await self.session.flush()
        if tag not in item.tags:
            item.tags.append(tag)
            await self.session.flush()

    async def get_recent(self, limit: int = 10) -> list[Item]:
        stmt = (
            select(Item)
            .options(selectinload(Item.images))
            .order_by(Item.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
