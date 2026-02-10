from typing import Any, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository[T]:
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def get(self, id: int) -> T | None:
        return await self.session.get(self.model, id)

    async def get_all(self, offset: int = 0, limit: int = 100) -> list[T]:
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> T:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: int, **kwargs: Any) -> T | None:
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if not kwargs:
            return await self.get(id)
        stmt = update(self.model).where(self.model.id == id).values(**kwargs)
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get(id)

    async def delete(self, id: int) -> bool:
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()
