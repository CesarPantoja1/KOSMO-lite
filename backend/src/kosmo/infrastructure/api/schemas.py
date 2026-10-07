"""DTOs Pydantic expuestos por la API HTTP.

Pertenecen al adaptador de entrada (FastAPI), por lo que viven en infraestructura
y pueden referenciar entidades de dominio para conversión I/O sin invertir capas.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from kosmo.contracts.ai.chat import HistorialChat, MensajeChat
from kosmo.contracts.auth import TokenPair

# Enumeraciones de negocio


class CodeChallengeMethod(StrEnum):
    """Método de transformación PKCE permitido por el servidor.

    Actualmente solo se acepta S256 (SHA-256), que es el estándar
    recomendado por RFC 7636 y el único permitido en KOSMO.
    """

    S256 = "S256"


class GrantType(StrEnum):
    """Tipo de concesión OAuth 2.0 soportado en el endpoint /token."""

    authorization_code = "authorization_code"


class RefreshGrantType(StrEnum):
    """Tipo de concesión para renovar un par de tokens mediante refresh token."""

    refresh_token = "refresh_token"


class TokenType(StrEnum):
    """Esquema de autenticación que debe adjuntarse en el header Authorization."""

    Bearer = "Bearer"


# Scopes de acceso disponibles en KOSMO

KNOWN_SCOPES: list[str] = [
    "profile:read",
    "profile:write",
    "agent:run",
    "agent:read",
    "admin",
]
"""Scopes reconocidos por el sistema.

El servidor no rechaza scopes desconocidos para permitir extensibilidad, pero
el Frontend debe presentar únicamente los de esta lista al usuario (se puede
extender, no está definido ni cerrado al cambio).
"""

# Requests


class RegisterRequest(BaseModel):
    """Payload para crear una nueva cuenta de usuario en KOSMO."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Nombre completo del usuario (obligatorio).",
        examples=["Gianfranco"],
    )
    email: EmailStr = Field(
        description=(
            "Dirección de correo electrónico del nuevo usuario. "
            "Debe ser única en el sistema; intentar registrar un email ya existente "
            "devuelve 409 Conflict."
        ),
        examples=["usuario@ejemplo.com"],
    )
    password: str = Field(
        min_length=12,
        max_length=128,
        description=(
            "Contraseña en texto plano. El servidor la procesa con Argon2id "
            "(OWASP 2025) antes de persistirla; jamás se almacena en claro. "
            "Mínimo 12 caracteres, máximo 128."
        ),
        examples=["M1ContraseñaSegura!"],
    )


class AuthorizeRequest(BaseModel):
    """Payload para iniciar el flujo PKCE y obtener un código de autorización.

    El cliente genera un ``code_verifier`` aleatorio (43-128 chars, Base64URL),
    calcula ``code_challenge = BASE64URL(SHA256(code_verifier))`` y envía
    el challenge aquí. El verifier se usa después en ``/token``.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        description="Email del usuario que intenta autenticarse.",
        examples=["usuario@ejemplo.com"],
    )
    password: str = Field(
        min_length=1,
        max_length=128,
        description="Contraseña en texto plano del usuario.",
        examples=["M1ContraseñaSegura!"],
    )
    code_challenge: str = Field(
        min_length=43,
        max_length=128,
        description=(
            "Hash SHA-256 del ``code_verifier``, codificado en Base64URL sin padding. "
            "Se almacena en caché por 5 minutos y se valida en el intercambio de tokens."
        ),
        examples=["E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"],
    )
    code_challenge_method: CodeChallengeMethod = Field(
        default=CodeChallengeMethod.S256,
        description="Método de transformación del code_challenge. Solo se acepta 'S256'.",
        examples=["S256"],
    )
    scopes: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de permisos solicitados para la sesión. "
            f"Valores reconocidos: {', '.join(KNOWN_SCOPES)}. "
            "Se pueden solicitar múltiples scopes en la misma llamada."
        ),
        examples=[["profile:read", "agent:run"]],
    )


class TokenExchangeRequest(BaseModel):
    """Payload para intercambiar el código de autorización por un par de tokens JWT."""

    model_config = ConfigDict(extra="forbid")

    grant_type: GrantType = Field(
        description="Debe ser exactamente 'authorization_code'.",
        examples=["authorization_code"],
    )
    code: str = Field(
        min_length=1,
        max_length=256,
        description=(
            "Código de autorización opaco devuelto por ``/authorize``. Es de un solo uso y expira en 5 minutos."
        ),
        examples=["a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"],
    )
    code_verifier: str = Field(
        min_length=43,
        max_length=128,
        description=(
            "Secreto original generado por el cliente antes de calcular el challenge. "
            "El servidor recalcula SHA-256 y compara con el challenge almacenado."
        ),
        examples=["dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"],
    )


class TokenRefreshRequest(BaseModel):
    """Payload para renovar un par de tokens usando el refresh token activo."""

    model_config = ConfigDict(extra="forbid")

    grant_type: RefreshGrantType = Field(
        description="Debe ser exactamente 'refresh_token'.",
        examples=["refresh_token"],
    )
    refresh_token: str = Field(
        min_length=1,
        description=(
            "JWT de tipo refresh emitido previamente por ``/token`` o ``/refresh``. "
            "Cada refresh token es de un solo uso; el servidor emite un par nuevo "
            "y revoca el token consumido. Si se detecta reutilización, toda la "
            "familia de tokens queda revocada (Token Rotation)."
        ),
        examples=[
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ1c3ItMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1AiLCJqdGkiOiJydGktMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1EiLCJ0eXAiOiJyZWZyZXNoIn0."
            "SIGNATURE"
        ],
    )


class LogoutRequest(BaseModel):
    """Payload para cerrar la sesión activa del usuario autenticado.

    El header ``Authorization: Bearer <access_token>`` es obligatorio.
    El ``refresh_token`` es opcional pero recomendado para revocar ambos tokens
    simultáneamente y garantizar cierre de sesión completo.
    """

    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(
        default=None,
        description=(
            "JWT de tipo refresh a revocar junto con el access token. "
            "Si se omite, solo se revoca el access token del header."
        ),
        examples=[
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ1c3ItMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1AiLCJqdGkiOiJydGktMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1EiLCJ0eXAiOiJyZWZyZXNoIn0."
            "SIGNATURE"
        ],
    )


# Responses


class AuthorizationCodeResponse(BaseModel):
    """Resultado exitoso de ``POST /authorize``.

    El ``authorization_code`` debe intercambiarse por tokens en ``/token``
    antes de que expire ``expires_in`` segundos.
    """

    authorization_code: str = Field(
        description=(
            "Código de autorización opaco de un solo uso. "
            "Válido únicamente para el ``code_verifier`` generado en la misma sesión."
        ),
        examples=["a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"],
    )
    expires_in: int = Field(
        ge=1,
        le=600,
        description="Segundos que quedan hasta que el código expire. Máximo 600 (10 min).",
        examples=[300],
    )


class TokenView(BaseModel):
    """Representación serializable de un token JWT emitido."""

    token: str = Field(
        description=(
            "Token JWT firmado con RS256. Incluye claims estándar (sub, iat, exp, jti) "
            "más claims propietarios de KOSMO (typ, scopes, family_id para refresh)."
        ),
        examples=[
            "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJ1c3ItMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1AiLCJqdGkiOiJhdGktMDFIWFlaQVpCQ0RFRkdISUpLTE1OT1EiLCJ0eXAiOiJhY2Nlc3MiLCJzY29wZXMiOlsicHJvZmlsZTpyZWFkIl0sImlhdCI6MTc0NjE0MDAwMCwiZXhwIjoxNzQ2MTQwOTAwfQ."
            "SIGNATURE"
        ],
    )
    jti: str = Field(
        description=(
            "JWT ID — identificador único del token (UUID v4). "
            "Se usa como clave en Redis para la lista de revocación; "
            "permite invalidar un token individual sin rotar las claves RSA."
        ),
        examples=["ati-01HXYAZABCDEFGHIJKLMNOP"],
    )
    expires_at: datetime = Field(
        description=(
            "Timestamp ISO-8601 (UTC) en que el token expira. "
            "El access token tiene TTL de 15 min; el refresh token, 7 días."
        ),
        examples=["2025-12-31T23:59:59Z"],
    )


class TokenPairResponse(BaseModel):
    """Par de tokens emitido tras autenticación exitosa o renovación.

    El ``access`` token se adjunta en el header ``Authorization: Bearer``
    en cada petición autenticada. El ``refresh`` token se usa exclusivamente
    en ``POST /refresh`` para renovar la sesión.
    """

    access: TokenView = Field(description="Token de acceso de corta vida (TTL: 15 minutos). Uso: Authorization header.")
    refresh: TokenView = Field(
        description=(
            "Token de renovación de larga vida (TTL: 7 días). "
            "Almacenar en almacenamiento seguro (HttpOnly cookie o Secure storage)."
        )
    )
    token_type: Literal["Bearer"] = Field(
        default="Bearer",
        description="Esquema de autenticación. Siempre 'Bearer' según RFC 6750.",
        examples=["Bearer"],
    )

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokenPairResponse":
        return cls(
            access=TokenView(
                token=pair.access.token,
                jti=pair.access.jti,
                expires_at=pair.access.expires_at,
            ),
            refresh=TokenView(
                token=pair.refresh.token,
                jti=pair.refresh.jti,
                expires_at=pair.refresh.expires_at,
            ),
        )


class PrincipalView(BaseModel):
    """Identidad y perfil del usuario autenticado extraída del access token y persistencia."""

    subject: str = Field(
        description=(
            "Identificador opaco del usuario propietario del token. "
            "Corresponde al claim ``sub`` del JWT y al ``id`` en ``UserPublic``. "
            "Formato: prefijo de recurso + ULID (ej: ``usr-01HXYAZABCDEFGHIJKLMNOP``)."
        ),
        examples=["usr-01HXYAZABCDEFGHIJKLMNOP"],
    )
    name: str | None = Field(
        default=None,
        description="Nombre completo del usuario.",
        examples=["Gianfranco"],
    )
    email: str | None = Field(
        default=None,
        description="Correo electrónico del usuario.",
        examples=["usuario@ejemplo.com"],
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL de la foto de perfil o avatar del usuario.",
        examples=["https://avatars.githubusercontent.com/u/123456?v=4"],
    )
    scopes: list[str] = Field(
        description=(
            "Permisos concedidos en esta sesión, ordenados alfabéticamente. "
            f"Valores posibles: {', '.join(KNOWN_SCOPES)}."
        ),
        examples=[["agent:run", "profile:read"]],
    )


class RegisterResponse(BaseModel):
    """Confirmación genérica de registro para mitigar enumeración de usuarios (CWE-204)."""

    email: EmailStr = Field(
        description="Correo electrónico asociado a la solicitud de registro.",
        examples=["usuario@ejemplo.com"],
    )
    message: str = Field(
        default="Si el correo no estaba registrado previamente, la cuenta ha sido creada exitosamente.",
        description="Mensaje genérico de confirmación.",
        examples=["Si el correo no estaba registrado previamente, la cuenta ha sido creada exitosamente."],
    )


class UserPublic(BaseModel):
    """Datos públicos del usuario recién registrado. No incluye información sensible."""

    id: str = Field(
        description=(
            "Identificador único del usuario en el sistema. "
            "Formato: 'usr-' + ULID de 26 chars. Inmutable tras la creación."
        ),
        examples=["usr-01HXYAZABCDEFGHIJKLMNOP"],
    )
    name: str = Field(
        description="Nombre completo del usuario.",
        examples=["Gianfranco"],
    )
    email: EmailStr = Field(
        description="Dirección de correo verificada y normalizada del usuario.",
        examples=["usuario@ejemplo.com"],
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL del avatar del usuario.",
        examples=["https://avatars.githubusercontent.com/u/123456?v=4"],
    )
    created_at: datetime = Field(
        description="Timestamp ISO-8601 (UTC) de creación de la cuenta.",
        examples=["2025-01-15T10:30:00Z"],
    )


class OAuthErrorResponse(BaseModel):
    """Respuesta de error compatible con RFC 6749.

    Todos los endpoints de autenticación devuelven este esquema cuando
    falla la operación, permitiendo al cliente manejar errores de forma
    estructurada y consistente.
    """

    error: str = Field(
        description=(
            "Código de error máquina-legible según OAuth 2.0 RFC 6749. "
            "Valores comunes: ``invalid_grant``, ``invalid_token``, "
            "``account_locked``, ``email_already_registered``."
        ),
        examples=["invalid_grant"],
    )
    error_description: str = Field(
        description="Descripción legible por humanos del error, útil para logging y debugging.",
        examples=["Credenciales inválidas"],
    )
    seconds_remaining: int | None = Field(
        default=None,
        description=(
            "Segundos restantes de bloqueo en caso de error account_locked o rate limit. "
            "Permite al cliente sincronizar cuentas regresivas con la fuente de verdad del servidor."
        ),
        examples=[300],
    )


class CreateProjectRequest(BaseModel):
    """Payload para crear un nuevo proyecto en KOSMO."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=200,
        description="Nombre del proyecto.",
        examples=["Mi Proyecto"],
    )
    description: str = Field(
        default="",
        min_length=0,
        max_length=2000,
        description="Descripción del proyecto.",
        examples=["Proyecto de ejemplo para KOSMO"],
    )


class ProjectResponse(BaseModel):
    """Representación pública de un proyecto."""

    id: str = Field(
        description="Identificador único del proyecto.",
        examples=["prj_abc123def456"],
    )
    name: str = Field(
        description="Nombre del proyecto.",
        examples=["Mi Proyecto"],
    )
    slug: str = Field(
        description="Slug único del proyecto generado a partir del nombre.",
        examples=["mi-proyecto"],
    )
    description: str = Field(
        description="Descripción del proyecto.",
        examples=["Proyecto de ejemplo para KOSMO"],
    )
    owner_id: str = Field(
        description="Identificador del usuario propietario.",
        examples=["usr_abc123"],
    )
    created_at: datetime = Field(
        description="Timestamp ISO-8601 (UTC) de creación del proyecto.",
        examples=["2026-06-16T10:00:00Z"],
    )
    updated_at: datetime = Field(
        description="Timestamp ISO-8601 (UTC) de última modificación.",
        examples=["2026-06-16T10:00:00Z"],
    )


class HttpErrorResponse(BaseModel):
    """Respuesta de error HTTP genérica para errores de infraestructura (4xx/5xx).

    Se emite cuando el error no está dentro del flujo OAuth (ej: error interno
    del servidor, acceso prohibido a un recurso).
    """

    detail: str = Field(
        description="Mensaje descriptivo del error de infraestructura.",
        examples=["Error interno del servidor. Por favor contacte al soporte."],
    )


class DiscoveryResponse(BaseModel):
    """Documento de descubrimiento de un proyecto.

    Coincide con la interfaz DiscoveryResponse del frontend.
    """

    id: str = Field(
        description="Identificador del documento de descubrimiento.",
        examples=["doc_prj_abc123def456"],
    )
    project_id: str = Field(
        description="Identificador del proyecto al que pertenece el documento.",
        examples=["prj_abc123def456"],
    )
    content: str = Field(
        description="Contenido del documento en formato Markdown.",
        examples=["## Visión\n..."],
    )


class RefineDiscoveryRequest(BaseModel):
    """Payload para refinar el documento de descubrimiento mediante IA."""

    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Instrucciones de refinamiento que el agente de IA debe aplicar "
            "sobre el documento de descubrimiento actual."
        ),
        examples=["Haz que la visión del producto sea más concisa y enfocada en los resultados."],
    )


class FeatureResponse(BaseModel):
    """Característica del producto software."""

    id: str = Field(
        description="Identificador único de la característica.",
        examples=["feat_abc123"],
    )
    project_id: str = Field(
        description="Identificador del proyecto al que pertenece.",
        examples=["prj_abc123def456"],
    )
    number: int = Field(
        description="Número secuencial de la característica.",
        examples=[1],
    )
    title: str = Field(
        description="Título de la característica.",
        examples=["Gestión de catálogo de productos"],
    )
    slug: str = Field(
        description="Slug de la característica generado a partir del título.",
        examples=["gestion-de-catalogo-de-productos"],
    )
    description: str = Field(
        description="Descripción detallada de la característica.",
        examples=["Permite a los usuarios administrar el catálogo..."],
    )
    origin: str = Field(
        description="Justificación de existencia y trazabilidad a secciones del descubrimiento.",
        examples=["Se deriva de la meta Gestión financiera. Se traza a Metas del producto."],
    )
    display_id: str = Field(
        description="Identificador visible para el usuario (ej: C01).",
        examples=["C01"],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advertencias sobre solapamientos funcionales o inconsistencias menores.",
    )


class FeatureSuggestionItem(BaseModel):
    """Una sugerencia individual de característica."""

    title: str
    description: str
    origin: str = ""


class SaveSelectedFeaturesRequest(BaseModel):
    """Payload para guardar características seleccionadas."""

    features: list[FeatureSuggestionItem] = Field(description="Lista de características a guardar.")


class FeatureSuggestionResponse(BaseModel):
    """Respuesta con una sugerencia de característica."""

    number: int = Field(description="Número sugerido para la característica.")
    title: str = Field(description="Título sugerido.")
    description: str = Field(description="Descripción sugerida.")
    origin: str = Field(description="Justificación y trazabilidad de la característica.")


class CreateCharacteristicRequest(BaseModel):
    """Payload para crear una característica de forma manual."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=50,
        description="Título de la característica (máximo 50 caracteres).",
        examples=["Gestión de catálogo de productos"],
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Descripción de la característica (máximo 500 caracteres).",
        examples=["Permite a los usuarios administrar el catálogo de productos del sistema."],
    )
    origin: str = Field(
        default="",
        description="Origen y trazabilidad de la característica. Si se deja vacío, la IA lo deriva del descubrimiento.",
    )


class EditFeatureManualRequest(BaseModel):
    """Payload para editar una característica de forma manual."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=50,
        description="Nuevo título de la característica (máximo 50 caracteres).",
    )
    description: str = Field(
        min_length=0,
        max_length=500,
        description="Nueva descripción de la característica (máximo 500 caracteres).",
    )


class ChangeSuggestion(BaseModel):
    """Sugerencia de cambio generada por la IA."""

    id: str = Field(description="ID de la sugerencia (chg_ + ULID)")
    section: str = Field(description="Sección del documento afectada")
    description: str = Field(description="Descripción corta del cambio propuesto")
    diff_before: str = Field(description="Contenido actual de la sección")
    diff_after: str = Field(description="Contenido sugerido por la IA")
    rationale: str | None = Field(default=None, description="Justificación del cambio propuesto")
    applied: bool = Field(default=True, description="True si el servidor aplicó el cambio al instante")
    not_applied_reason: str | None = Field(
        default=None, description="Razón por la que el cambio no se pudo aplicar (solo si applied=false)"
    )


class SendChatRequest(BaseModel):
    """Payload para enviar un mensaje al chat."""

    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000, description="Mensaje del usuario")
    session_id: str | None = Field(
        default=None,
        description="Hilo de conversación (cht_). Si es null, se usa el contexto actual de la fase.",
    )


class ModificationResultView(BaseModel):
    """Resultado de la modificacion aplicada por el chat (aplicacion instantanea)."""

    applied: bool = Field(description="True si la modificación fue aplicada al documento")
    modified_section: str | None = Field(default=None, description="Nombre de la sección o atributo modificado")
    change_description: str | None = Field(default=None, description="Descripción breve del cambio aplicado")
    modified_document: str | None = Field(
        default=None,
        description="Markdown completo actualizado. En el chat de Características contiene el nuevo título.",
    )
    before: str | None = Field(default=None, description="Contenido previo de la sección o atributo modificado")
    after: str | None = Field(default=None, description="Contenido posterior de la sección o atributo modificado")
    undo_version_id: str | None = Field(
        default=None, description="Versión previa al cambio (reservado para el endpoint de undo)"
    )
    clarification_message: str | None = Field(
        default=None, description="Mensaje solicitando detalle cuando la instrucción es ambigua (applied=false)"
    )


class RedirectInfoView(BaseModel):
    """Redirección cuando el cambio pertenece a otra fase (fuente de verdad a la izquierda)."""

    target_phase: str = Field(description="Fase destino del cambio")
    redirect_message: str = Field(description="Explicación de por qué el cambio pertenece a esa fase")


class ChatMessage(BaseModel):
    """Respuesta con un mensaje individual del chat."""

    id: str = Field(description="ID del mensaje.")
    role: str = Field(description="Rol del emisor (user, assistant, system).")
    content: str = Field(description="Contenido del mensaje.")
    created_at: datetime = Field(description="Fecha y hora del mensaje.")
    change_suggestions: list[ChangeSuggestion] | None = Field(
        default=None, description="Sugerencias de cambio asociadas"
    )
    modification: ModificationResultView | None = Field(
        default=None, description="Modificación aplicada (solo mensajes del asistente)"
    )

    @classmethod
    def from_domain(cls, msg: MensajeChat) -> "ChatMessage":
        suggestions = None
        if msg.suggested_changes:
            suggestions = [
                ChangeSuggestion(
                    id=sc.id,
                    section=sc.section,
                    description=sc.description,
                    diff_before=sc.diff.before,
                    diff_after=sc.diff.after,
                    rationale=sc.rationale,
                    applied=sc.applied,
                    not_applied_reason=sc.not_applied_reason,
                )
                for sc in msg.suggested_changes
            ]
        modification = None
        if msg.modification is not None:
            modification = ModificationResultView(
                applied=msg.modification.applied,
                modified_section=msg.modification.modified_section,
                change_description=msg.modification.change_description,
                modified_document=msg.modification.modified_document,
                before=msg.modification.before,
                after=msg.modification.after,
                clarification_message=msg.modification.clarification_message,
            )
        return cls(
            id=str(msg.id),
            role=str(msg.role),
            content=msg.content,
            created_at=msg.timestamp,
            change_suggestions=suggestions,
            modification=modification,
        )


class ChatResponse(BaseModel):
    """Respuesta del chat con modificación aplicada, consistencia o redirección."""

    message: ChatMessage = Field(description="Mensaje del asistente")
    modification: ModificationResultView | None = Field(
        default=None, description="Presente si el chat aplicó un cambio al documento"
    )
    redirect: RedirectInfoView | None = Field(default=None, description="Presente si el cambio pertenece a otra fase")
    consistency: list[dict[str, object]] | None = Field(
        default=None,
        description="Impactos de consistencia en las fases a la derecha (solo si se aplicó un cambio)",
    )

    @classmethod
    def from_message(cls, output: Any) -> "ChatResponse":
        message = ChatMessage.from_domain(output.message)
        return cls(
            message=message,
            modification=message.modification,
            consistency=None,
            redirect=None,
        )

    @classmethod
    def from_redirect(cls, target_phase: str, redirect_message: str) -> "ChatResponse":
        from kosmo.contracts.ai.chat import ChatRole
        from kosmo.contracts.sdd.ids import ChatMessageId
        from kosmo.domain.sdd.id_generator import IdGenerator

        redirect_msg = MensajeChat(
            id=ChatMessageId(IdGenerator.generate("chat_message")),
            role=ChatRole.ASSISTANT,
            content=redirect_message,
        )
        return cls(
            message=ChatMessage.from_domain(redirect_msg),
            redirect=RedirectInfoView(
                target_phase=target_phase,
                redirect_message=redirect_message,
            ),
        )


class ChatHistoryResponse(BaseModel):
    """Respuesta con el historial paginado de un chat."""

    phase: str = Field(description="Fase a la que pertenece el historial")
    context: str = Field(description="Contexto específico (ej. project_id)")
    messages: list[ChatMessage] = Field(description="Lista de mensajes.")
    has_more: bool = Field(default=False, description="Indica si hay más mensajes anteriores")
    next_cursor: str | None = Field(default=None, description="Cursor para la siguiente página (ISO-8601)")

    @classmethod
    def from_domain(cls, history: HistorialChat) -> "ChatHistoryResponse":
        return cls(
            phase=str(history.phase.value if hasattr(history.phase, "value") else history.phase),
            context=str(history.project_id),
            messages=[ChatMessage.from_domain(msg) for msg in history.messages],
            has_more=history.has_more,
            next_cursor=history.next_cursor,
        )


class ContextRedirectResponse(BaseModel):
    """Redirección cuando el mensaje no corresponde al ámbito de la fase actual."""

    message: str = Field(description="Mensaje indicando la fase correcta")
    target_phase: str = Field(description="Fase destino: discovery, features, requirements")


# ═══ Verificación de consistencia en guardado manual (Sprint 4 - HU18/T7) ═══


class CheckConsistencyRequestView(BaseModel):
    """Payload para verificar consistencia antes de guardado manual de feature."""

    model_config = ConfigDict(extra="forbid")
    content: dict[str, object] = Field(description="Contenido nuevo a validar contra el documento fuente")


class InconsistencyResultView(BaseModel):
    """Resultado de verificación de consistencia en guardado manual."""

    is_consistent: bool = Field(description="False si se detectó contradicción flagrante")
    reason: str | None = Field(default=None, description="Motivo de la inconsistencia (solo si is_consistent = false)")
    conflicting_section: str | None = Field(
        default=None, description="Sección del documento fuente con la que hay conflicto"
    )


# ═══ Consistencia (Sprint 4 - HU17) ═══


class ChangeInputView(BaseModel):
    """Cambio individual dentro de la solicitud de evaluacion de consistencia."""

    section: str = Field(description="Sección del documento afectada")
    diff_before: str = Field(description="Contenido antes del cambio")
    diff_after: str = Field(description="Contenido después del cambio")
    description: str = Field(default="", description="Descripción semántica del cambio")


class EvaluateConsistencyRequestView(BaseModel):
    """Payload para solicitar analisis de consistencia entre fases."""

    model_config = ConfigDict(extra="forbid")
    phase_origin: str = Field(description="Fase de origen de los cambios")
    phase_destination: str | None = Field(
        default=None, description="Fase destino a evaluar (opcional, si se omite evalúa todas las adyacentes)"
    )
    changes: list[ChangeInputView] = Field(description="Cambios a evaluar para consistencia")


class ImpactItemView(BaseModel):
    """Artefacto afectado por propagación de cambios."""

    phase: str = Field(description="Fase del artefacto afectado")
    artifact_id: str = Field(description="ID del artefacto afectado")
    artifact_type: str = Field(description="Tipo de artefacto")
    artifact_label: str = Field(description="Etiqueta visible del artefacto")
    section: str = Field(default="", description="Sección o atributo afectado")
    rationale: str = Field(default="", description="Justificación de por qué está desactualizado")
    diff_suggestion: dict[str, object] | None = Field(
        default=None, description="Diff sugerido para actualizar el artefacto"
    )


class ConsistencyReportView(BaseModel):
    """Reporte de analisis de consistencia entre fases."""

    id: str = Field(description="ID del reporte (cnr_ + ULID)")
    phase_origin: str = Field(description="Fase donde se originaron los cambios")
    own_changes: list[ChangeInputView] = Field(  # type: ignore[reportUnknownVariableType]
        default_factory=list, description="Cambios propios evaluados"
    )
    upstream_impact: list[ImpactItemView] | None = Field(default=None, description="Impacto en fases anteriores")
    downstream_impact: list[ImpactItemView] | None = Field(default=None, description="Impacto en fases posteriores")
    created_at: str = Field(description="Timestamp ISO-8601 UTC")


# ═══ Modificación directa de documentos vía chat (Sprint 5 - HU-20) ═══


class DocumentModifyRequestView(BaseModel):
    """Payload para solicitar la modificación directa de un documento vía chat sin plan."""

    model_config = ConfigDict(extra="forbid")
    document_type: Literal["discovery", "features", "requirements", "model"] = Field(
        description="Tipo de documento a modificar"
    )
    document_id: str = Field(description="ID del documento o característica a modificar")
    instruction: str = Field(
        min_length=1,
        max_length=2000,
        description="Instrucción textual del cambio deseado",
    )


class DocumentModifyResponseView(BaseModel):
    """Respuesta con el resultado de una modificación directa de documento."""

    document_id: str = Field(description="ID del documento modificado")
    content: str = Field(description="Contenido completo del documento actualizado")
    highlighted_section: str | None = Field(
        default=None,
        description="Nombre de la sección modificada, para resaltar en la UI",
    )
    message: str = Field(description="Mensaje de confirmación para el usuario")


class TraceabilityNavigationOutputView(BaseModel):
    """Respuesta de navegación con guardas de trazabilidad."""

    permitted: bool = Field(description="Indica si la edición está permitida en este nivel.")
    redirect_message: str | None = Field(
        default=None, description="Mensaje para mostrar al usuario si no está permitido."
    )
    source_entity_name: str | None = Field(default=None, description="Nombre de la entidad de origen.")
    source_entity_id: str | None = Field(default=None, description="ID de la entidad de origen.")
    source_level: str | None = Field(default=None, description="Fase de la entidad de origen (ej. caracteristicas).")


class GenerateImplementationRequest(BaseModel):
    """Petición para iniciar la generación asíncrona de implementación."""

    feature_id: str = Field(description="ID de la característica a implementar")
    max_retries: int = Field(default=3, ge=1, le=5)


class GenerateImplementationResponse(BaseModel):
    """Respuesta tras iniciar la generación asíncrona."""

    implementation_id: str = Field(description="ID del proceso iniciado para consumir sus eventos")


class ImplementationFileContentResponse(BaseModel):
    """Contenido de un archivo generado en el workspace."""

    path: str = Field(description="Ruta relativa del archivo solicitado")
    content: str = Field(description="Contenido del archivo en texto plano")


class ImplementationRecordResponse(BaseModel):
    """Registro persistido de una implementación (fuente de verdad para el frontend)."""

    implementation_id: str = Field(description="ID de la implementación")
    feature_id: str = Field(description="ID de la característica implementada")
    project_id: str = Field(description="ID del proyecto al que pertenece la característica")
    status: str = Field(description="Estado actual de la implementación")
    generated_files: list[str] = Field(default_factory=list, description="Archivos generados")
    features_count: int = Field(default=1, description="Cantidad de características implementadas")
    screens_count: int = Field(default=0, description="Cantidad de pantallas y componentes generados")
    requirements_count: int = Field(default=0, description="Cantidad de requisitos de negocio cubiertos")
    validations_passed: int = Field(default=0, description="Pasos de validación exitosos")
    validations_total: int = Field(default=0, description="Total de pasos de validación")
    traceability_edges_count: int = Field(default=0, description="Total de aristas de trazabilidad registradas")
    technologies: list[str] = Field(default_factory=list, description="Tecnologías principales del proyecto")
    updated_at: datetime = Field(description="Última actualización del registro")


class ValidationStepResultResponse(BaseModel):
    """Resultado de un paso individual del pipeline de validación."""

    step: str = Field(description="Nombre del paso ejecutado (typecheck, lint, tests, build)")
    success: bool = Field(description="Si el paso terminó sin errores")
    duration_ms: int = Field(default=0, description="Duración del paso en milisegundos")
    exit_code: int = Field(default=0, description="Código de salida del proceso")
    error_messages: list[str] = Field(default_factory=list, description="Mensajes de error del paso")


class ValidateWorkspaceResponse(BaseModel):
    """Resultado del pipeline de validación de un workspace."""

    all_passed: bool = Field(description="Si todos los pasos pasaron")
    steps: list[ValidationStepResultResponse] = Field(
        default_factory=list[ValidationStepResultResponse], description="Resultado por paso"
    )
    failed_step: str | None = Field(default=None, description="Primer paso que falló, si hubo")
    error_summary: list[str] = Field(default_factory=list, description="Resumen de errores")
    total_duration_ms: int = Field(default=0, description="Duración total en milisegundos")


class AIModelInfoResponse(BaseModel):
    id: str
    display_name: str
    tier: str


class AIProviderInfoResponse(BaseModel):
    value: str
    label: str
    models: list[AIModelInfoResponse]


class AIConfigResponse(BaseModel):
    provider: str
    model: str
    is_custom: bool
    has_api_key: bool
    masked_key: str | None = None
    updated_at: datetime | None = None


class SaveAIConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: str


class TestAIConnectionRequest(BaseModel):
    provider: str
    model: str
    api_key: str | None = None


class TestAIConnectionResponse(BaseModel):
    is_connected: bool
    detected_model: str
    message: str


# ── Integrations & GitHub Sync (HU-23) ──


class ConnectOAuthRequest(BaseModel):
    """Payload para intercambiar el código temporal de OAuth por credenciales de acceso."""

    code: str = Field(min_length=1, max_length=500, description="Código de autorización temporal devuelto por OAuth")
    redirect_uri: str | None = Field(default=None, description="URI de redirección utilizada")
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128)


class IntegrationStatusResponse(BaseModel):
    """Estado de vinculación de una plataforma externa con la cuenta de usuario."""

    provider: str = Field(description="Identificador del proveedor (github | railway)")
    is_connected: bool = Field(description="True si la cuenta de usuario se encuentra vinculada")
    username: str | None = Field(default=None, description="Nombre de usuario en la plataforma externa")
    connected_at: datetime | None = Field(default=None, description="Marca de tiempo ISO-8601 UTC de la vinculación")


class ProjectGitHubResponse(BaseModel):
    """Metadatos de vinculación y sincronización con GitHub para un proyecto."""

    has_repository: bool = Field(description="True si el proyecto ya cuenta con repositorio en GitHub")
    repo_name: str | None = Field(default=None, description="Nombre del repositorio remoto en GitHub")
    repo_url: str | None = Field(default=None, description="URL pública o accesible del repositorio en GitHub")
    is_public: bool | None = Field(default=None, description="Visibilidad del repositorio (True=público)")
    last_push_at: datetime | None = Field(default=None, description="Marca de tiempo UTC del último envío exitoso")
    last_commit_hash: str | None = Field(default=None, description="Hash SHA-1 del último commit sincronizado")
    sync_status: str = Field(description="Estado del ciclo de vida y sincronización del repositorio")
    suggested_repo_name: str | None = Field(default=None, description="Nombre de repositorio sugerido normalizado")
    error_message: str | None = Field(default=None, description="Detalle del error en caso de fallo en sincronización")


class PushGitHubRequest(BaseModel):
    """Payload para solicitar la creación de repositorio o push incremental de código."""

    repo_name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Nombre deseado para el repositorio"
    )
    is_public: bool = Field(
        default=True, description="Visibilidad del repositorio (siempre público; no se permiten repositorios privados)"
    )
    commit_message: str | None = Field(
        default=None, max_length=300, description="Mensaje descriptivo para el commit de sincronización"
    )

    @field_validator("is_public")
    @classmethod
    def validate_is_public(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "No se permiten repositorios privados. Todos los repositorios de GitHub deben ser públicos."
            )
        return v


# ── Cloud Deployment (HU-24) ──


class DeployStatusEnum(StrEnum):
    """Estado del ciclo de vida del despliegue en la plataforma en la nube."""

    idle = "idle"
    pending = "pending"
    building = "building"
    ready = "ready"
    failed = "failed"


class ProjectDeployStatusResponse(BaseModel):
    """Metadatos y estado actual de la publicación del proyecto en la nube."""

    service_id: str | None = Field(default=None, description="Identificador único del servicio en Railway")
    service_name: str | None = Field(default=None, description="Nombre del servicio desplegado en la plataforma")
    deploy_url: str | None = Field(default=None, description="URL pública accesible en internet generada por Railway")
    status: str = Field(description="Estado del ciclo de vida del despliegue en la plataforma en la nube")
    last_deploy_at: datetime | None = Field(
        default=None, description="Marca de tiempo ISO-8601 UTC del último despliegue disparado"
    )
    error_message: str | None = Field(
        default=None, description="Mensaje de error si la construcción o arranque del servicio fallaron"
    )
    error_log_url: str | None = Field(
        default=None, description="Enlace directo hacia la consola de registros de compilación en Railway"
    )


class DeployRailwayRequest(BaseModel):
    """Parámetros opcionales para configurar o personalizar el despliegue en Railway."""

    service_name: str | None = Field(
        default=None, max_length=100, description="Nombre personalizado para el servicio en Railway"
    )
    environment_variables: dict[str, str] | None = Field(
        default=None, description="Variables de entorno adicionales a configurar en el servicio"
    )
