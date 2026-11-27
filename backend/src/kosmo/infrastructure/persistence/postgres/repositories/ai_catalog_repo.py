from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.ai.catalog import AiCatalogRepository, CatalogModel, ModelTier
from kosmo.infrastructure.persistence.postgres.models import AiCatalogModel


class SqlAlchemyAiCatalogRepository(AiCatalogRepository):
    """Implementación PostgreSQL del puerto de catálogo de modelos."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_entity(model: AiCatalogModel) -> CatalogModel:
        return CatalogModel(
            id=model.id,
            provider=model.provider,
            model_id=model.model_id,
            opencode_model_id=model.opencode_model_id,
            display_name=model.display_name,
            tier=ModelTier(model.tier),
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            supports_tools=model.supports_tools,
            supports_vision=model.supports_vision,
            opencode_compatible=model.opencode_compatible,
            is_active=model.is_active,
            is_deprecated=model.is_deprecated,
            shutdown_date=model.shutdown_date,
            metadata_json=model.metadata_json,
            last_discovered_at=model.last_discovered_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def list_active(self, provider: str | None = None) -> list[CatalogModel]:
        async with self._session_factory() as session:
            stmt = select(AiCatalogModel).where(
                AiCatalogModel.is_active.is_(True),
                AiCatalogModel.opencode_compatible.is_(True),
            )
            if provider:
                stmt = stmt.where(AiCatalogModel.provider == provider)
            stmt = stmt.order_by(AiCatalogModel.provider, AiCatalogModel.tier)
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def get_by_provider_and_model(self, provider: str, model_id: str) -> CatalogModel | None:
        async with self._session_factory() as session:
            stmt = (
                select(AiCatalogModel)
                .where(
                    AiCatalogModel.provider == provider,
                    or_(
                        AiCatalogModel.model_id == model_id,
                        AiCatalogModel.opencode_model_id == model_id,
                    ),
                )
                .order_by(
                    (AiCatalogModel.model_id == model_id).desc(),
                    AiCatalogModel.is_active.desc(),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            model = result.scalars().first()
            return self._to_entity(model) if model else None

    async def upsert_batch(self, models: list[CatalogModel]) -> None:
        if not models:
            return
        async with self._session_factory() as session:
            for entity in models:
                now = datetime.now(UTC)
                insert_stmt = pg.insert(AiCatalogModel).values(
                    id=entity.id,
                    provider=entity.provider,
                    model_id=entity.model_id,
                    opencode_model_id=entity.opencode_model_id,
                    display_name=entity.display_name,
                    tier=entity.tier.value,
                    context_window=entity.context_window,
                    max_output_tokens=entity.max_output_tokens,
                    supports_tools=entity.supports_tools,
                    supports_vision=entity.supports_vision,
                    opencode_compatible=entity.opencode_compatible,
                    is_active=entity.is_active,
                    is_deprecated=entity.is_deprecated,
                    shutdown_date=entity.shutdown_date,
                    metadata_json=entity.metadata_json,
                    last_discovered_at=entity.last_discovered_at,
                    created_at=entity.created_at,
                    updated_at=now,
                )
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    constraint="uq_ai_catalog_provider_model",
                    set_={
                        "opencode_model_id": insert_stmt.excluded.opencode_model_id,
                        "display_name": insert_stmt.excluded.display_name,
                        "tier": insert_stmt.excluded.tier,
                        "context_window": insert_stmt.excluded.context_window,
                        "max_output_tokens": insert_stmt.excluded.max_output_tokens,
                        "supports_tools": insert_stmt.excluded.supports_tools,
                        "supports_vision": insert_stmt.excluded.supports_vision,
                        "opencode_compatible": insert_stmt.excluded.opencode_compatible,
                        "is_active": insert_stmt.excluded.is_active,
                        "is_deprecated": insert_stmt.excluded.is_deprecated,
                        "shutdown_date": insert_stmt.excluded.shutdown_date,
                        "metadata_json": insert_stmt.excluded.metadata_json,
                        "last_discovered_at": insert_stmt.excluded.last_discovered_at,
                        "updated_at": now,
                    },
                )
                await session.execute(upsert_stmt)
            await session.commit()

    async def mark_unseen_as_retired(self, provider: str, seen_model_ids: set[str]) -> None:
        if not seen_model_ids:
            return
        async with self._session_factory() as session:
            stmt = (
                update(AiCatalogModel)
                .where(
                    AiCatalogModel.provider == provider,
                    AiCatalogModel.model_id.notin_(seen_model_ids),
                )
                .values(is_active=False, is_deprecated=True, updated_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()
