from __future__ import annotations

from dataclasses import dataclass

from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.application.consistency.cascade_consistency import CascadingConsistencyUseCase
from kosmo.application.consistency.evaluate_project_consistency import EvaluateProjectConsistencyUseCase
from kosmo.application.consistency.manage_consistency import (
    ApplyConsistencyEvaluationUseCase,
    BulkResolveConsistencyUseCase,
    DiscardConsistencyEvaluationUseCase,
    GetConsistencyActivityUseCase,
    GetConsistencyReviewUseCase,
    GetConsistencyStatusUseCase,
)
from kosmo.application.discovery import (
    GenerateDiscoveryUseCase,
    GetDiscoveryChatHistoryUseCase,
    GetDiscoveryUseCase,
    RefineDiscoveryUseCase,
    SaveDiscoveryUseCase,
)
from kosmo.application.features import (
    CreateCharacteristicUseCase,
    EditFeatureUseCase,
    GenerateFeaturesUseCase,
    SaveSelectedFeaturesUseCase,
    SuggestFeaturesUseCase,
)
from kosmo.application.features.check_feature_consistency import CheckFeatureConsistencyUseCase
from kosmo.application.features.delete_feature import DeleteFeatureUseCase
from kosmo.application.features.get_feature_chat_history import GetFeatureChatHistoryUseCase
from kosmo.application.features.list_features import ListFeaturesUseCase
from kosmo.application.integrations.delete_deployment import DeleteDeploymentUseCase
from kosmo.application.modelo import (
    DeleteActivityDiagramUseCase,
    GenerateActivityDiagramUseCase,
    GetActivityDiagramUseCase,
)
from kosmo.application.projects import (
    CreateProjectUseCase,
    DeleteProjectUseCase,
    GetProjectUseCase,
    ListProjectsUseCase,
)
from kosmo.application.requirements import (
    DeleteRequirementsUseCase,
    GenerateEARSUseCase,
    GetRequirementsUseCase,
    RefineRequirementsUseCase,
    RegenerateRequirementsUseCase,
    SaveRequirementsUseCase,
)
from kosmo.application.requirements.get_requirement_chat_history import GetRequirementChatHistoryUseCase
from kosmo.contracts.ai.consistency import ConsistencyEvaluator
from kosmo.contracts.auth.secrets import SecretCipher
from kosmo.contracts.integrations.deployment import DeploymentProviderPort, DeploymentWorkerPort
from kosmo.contracts.integrations.github import GitHubClientPort
from kosmo.contracts.sdd.codegen import WorkspaceManagerPort
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.infrastructure.api.composition.pipeline import PipelineComponents
from kosmo.infrastructure.persistence.postgres.registry import RepositoryRegistry
from kosmo.infrastructure.persistence.postgres.uow import SqlAlchemyUnitOfWork


@dataclass(frozen=True, slots=True)
class ProjectComponents:
    create_project: CreateProjectUseCase
    get_project: GetProjectUseCase
    list_projects: ListProjectsUseCase
    delete_project: DeleteProjectUseCase


def build_project_components(
    repos: RepositoryRegistry,
    pipeline: PipelineComponents,
    workspace_manager: WorkspaceManagerPort | None = None,
    github_client: GitHubClientPort | None = None,
    railway_client: DeploymentProviderPort | None = None,
    deployment_worker: DeploymentWorkerPort | None = None,
    cipher: SecretCipher | None = None,
    delete_deployment: DeleteDeploymentUseCase | None = None,
) -> ProjectComponents:
    return ProjectComponents(
        create_project=CreateProjectUseCase(project_repository=repos.projects),
        get_project=GetProjectUseCase(project_repository=repos.projects),
        list_projects=ListProjectsUseCase(project_repository=repos.projects),
        delete_project=DeleteProjectUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
            document_repo=repos.documents,
            chat_repo=repos.chat,
            consistency_evaluation_repo=repos.consistency_evaluations,
            traceability_repo=repos.traceability,
            agent_memory=pipeline.agent_memory,
            workspace_manager=workspace_manager,
            project_github_repo=repos.project_integrations,
            user_github_repo=repos.user_github_integrations,
            github_client=github_client,
            project_deployment_repo=repos.project_deployments,
            user_deployment_repo=repos.user_deployment_integrations,
            deployment_client=railway_client,
            deployment_worker=deployment_worker,
            cipher=cipher,
            delete_deployment=delete_deployment,
        ),
    )


@dataclass(frozen=True, slots=True)
class DiscoveryComponents:
    generate_discovery: GenerateDiscoveryUseCase
    get_discovery: GetDiscoveryUseCase
    save_discovery: SaveDiscoveryUseCase
    refine_discovery: RefineDiscoveryUseCase
    get_discovery_chat_history: GetDiscoveryChatHistoryUseCase
    consistency_evaluator: ConsistencyEvaluator
    document_repo: DocumentRepository


def build_discovery_components(
    repos: RepositoryRegistry,
    pipeline: PipelineComponents,
) -> DiscoveryComponents:
    consistency_evaluator: ConsistencyEvaluator = pipeline.consistency_evaluator

    return DiscoveryComponents(
        generate_discovery=GenerateDiscoveryUseCase(
            project_repo=repos.projects,
            document_repo=repos.documents,
            agent=pipeline.agent,
        ),
        get_discovery=GetDiscoveryUseCase(document_repo=repos.documents),
        save_discovery=SaveDiscoveryUseCase(
            document_repo=repos.documents,
            outbox=pipeline.outbox,
        ),
        refine_discovery=RefineDiscoveryUseCase(
            project_repo=repos.projects,
            document_repo=repos.documents,
            context_builder=pipeline.context_builder,
            agent=pipeline.agent,
            outbox=pipeline.outbox,
        ),
        get_discovery_chat_history=GetDiscoveryChatHistoryUseCase(
            project_repo=repos.projects,
            chat_repo=repos.chat,
        ),
        consistency_evaluator=consistency_evaluator,
        document_repo=repos.documents,
    )


@dataclass(frozen=True, slots=True)
class FeaturesComponents:
    generate_features: GenerateFeaturesUseCase
    suggest_features: SuggestFeaturesUseCase
    save_selected_features: SaveSelectedFeaturesUseCase
    create_characteristic: CreateCharacteristicUseCase
    feature_repo: FeatureRepository
    get_feature_chat_history: GetFeatureChatHistoryUseCase
    list_features: ListFeaturesUseCase
    edit_feature: EditFeatureUseCase
    check_feature_consistency: CheckFeatureConsistencyUseCase


def build_features_components(
    repos: RepositoryRegistry,
    pipeline: PipelineComponents,
    consistency_evaluator: ConsistencyEvaluator,
) -> FeaturesComponents:
    suggest_features = SuggestFeaturesUseCase(
        document_repo=repos.documents,
        feature_repo=repos.features,
        llm_client=pipeline.llm_client,
    )

    get_feature_chat_history = GetFeatureChatHistoryUseCase(
        feature_repo=repos.features,
        chat_repo=repos.chat,
    )

    return FeaturesComponents(
        generate_features=GenerateFeaturesUseCase(
            project_repo=repos.projects,
            document_repo=repos.documents,
            feature_repo=repos.features,
            agent=pipeline.agent,
        ),
        suggest_features=suggest_features,
        save_selected_features=SaveSelectedFeaturesUseCase(
            feature_repo=repos.features,
        ),
        create_characteristic=CreateCharacteristicUseCase(
            feature_repo=repos.features,
            document_repo=repos.documents,
            llm_client=pipeline.llm_client,
        ),
        feature_repo=repos.features,
        get_feature_chat_history=get_feature_chat_history,
        list_features=ListFeaturesUseCase(feature_repo=repos.features),
        edit_feature=EditFeatureUseCase(
            feature_repo=repos.features,
            consistency_evaluator=consistency_evaluator,
            outbox=pipeline.outbox,
        ),
        check_feature_consistency=CheckFeatureConsistencyUseCase(
            feature_repo=repos.features,
            consistency_evaluator=consistency_evaluator,
        ),
    )


@dataclass(frozen=True, slots=True)
class RequirementsComponents:
    generate_ears: GenerateEARSUseCase
    get_requirements: GetRequirementsUseCase
    save_requirements: SaveRequirementsUseCase
    refine_requirements: RefineRequirementsUseCase
    regenerate_requirements: RegenerateRequirementsUseCase
    delete_requirements: DeleteRequirementsUseCase
    get_requirement_chat_history: GetRequirementChatHistoryUseCase
    requirement_repo: RequirementRepository


def build_requirements_components(
    repos: RepositoryRegistry,
    pipeline: PipelineComponents,
    uow: SqlAlchemyUnitOfWork,
) -> RequirementsComponents:
    get_requirement_chat_history = GetRequirementChatHistoryUseCase(
        feature_repo=repos.features,
        chat_repo=repos.chat,
    )

    return RequirementsComponents(
        generate_ears=GenerateEARSUseCase(
            uow=uow,
            agent=pipeline.agent,
        ),
        get_requirements=GetRequirementsUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
        ),
        save_requirements=SaveRequirementsUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            outbox=pipeline.outbox,
        ),
        refine_requirements=RefineRequirementsUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            agent=pipeline.agent,
            outbox=pipeline.outbox,
        ),
        regenerate_requirements=RegenerateRequirementsUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            agent=pipeline.agent,
            outbox=pipeline.outbox,
        ),
        delete_requirements=DeleteRequirementsUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
        ),
        get_requirement_chat_history=get_requirement_chat_history,
        requirement_repo=repos.requirements,
    )


@dataclass(frozen=True, slots=True)
class ModeloComponents:
    generate_diagram: GenerateActivityDiagramUseCase
    get_diagram: GetActivityDiagramUseCase
    delete_diagram: DeleteActivityDiagramUseCase
    diagram_repo: ActivityDiagramRepository


def build_modelo_components(repos: RepositoryRegistry, pipeline: PipelineComponents) -> ModeloComponents:
    return ModeloComponents(
        generate_diagram=GenerateActivityDiagramUseCase(
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
            agent=pipeline.agent,
            project_repo=repos.projects,
        ),
        get_diagram=GetActivityDiagramUseCase(
            feature_repo=repos.features,
            diagram_repo=repos.diagrams,
        ),
        delete_diagram=DeleteActivityDiagramUseCase(
            feature_repo=repos.features,
            diagram_repo=repos.diagrams,
        ),
        diagram_repo=repos.diagrams,
    )


@dataclass(frozen=True, slots=True)
class ConsistencyComponents:
    evaluate_project_consistency: EvaluateProjectConsistencyUseCase
    cascade_consistency: CascadingConsistencyUseCase
    apply_consistency_impacts: ApplyConsistencyImpactsUseCase
    delete_feature: DeleteFeatureUseCase
    consistency_status: GetConsistencyStatusUseCase
    consistency_review: GetConsistencyReviewUseCase
    apply_consistency_evaluation: ApplyConsistencyEvaluationUseCase
    discard_consistency_evaluation: DiscardConsistencyEvaluationUseCase
    bulk_resolve_consistency: BulkResolveConsistencyUseCase
    consistency_activity: GetConsistencyActivityUseCase


def build_consistency_components(
    repos: RepositoryRegistry,
    evaluator: ConsistencyEvaluator,
    uow: SqlAlchemyUnitOfWork,
) -> ConsistencyComponents:
    apply_impacts = ApplyConsistencyImpactsUseCase(uow=uow)

    evaluation_repo = repos.consistency_evaluations
    apply_evaluation = ApplyConsistencyEvaluationUseCase(
        evaluation_repo=evaluation_repo,
        apply_uc=apply_impacts,
        document_repo=repos.documents,
        feature_repo=repos.features,
        requirement_repo=repos.requirements,
        diagram_repo=repos.diagrams,
        implementation_repo=repos.implementations,
    )
    discard_evaluation = DiscardConsistencyEvaluationUseCase(evaluation_repo=evaluation_repo)

    return ConsistencyComponents(
        evaluate_project_consistency=EvaluateProjectConsistencyUseCase(
            project_repo=repos.projects,
            evaluator=evaluator,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
        ),
        cascade_consistency=CascadingConsistencyUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
            evaluator=evaluator,
        ),
        apply_consistency_impacts=apply_impacts,
        delete_feature=DeleteFeatureUseCase(
            project_repo=repos.projects,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
            traceability_repo=repos.traceability,
        ),
        consistency_status=GetConsistencyStatusUseCase(evaluation_repo=evaluation_repo),
        consistency_review=GetConsistencyReviewUseCase(
            evaluation_repo=evaluation_repo,
            document_repo=repos.documents,
            feature_repo=repos.features,
            requirement_repo=repos.requirements,
            diagram_repo=repos.diagrams,
            implementation_repo=repos.implementations,
        ),
        apply_consistency_evaluation=apply_evaluation,
        discard_consistency_evaluation=discard_evaluation,
        bulk_resolve_consistency=BulkResolveConsistencyUseCase(
            evaluation_repo=evaluation_repo,
            apply_uc=apply_evaluation,
            discard_uc=discard_evaluation,
        ),
        consistency_activity=GetConsistencyActivityUseCase(evaluation_repo=evaluation_repo),
    )
