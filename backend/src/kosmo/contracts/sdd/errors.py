from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ulid import ULID


@dataclass
class Violation:
    loc: list[str]
    msg: str
    input: Any = None


@dataclass
class ProblemDetail:
    type: str
    title: str
    status: int
    detail: str
    instance: str
    trace_id: str = field(default_factory=lambda: ULID().hex)
    violations: list[Violation] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class SpecError(Exception):
    def __init__(self, problem: ProblemDetail) -> None:
        self.problem = problem
        super().__init__(problem.detail)


class ProjectNotFoundError(SpecError):
    def __init__(
        self,
        *,
        project_id: str,
        instance: str = "/api/v1/projects",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:projects:not-found",
            title="Proyecto no encontrado",
            status=404,
            detail=f"El proyecto {project_id} no existe",
            instance=instance,
        )
        super().__init__(problem)


class FeatureNotFoundError(SpecError):
    def __init__(
        self,
        *,
        feature_id: str,
        instance: str = "/api/v1/features",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:features:not-found",
            title="Feature no encontrada",
            status=404,
            detail=f"La feature {feature_id} no existe o no pertenece al proyecto",
            instance=instance,
        )
        super().__init__(problem)


class RequirementsNotFoundError(SpecError):
    def __init__(
        self,
        *,
        feature_id: str,
        instance: str = "/api/v1/requirements",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:requirements:not-found",
            title="Requisitos no encontrados",
            status=404,
            detail=f"La feature {feature_id} no tiene requisitos generados",
            instance=instance,
        )
        super().__init__(problem)


class DocumentValidationError(SpecError):
    def __init__(
        self,
        *,
        detail: str,
        violations: list[Violation] | None = None,
        instance: str = "/api/v1/discovery",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:document:invalid-structure",
            title="Documento inválido",
            status=422,
            detail=detail,
            instance=instance,
            violations=violations or [],
        )
        super().__init__(problem)


class DocumentNotFoundError(SpecError):
    def __init__(
        self,
        *,
        document_type: str,
        instance: str = "/api/v1/discovery",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:document:not-found",
            title="Documento no encontrado",
            status=404,
            detail=f"El documento de tipo {document_type} no existe",
            instance=instance,
        )
        super().__init__(problem)


class MarkdownParseError(SpecError):
    def __init__(
        self,
        *,
        detail: str,
        instance: str = "/api/v1/discovery",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:document:parse-error",
            title="Error de parseo Markdown",
            status=422,
            detail=detail,
            instance=instance,
        )
        super().__init__(problem)


class LLMInvocationError(SpecError):
    def __init__(
        self,
        *,
        detail: str,
        instance: str = "/api/v1/pipeline",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:llm:invocation-error",
            title="Error de invocación al modelo de IA",
            status=502,
            detail=detail,
            instance=instance,
        )
        super().__init__(problem)


class AIProviderAuthError(SpecError):
    def __init__(
        self,
        *,
        detail: str = (
            "Tu clave de API de IA no es válida o ha expirado. "
            "Por favor, revísala y actualízala en la pestaña de IA de tu perfil."
        ),
        instance: str = "/api/v1/ai",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:ai:auth-error",
            title="Clave de API inválida o expirada",
            status=422,
            detail=detail,
            instance=instance,
        )
        super().__init__(problem)


class DiagramNotFoundError(SpecError):
    def __init__(
        self,
        *,
        feature_id: str,
        instance: str = "/api/v1/diagrams",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:diagrams:not-found",
            title="Diagrama no encontrado",
            status=404,
            detail=f"La feature {feature_id} no tiene un diagrama de actividad generado",
            instance=instance,
        )
        super().__init__(problem)


class PlanChangeNotFoundError(SpecError):
    def __init__(
        self,
        *,
        change_id: str,
        instance: str = "/api/v1/plan",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:plan:change-not-found",
            title="Cambio no encontrado en el plan",
            status=404,
            detail=f"El cambio {change_id} no existe en el plan de cambios",
            instance=instance,
        )
        super().__init__(problem)


class ConsistencyStaleError(SpecError):
    def __init__(
        self,
        *,
        evaluation_id: str,
        detail: str,
        instance: str = "/api/v1/consistency",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:consistency:stale",
            title="La sugerencia ya no aplica",
            status=409,
            detail=detail,
            instance=f"{instance}/evaluations/{evaluation_id}/apply",
        )
        super().__init__(problem)


class ConsistencyEvaluationNotFoundError(SpecError):
    def __init__(
        self,
        *,
        evaluation_id: str,
        instance: str = "/api/v1/consistency",
    ) -> None:
        problem = ProblemDetail(
            type="urn:kosmo:consistency:evaluation-not-found",
            title="Evaluación de consistencia no encontrada",
            status=404,
            detail=f"La evaluación {evaluation_id} no existe",
            instance=f"{instance}/evaluations/{evaluation_id}",
        )
        super().__init__(problem)


class ChatSessionNotFoundError(SpecError):
    def __init__(
        self,
        *,
        session_id: str,
        project_id: str | None = None,
        instance: str = "/api/v1/chat-sessions",
    ) -> None:
        detail = (
            f"La sesión de chat '{session_id}' no existe o no pertenece al proyecto '{project_id}'."
            if project_id
            else f"La sesión de chat '{session_id}' no existe o no pertenece al proyecto."
        )
        problem = ProblemDetail(
            type="urn:kosmo:chat:session-not-found",
            title="Sesión de chat no encontrada",
            status=404,
            detail=detail,
            instance=instance,
        )
        super().__init__(problem)
