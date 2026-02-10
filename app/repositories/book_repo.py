from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.book import Book
from app.models.item import Item
from app.repositories.base import BaseRepository


class BookRepository(BaseRepository[Book]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Book)

    async def get_all_books(self, offset: int = 0, limit: int = 100) -> list[Book]:
        stmt = (
            select(Book)
            .options(selectinload(Item.images))
            .offset(offset)
            .limit(limit)
            .order_by(Book.title)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_books(
        self,
        query: str | None = None,
        author: str | None = None,
        genre: str | None = None,
        room_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Book]:
        stmt = select(Book)

        if query:
            stmt = stmt.where(
                Book.title.ilike(f"%{query}%")
                | Book.author.ilike(f"%{query}%")
                | Book.name.ilike(f"%{query}%")
            )
        if author:
            stmt = stmt.where(Book.author.ilike(f"%{author}%"))
        if genre:
            stmt = stmt.where(Book.genre == genre)
        if room_id:
            stmt = stmt.where(Book.room_id == room_id)

        stmt = stmt.offset(offset).limit(limit).order_by(Book.title)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_isbn(self, isbn: str) -> Book | None:
        stmt = select(Book).where(Book.isbn == isbn)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
