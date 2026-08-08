from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository[ModelT]:
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, object_id: Any) -> ModelT | None:
        return await self.session.get(self.model, object_id)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ModelT]:
        statement = select(self.model).offset(offset)

        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def create(
        self,
        data: Mapping[str, Any],
        *,
        commit: bool = True,
        refresh: bool = True,
    ) -> ModelT:
        db_object = self.model(**dict(data))
        self.session.add(db_object)

        if commit:
            await self.session.commit()

        if refresh:
            await self.session.refresh(db_object)

        return db_object

    async def update(
        self,
        db_object: ModelT,
        data: Mapping[str, Any],
        *,
        commit: bool = True,
        refresh: bool = True,
    ) -> ModelT:
        for field, value in data.items():
            setattr(db_object, field, value)

        if commit:
            await self.session.commit()

        if refresh:
            await self.session.refresh(db_object)

        return db_object

    async def delete(
        self,
        db_object: ModelT,
        *,
        commit: bool = True,
    ) -> None:
        await self.session.delete(db_object)

        if commit:
            await self.session.commit()
