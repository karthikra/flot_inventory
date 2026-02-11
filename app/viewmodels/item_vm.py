from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book
from app.models.item import Item
from app.repositories.book_repo import BookRepository
from app.repositories.item_repo import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.value_estimator import calculate_depreciation


@dataclass
class ItemDetailViewModel:
    item: Item | None = None
    is_book: bool = False
    duplicate_warnings: list[dict] = field(default_factory=list)
    depreciation: dict | None = None

    @classmethod
    async def load(cls, session: AsyncSession, item_id: int) -> "ItemDetailViewModel":
        repo = ItemRepository(session)
        item = await repo.get_with_relations(item_id)
        if not item:
            return cls()

        dep = None
        if item.replacement_cost and item.purchase_date:
            dep = calculate_depreciation(
                item.replacement_cost, item.purchase_date, item.category or "other"
            )

        return cls(item=item, is_book=isinstance(item, Book), depreciation=dep)

    @classmethod
    async def create_item(cls, session: AsyncSession, data: ItemCreate) -> Item:
        repo = ItemRepository(session)
        item = await repo.create(**data.model_dump())
        await session.commit()
        return item

    @classmethod
    async def update_item(cls, session: AsyncSession, item_id: int, data: ItemUpdate) -> Item | None:
        repo = ItemRepository(session)
        updates = data.model_dump(exclude_unset=True)
        item = await repo.update(item_id, **updates)
        await session.commit()
        return item

    @classmethod
    async def delete_item(cls, session: AsyncSession, item_id: int) -> bool:
        repo = ItemRepository(session)
        result = await repo.delete(item_id)
        await session.commit()
        return result

    @classmethod
    async def update_status(cls, session: AsyncSession, item_id: int, status: str) -> Item | None:
        repo = ItemRepository(session)
        item = await repo.update(item_id, status=status)
        await session.commit()
        return item

    @classmethod
    async def add_image(cls, session: AsyncSession, item_id: int, image_path: str, image_type: str = "front"):
        repo = ItemRepository(session)
        img = await repo.add_image(item_id, image_path, image_type)
        await session.commit()
        return img

    @classmethod
    async def add_tag(cls, session: AsyncSession, item_id: int, tag_name: str):
        repo = ItemRepository(session)
        await repo.add_tag(item_id, tag_name)
        await session.commit()
