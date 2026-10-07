from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.application.chat.chat_sessions import (
    CreateChatSessionUseCase,
    DeleteChatSessionUseCase,
    ListChatSessionsUseCase,
)
from kosmo.application.chat.process_chat_message import ProcessChatMessageUseCase
from kosmo.application.chat.process_chat_modification import ProcessChatModificationUseCase
from kosmo.application.chat.validate_phase_context import ValidatePhaseContextUseCase
from kosmo.application.consistency.evaluate_consistency import EvaluateConsistencyUseCase
from kosmo.application.knowledge import ConsolidateKnowledgePatterns
from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.application.pipeline.kosmo_agent import KOSMOAgent
from kosmo.config import Settings
from kosmo.contracts.ai.chat import ChatRepository
from kosmo.contracts.ai.consistency import ConsistencyEvaluator, TraceabilityRepository
from kosmo.contracts.llm.ports import Embedder, LLMClient
from kosmo.contracts.memory.agent_memory import AgentMemoryPort, KnowledgePatternStore
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.domain.pipeline.knowledge_tool_registry import KnowledgeToolRegistry
from kosmo.domain.pipeline.skill_registry import SkillRegistry
from kosmo.infrastructure.api.composition.skill_registration import build_skill_registry
from kosmo.infrastructure.llm.dynamic_llm_client import (
    DynamicUserLLMClient,
    build_pydantic_ai_model,
)
from kosmo.infrastructure.llm.embedder import OpenAIEmbedder
from kosmo.infrastructure.llm.knowledge_tools import (
    build_find_similar_sessions,
    build_get_diagram_for_feature,
    build_get_downstream_artifacts,
    build_get_impact,
    build_get_phase_document,
    build_get_requirements_for_feature,
)
from kosmo.infrastructure.llm.noop_adapter import NoopLLMClient
from kosmo.infrastructure.llm.pydantic_ai_adapter import PydanticAILLMClient
from kosmo.infrastructure.persistence.postgres.outbox import OutboxStore
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.persistence.postgres.repositories.agent_memory_repo import (
    SqlAlchemyAgentSessionStore,
    SqlAlchemyKnowledgePatternStore,
)
from kosmo.infrastructure.security import FernetSecretCipher


@dataclass(frozen=True, slots=True)
class PipelineComponents:
    llm_client: LLMClient
    context_builder: ContextBuilder
    agent: AgentPort
    skill_registry: SkillRegistry
    agent_memory: AgentMemoryPort
    pattern_store: KnowledgePatternStore
    validate_phase_context: ValidatePhaseContextUseCase
    process_chat_message: ProcessChatMessageUseCase
    process_chat_modification: ProcessChatModificationUseCase
    consistency_evaluator: ConsistencyEvaluator
    chat_repo: ChatRepository
    traceability_repo: TraceabilityRepository
    outbox: OutboxStore
    consolidate_patterns: ConsolidateKnowledgePatterns
    create_chat_session: CreateChatSessionUseCase
    list_chat_sessions: ListChatSessionsUseCase
    delete_chat_session: DeleteChatSessionUseCase


def _build_embedder(settings: Settings) -> Embedder | None:
    if settings.embedding_provider == "none":
        return None
    if settings.embedding_provider == "openai" and settings.llm_api_key:
        return OpenAIEmbedder(api_key=settings.llm_api_key.get_secret_value())
    if settings.embedding_provider == "fastembed":
        from kosmo.infrastructure.llm.local_embedder import FastembedEmbedder

        return FastembedEmbedder()
    if settings.embedding_provider == "auto":
        if settings.llm_provider.lower() == "openai" and settings.llm_api_key:
            return OpenAIEmbedder(api_key=settings.llm_api_key.get_secret_value())
        try:
            from kosmo.infrastructure.llm.local_embedder import FastembedEmbedder

            return FastembedEmbedder()
        except ImportError:
            return None
    return None


def build_pipeline_components(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    repos: RepositoryRegistry,
) -> PipelineComponents:
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    if settings.fernet_master_key is not None:
        cipher = FernetSecretCipher(settings.fernet_master_key.get_secret_value())
        llm_client: LLMClient = DynamicUserLLMClient(
            config_repo=repos.user_ai_configs,
            cipher=cipher,
            default_provider=settings.llm_provider,
            default_model=settings.llm_model,
            default_api_key=api_key,
            max_concurrency=settings.llm_max_concurrency,
            cache_ttl_seconds=settings.user_ai_config_cache_ttl_seconds,
        )
    elif settings.llm_provider.lower() == "noop":
        llm_client = NoopLLMClient()
    else:
        model = build_pydantic_ai_model(settings.llm_provider, settings.llm_model, api_key)
        llm_client = PydanticAILLMClient(model=model)

    context_builder = ContextBuilder(
        document_repo=repos.documents,
        project_repo=repos.projects,
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
    )

    agent_memory = SqlAlchemyAgentSessionStore(session_factory)
    pattern_store = SqlAlchemyKnowledgePatternStore(session_factory)

    skill_registry = build_skill_registry()

    embedding_generator = _build_embedder(settings)

    knowledge_tools = KnowledgeToolRegistry()
    knowledge_tools.register(*build_get_phase_document(repos.documents))
    knowledge_tools.register(*build_get_downstream_artifacts(repos.features))
    knowledge_tools.register(*build_get_requirements_for_feature(repos.requirements))
    knowledge_tools.register(*build_get_diagram_for_feature(repos.diagrams))
    if embedding_generator is not None:
        knowledge_tools.register(*build_find_similar_sessions(agent_memory, embedding_generator))
    knowledge_tools.register(*build_get_impact(repos.traceability))

    outbox = OutboxStore(session_factory)

    agent = KOSMOAgent(
        llm_client=llm_client,
        skill_registry=skill_registry,
        memory=agent_memory,
        embedding_generator=embedding_generator,
        knowledge_tools=knowledge_tools,
        pattern_store=pattern_store,
        outbox=outbox,
    )

    validate_phase_context = ValidatePhaseContextUseCase()

    consistency_evaluator: ConsistencyEvaluator = EvaluateConsistencyUseCase(
        agent=agent,
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
        diagram_repo=repos.diagrams,
        document_repo=repos.documents,
        implementation_repo=repos.implementations,
    )

    process_chat_message = ProcessChatMessageUseCase(
        chat_repo=repos.chat,
        agent=agent,
        skill_registry=skill_registry,
        project_repo=repos.projects,
        document_repo=repos.documents,
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
        outbox=outbox,
        consistency_evaluator=consistency_evaluator,
    )

    process_chat_modification = ProcessChatModificationUseCase(
        document_repo=repos.documents,
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
        llm_client=llm_client,
        outbox=outbox,
    )

    consolidate_patterns = ConsolidateKnowledgePatterns(
        memory=agent_memory,
        pattern_store=pattern_store,
        llm_client=llm_client,
    )

    return PipelineComponents(
        llm_client=llm_client,
        context_builder=context_builder,
        agent=agent,
        skill_registry=skill_registry,
        agent_memory=agent_memory,
        pattern_store=pattern_store,
        validate_phase_context=validate_phase_context,
        process_chat_message=process_chat_message,
        process_chat_modification=process_chat_modification,
        consistency_evaluator=consistency_evaluator,
        chat_repo=repos.chat,
        traceability_repo=repos.traceability,
        outbox=outbox,
        consolidate_patterns=consolidate_patterns,
        create_chat_session=CreateChatSessionUseCase(chat_repo=repos.chat),
        list_chat_sessions=ListChatSessionsUseCase(chat_repo=repos.chat),
        delete_chat_session=DeleteChatSessionUseCase(chat_repo=repos.chat),
    )
