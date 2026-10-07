import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from kosmo.contracts.audit import AuditEvent, AuditEventSink, AuditOutcome
from kosmo.contracts.auth import (
    PasswordHasher,
    User,
    UserAlreadyExistsError,
    UserRepository,
)
from kosmo.contracts.telemetry import record_auth_event, traced
from kosmo.domain.sdd.id_generator import IdGenerator


@dataclass(frozen=True, slots=True)
class RegisterUser:
    user_repository: UserRepository
    password_hasher: PasswordHasher
    audit_sink: AuditEventSink

    @traced("auth.register")
    async def execute(self, *, name: str, email: str, password: str) -> User:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre no puede estar vacío")
        normalized_email = email.strip().lower()
        existing = await self.user_repository.by_email(normalized_email)
        hashed_password = await asyncio.to_thread(self.password_hasher.hash, password)
        if existing is not None:
            await self.audit_sink.record(
                AuditEvent(
                    event_type="auth.register",
                    outcome=AuditOutcome.FAILURE,
                    occurred_at=datetime.now(UTC),
                    actor_id=existing.id,
                    actor_email=normalized_email,
                )
            )
            record_auth_event("register_duplicate", user_id=existing.id)
            raise UserAlreadyExistsError("Email ya registrado")
        user = User(
            id=IdGenerator.generate("user"),
            email=normalized_email,
            name=normalized_name,
            avatar_url=None,
            hashed_password=hashed_password,
            created_at=datetime.now(UTC),
        )
        await self.user_repository.create(user)
        await self.audit_sink.record(
            AuditEvent(
                event_type="auth.register",
                outcome=AuditOutcome.SUCCESS,
                occurred_at=datetime.now(UTC),
                actor_id=user.id,
                actor_email=normalized_email,
            )
        )
        record_auth_event("register_success", user_id=user.id)
        return user
