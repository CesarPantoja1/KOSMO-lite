from __future__ import annotations

from ulid import ULID

_PREFIX_MAP: dict[str, str] = {
    "project": "prj_",
    "feature": "feat_",
    "spec": "spec_",
    "task": "tsk_",
    "user": "usr_",
    "apikey": "apk_",
    "audit": "aud_",
    "pipeline": "pipe_",
    "requirement": "req_",
    "agent_memory": "agm_",
    "knowledge_pattern": "kpat_",
    "chat_history": "chh_",
    "chat_message": "msg_",
    "plan_change": "chg_",
    "outbox": "out_",
    "doc_version": "dver_",
    "trace_edge": "ted_",
    "user_pref": "upf_",
    "consistency_evaluation": "cev_",
    "chat_session": "cht_",
    "operation": "ope_",
    "workspace": "ws_",
    "code_workspace": "ws_",
    "implementation": "impl_",
    "feature_implementation": "impl_",
    "ai_config": "uai_",
    "user_ai_config": "uai_",
    "user_integration": "uint_",
    "integration": "uint_",
    "project_integration": "pint_",
    "code_sync_log": "csync_",
}


class IdGenerator:
    @staticmethod
    def generate(entity: str) -> str:
        prefix = _PREFIX_MAP.get(entity)
        if prefix is None:
            raise ValueError(f"Entidad desconocida: {entity}. Valores validos: {sorted(_PREFIX_MAP.keys())}")
        return f"{prefix}{ULID()}"
