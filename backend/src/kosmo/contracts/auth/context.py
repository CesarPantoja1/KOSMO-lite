from __future__ import annotations

import contextvars

current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_user_id", default=None)
