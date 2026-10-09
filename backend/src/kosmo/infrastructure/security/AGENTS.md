# `infrastructure/security/` — Criptografía, Tokens JWT y Hashing de Contraseñas

## Responsabilidad y Propósito

Este módulo implementa los primitivos criptográficos y de seguridad del backend de KOSMO. Sus responsabilidades incluyen:
- **Cifrado y descifrado simétrico autenticado** de credenciales sensibles en reposo (API keys BYOK de usuarios, tokens de acceso/refresh de GitHub y Railway) mediante Fernet (AES-128-CBC + HMAC-SHA256).
- **Emisión y verificación asimétrica de tokens JWT** bajo el estándar RS256 con claves RSA PEM, validación estricta de claims (`iss`, `aud`, `exp`, `jti`, `fam`), y segregación de tipos (`access` y `refresh`).
- **Hashing y verificación de contraseñas de usuario** mediante Argon2id conforme a las directrices OWASP 2025, con detección automática de rehash (`needs_rehash`).

**Principio de diseño:** Todas las clases de este módulo implementan puertos abstractos definidos en `contracts/auth/` (`SecretCipher`, `TokenIssuer`, `TokenVerifier`, `PasswordHasher`). Ningún caso de uso depende directamente de las implementaciones concretas de este directorio.

---

## Estructura de Archivos y Componentes

```
infrastructure/security/
├── __init__.py          # Exporta FernetSecretCipher, JoseJwtIssuer, JoseJwtVerifier, JwtSettings, Argon2id*
├── fernet_vault.py      # Adaptador Fernet para cifrado/descifrado simétrico en reposo
├── jwt_codec.py         # Emisor y verificador de JWTs RS256 con dataclass JwtSettings
└── password_hasher.py   # Adaptador Argon2id con dataclass Argon2idParameters
```

---

## Descripción Detallada por Archivo

### 1. `fernet_vault.py` — Cifrado Simétrico Autenticado (Fernet)

Implementa el puerto `SecretCipher` de `kosmo.contracts.auth.secrets`.

#### Clase `FernetSecretCipher`:
- **Construcción (`__init__`)**:
  - Acepta `master_key` como `str`, `bytes` o `SecretStr` de Pydantic.
  - Valida que la clave no esté vacía; si lo está, lanza `ValueError("La clave maestra Fernet no puede estar vacía.")`.
  - Intenta instanciar `cryptography.fernet.Fernet`. Si la clave no es una cadena Base64 URL-safe de exactamente 32 bytes, lanza `ValueError("La clave maestra Fernet es inválida. Debe ser de 32 bytes codificados en base64 url-safe.") from exc`.
  - **Mecanismo de seguridad:** Fernet proporciona cifrado autenticado simétrico (AES-128 en modo CBC con PKCS7 padding y autenticación HMAC-SHA256). Cada llamada a `encrypt` genera 16 bytes de IV aleatorio y un timestamp de 8 bytes, por lo que dos cifrados del mismo texto plano producen textos cifrados distintos, protegiendo contra análisis de frecuencia.

- **Métodos principales**:
  - **`generate_master_key() -> str`** *(classmethod)*:
    - Genera una clave maestra segura de 32 bytes en base64 url-safe usando `Fernet.generate_key()`.
  - **`encrypt(plaintext: bytes) -> EncryptedSecret`**:
    - Cifra bytes crudos y retorna un value object inmutable `EncryptedSecret(ciphertext=bytes)`.
  - **`decrypt(secret: EncryptedSecret) -> bytes`**:
    - Descifra el ciphertext verificando la integridad del HMAC.
    - Captura `cryptography.fernet.InvalidToken` y lo transforma en `kosmo.contracts.auth.InvalidTokenError("Cifrado inválido o expirado")`.
  - **`encrypt_string(plaintext: str) -> EncryptedSecret`**:
    - Helper que codifica a UTF-8 y llama a `encrypt()`. Usado para API keys BYOK y OAuth tokens.
  - **`decrypt_string(secret: EncryptedSecret | bytes | str) -> str`**:
    - Helper polimórfico: acepta `EncryptedSecret`, `str` o `bytes`, descifra y decodifica a string UTF-8.
  - **`to_storage_str(secret: EncryptedSecret) -> str`** *(staticmethod)*:
    - Convierte el ciphertext binario a string UTF-8 para persistencia en columnas de base de datos (`String` o `Text`).
  - **`from_storage_str(stored: str) -> EncryptedSecret`** *(staticmethod)*:
    - Reconstruye un `EncryptedSecret` eliminando espacios en blanco y re-codificando a bytes.

---

### 2. `jwt_codec.py` — Tokens JWT Asimétricos (RS256)

Implementa los puertos `TokenIssuer` y `TokenVerifier` de `kosmo.contracts.auth.ports`.

#### Dataclass `JwtSettings` (`frozen=True, slots=True`):
Configuración inmutable consumida por el emisor y verificador:
- `algorithm: str` (por defecto `"RS256"`).
- `issuer: str` (por defecto `"kosmo"`).
- `audience: str` (por defecto `"kosmo-api"`).
- `access_ttl_seconds: int` (por defecto `900` segundos = 15 minutos).
- `refresh_ttl_seconds: int` (por defecto `604800` segundos = 7 días).

#### Función `_ttl_for(token_type: TokenType, settings: JwtSettings) -> int`:
Determina la vigencia del token: `access_ttl_seconds` si `token_type == TokenType.ACCESS`, o `refresh_ttl_seconds` en caso contrario.

#### Clase `JoseJwtIssuer`:
- **Construcción**: `__init__(*, private_key_pem: str, settings: JwtSettings)`
- **Método `issue(...) -> IssuedToken`**:
  - Parámetros: `subject: str`, `scopes: frozenset[str]`, `token_type: TokenType`, `family_id: str | None = None`.
  - Genera un identificador único de token `jti = ULID().hex` (32 caracteres hexadecimales, garantizando unicidad cronológicamente ordenable sin coordinación).
  - Estructura del Payload (Claims):
    - `sub`: Identificador del usuario (`user_id`).
    - `iss`: Issuer configurado (`"kosmo"`).
    - `aud`: Audiencia configurada (`"kosmo-api"`).
    - `iat`: Timestamp Unix de emisión (`now.timestamp()`).
    - `exp`: Timestamp Unix de expiración (`(now + ttl).timestamp()`).
    - `jti`: Identificador único ULID del token.
    - `type`: Valor string del enum (`"access"` o `"refresh"`).
    - `scopes`: Lista ordenada de permisos (`sorted(scopes)`).
    - `fam`: Identificador de familia de refresh tokens (si `family_id` no es None).
  - Firma el token con la clave privada RSA usando `jose.jwt.encode`.
  - Retorna `IssuedToken(token=str, jti=str, expires_at=datetime, token_type=TokenType, family_id=str | None)`.

#### Clase `JoseJwtVerifier`:
- **Construcción**: `__init__(*, public_key_pem: str, settings: JwtSettings)`
- **Método `verify(token: str, *, expected_type: TokenType) -> TokenClaims`**:
  - Decodifica y verifica la firma criptográfica usando la clave pública RSA:
    - Valida firma, algoritmo (`RS256`), emisor (`iss`) y audiencia (`aud`).
  - Mapeo estricto de excepciones de `python-jose`:
    - `jose.exceptions.ExpiredSignatureError` -> `kosmo.contracts.auth.TokenExpiredError("Token expired")`.
    - `jose.exceptions.JWTClaimsError` o `jose.exceptions.JWTError` -> `kosmo.contracts.auth.InvalidTokenError(str(exc))`.
  - **Validación de tipo de token:**
    - Verifica que `payload.get("type") == expected_type.value`.
    - Si no coincide (por ejemplo, si se intenta usar un refresh token para autenticar una petición a la API), lanza `InvalidTokenError("Unexpected token type...")`.
  - **Construcción de `TokenClaims`**:
    - Extrae `sub`, `jti`, `iat`, `exp`, `scopes` (convertido a `frozenset`), y `fam`.
    - Convierte timestamps a objetos `datetime` con timezone `UTC`.
    - Si el payload está corrupto (`KeyError`, `TypeError`, `ValueError`), lanza `InvalidTokenError(f"Malformed claims: {exc}")`.

---

### 3. `password_hasher.py` — Hashing de Contraseñas (Argon2id)

Implementa el puerto `PasswordHasher` de `kosmo.contracts.auth.ports`.

#### Dataclass `Argon2idParameters` (`frozen=True, slots=True`):
- `memory_kib: int`: Memoria requerida en KiB (OWASP 2025: `65536` KiB = 64 MB).
- `time_cost: int`: Número de iteraciones (OWASP 2025: `3`).
- `parallelism: int`: Número de hilos paralelos (OWASP 2025: `4`).

#### Clase `Argon2idPasswordHasher`:
- **Construcción**: `__init__(params: Argon2idParameters)`
  - Instancia `argon2.PasswordHasher` con:
    - `time_cost = params.time_cost`
    - `memory_cost = params.memory_kib`
    - `parallelism = params.parallelism`
    - `hash_len = 32` (longitud de salida de 32 bytes)
    - `salt_len = 16` (sal aleatoria de 16 bytes generada por el CSPRNG del sistema)
    - `type = argon2.Type.ID` (variante híbrida Argon2id: resistente a ataques de canal lateral por acceso a memoria y a computación paralela en GPU/ASIC).
- **Métodos**:
  - **`hash(plain: str) -> str`**:
    - Genera la cadena codificada estándar: `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`.
  - **`verify(hashed: str, plain: str) -> bool`**:
    - Verifica si la contraseña coincide con el hash almacenado.
    - Captura silenciosamente `VerifyMismatchError` y `InvalidHashError` retornando `False`.
    - **Seguridad:** No lanza excepciones internas ni filtra información sobre la validez del hash o la causa del fallo.
  - **`needs_rehash(hashed: str) -> bool`**:
    - Invoca `_hasher.check_needs_rehash(hashed)`.
    - Permite migración transparente de hashes: si en el futuro se incrementan los parámetros de seguridad en `Settings`, el sistema detecta en el próximo login exitoso que la contraseña debe ser re-hasheada con los nuevos costos sin requerir reinicio de credenciales por el usuario.

---

## Integración con el Sistema y Composición (`infrastructure/api/composition/root.py`)

En el Composition Root de KOSMO, los componentes de seguridad se inicializan como singletons dentro del contenedor `AppContainer`:

```python
# 1. Hasher de contraseñas
password_hasher = Argon2idPasswordHasher(
    Argon2idParameters(
        memory_kib=settings.argon2_memory_kib,
        time_cost=settings.argon2_time_cost,
        parallelism=settings.argon2_parallelism,
    )
)

# 2. Cifrador de secretos en reposo
secret_cipher = FernetSecretCipher(settings.fernet_master_key)

# 3. Configuración y códec JWT
jwt_settings = JwtSettings(
    algorithm=settings.jwt_algorithm,
    issuer=settings.jwt_issuer,
    audience=settings.jwt_audience,
    access_ttl_seconds=settings.jwt_access_ttl_seconds,
    refresh_ttl_seconds=settings.jwt_refresh_ttl_seconds,
)
token_issuer = JoseJwtIssuer(
    private_key_pem=settings.jwt_private_key_pem,
    settings=jwt_settings,
)
token_verifier = JoseJwtVerifier(
    public_key_pem=settings.jwt_public_key_pem,
    settings=jwt_settings,
)
```

### Consumidores Principales:
1. **`FernetSecretCipher`**:
   - `UserAiConfigRepository`: Cifra y descifra `encrypted_api_key` de proveedores LLM.
   - `UserIntegrationRepository`: Cifra y descifra `access_token_enc` y `refresh_token_enc` de GitHub y Railway.
   - `DynamicUserLLMClient`: Descifra la API key para instanciar el cliente HTTP en runtime.
   - `IsolatedOpenCodeClient`: Descifra credenciales para transmitirlas de forma segura al launcher de contenedores efímeros.
2. **`JoseJwtIssuer` / `JoseJwtVerifier`**:
   - Casos de uso de autenticación (`application/auth/`): Login, refresh token exchange, emisión de tokens PKCE OAuth2.
   - Dependencias de API (`infrastructure/api/dependencies/auth.py`): `get_principal` verifica el token en cada request.
3. **`Argon2idPasswordHasher`**:
   - Casos de uso de registro, login y cambio de contraseña en `application/auth/`.

---

## Constantes y Valores Clave

| Parámetro | Valor por Defecto | Origen / Estándar |
|:---|:---|:---|
| Algoritmo JWT | `RS256` | Clave asimétrica RSA PEM |
| Emisor JWT (`iss`) | `"kosmo"` | `Settings.jwt_issuer` |
| Audiencia JWT (`aud`) | `"kosmo-api"` | `Settings.jwt_audience` |
| Access Token TTL | `900s` (15 min) | `Settings.jwt_access_ttl_seconds` |
| Refresh Token TTL | `604800s` (7 días) | `Settings.jwt_refresh_ttl_seconds` |
| Formato JTI | ULID hexadecimal (32 chars) | `ULID().hex` |
| Memoria Argon2id | `65536 KiB` (64 MB) | OWASP 2025 / `Settings.argon2_memory_kib` |
| Tiempo Argon2id | `3` iteraciones | OWASP 2025 / `Settings.argon2_time_cost` |
| Paralelismo Argon2id | `4` hilos | OWASP 2025 / `Settings.argon2_parallelism` |
| Salida Hash Argon2id | `32` bytes | `hash_len=32` |
| Sal Argon2id | `16` bytes | `salt_len=16` |
| Algoritmo Fernet | AES-128-CBC + HMAC-SHA256 | RFC 9051 / Especificación Fernet |
| Longitud Clave Fernet | 32 bytes en base64 url-safe | `Fernet.generate_key()` |

---

## Contratos Implementados

| Puerto (en `contracts/auth/`) | Implementación Concreta | Archivo |
|:---|:---|:---|
| `SecretCipher` (`contracts/auth/secrets.py`) | `FernetSecretCipher` | `fernet_vault.py` |
| `TokenIssuer` (`contracts/auth/ports.py`) | `JoseJwtIssuer` | `jwt_codec.py` |
| `TokenVerifier` (`contracts/auth/ports.py`) | `JoseJwtVerifier` | `jwt_codec.py` |
| `PasswordHasher` (`contracts/auth/ports.py`) | `Argon2idPasswordHasher` | `password_hasher.py` |

---

## Reglas de Implementación y Mantenimiento

1. **Inmutabilidad de Parámetros Argon2id:** Nunca rebajar los parámetros de memoria (`64 MB`), tiempo (`3`) o paralelismo (`4`). Cumplen con el baseline de resistencia para GPUs en 2025/2026.
2. **Criptografía Asimétrica Obligatoria:** No utilizar algoritmos simétricos (como `HS256`) para JWTs. Las claves privadas residen exclusivamente en el servidor backend emisor; los servicios verificadores solo requieren la clave pública.
3. **Manejo de Errores de Descifrado:** `FernetSecretCipher.decrypt` debe atrapar `InvalidToken` y relanzar `InvalidTokenError`. Nunca permitir que excepciones de bajo nivel de `cryptography` alcancen las capas de aplicación o presentación.
4. **Segregación de Tipos de Token:** `JoseJwtVerifier.verify` debe validar obligatoriamente el parámetro `expected_type`. Un token emitido como `TokenType.REFRESH` no puede ser aceptado en endpoints protegidos que esperan `TokenType.ACCESS`.
5. **No Almacenar Plaintext:** Las API keys y tokens OAuth nunca deben persistirse en texto claro en ninguna tabla o archivo de log. Utilizar siempre `FernetSecretCipher.to_storage_str` antes del commit en PostgreSQL.
