# conftest.py se ejecuta antes de que pytest importe cualquier módulo de la aplicación.
# Las variables de entorno se inyectan aquí a nivel de módulo para que Settings()
# en config.py pueda inicializarse correctamente al momento de la importación.

import os
from base64 import urlsafe_b64encode
from secrets import token_bytes

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Par de llaves RSA efímero generado una vez por sesión de pruebas (sin archivos en disco).
_rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_PRIVATE_KEY_PEM: str = _rsa_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

_PUBLIC_KEY_PEM: str = (
    _rsa_key.public_key()
    .public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)

# Llave Fernet: 32 bytes aleatorios codificados en base64 url-safe.
_FERNET_KEY: str = urlsafe_b64encode(token_bytes(32)).decode()

# Se usa setdefault para no sobreescribir variables ya definidas en el entorno del desarrollador.
_TEST_DEFAULTS: dict[str, str] = {
    "ENV": "development",
    "LOG_LEVEL": "DEBUG",
    # Auth real en tests: el bypass de dev (.env AUTH_DISABLED=true) no debe filtrarse aquí.
    "AUTH_DISABLED": "false",
    # Llaves criptográficas inyectadas como texto PEM, no como rutas de archivo.
    "JWT_PRIVATE_KEY_PEM": _PRIVATE_KEY_PEM,
    "JWT_PUBLIC_KEY_PEM": _PUBLIC_KEY_PEM,
    "FERNET_MASTER_KEY": _FERNET_KEY,
    # Adaptador noop: no requiere API key real.
    "LLM_PROVIDER": "noop",
    "LLM_MODEL": "noop",
    # DSNs de infraestructura: valores stub; los tests deben usar fakes en memoria.
    "DATABASE_URL": "postgresql+asyncpg://kosmo:kosmo@localhost:5432/kosmo_test",
    "REDIS_URL": "redis://:test_redis_pass@localhost:6379/1",
    "OTEL_SERVICE_NAME": "kosmo-backend-test",
    "OTEL_ENVIRONMENT": "development",
}

for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def rsa_key_pair() -> tuple[str, str]:
    """Retorna el par de claves RSA (privada, publica) en formato PEM para la sesion."""
    return _PRIVATE_KEY_PEM, _PUBLIC_KEY_PEM
