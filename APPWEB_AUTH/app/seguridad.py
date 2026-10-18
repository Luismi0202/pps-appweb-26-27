"""Seguridad: hash de contraseñas y tokens JWT."""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ROL_ADMIN, ROL_GESTOR, Usuario

# En producción define LUDOTECA_SECRET_KEY como variable de entorno.
SECRET_KEY = os.getenv(
    "LUDOTECA_SECRET_KEY", "ludoteca-clave-de-desarrollo-cambiala-en-produccion"
)
ALGORITHM = "HS256"
MINUTOS_TOKEN = int(os.getenv("LUDOTECA_TOKEN_MINUTOS", "480"))  # 8 horas
# El refresh token vive mucho más que el access token: permite renovar la
# sesión sin volver a introducir la contraseña (POST /api/auth/refresh).
MINUTOS_REFRESH = int(os.getenv("LUDOTECA_REFRESH_MINUTOS", "10080"))  # 7 días

# Tipos de token (claim "tipo"): impide usar un access como refresh y viceversa.
TIPO_ACCESS = "access"
TIPO_REFRESH = "refresh"

# Esquema "Bearer": Swagger muestra el botón Authorize para pegar el token.
esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token JWT obtenido en POST /api/auth/login",
)


# ---------------------------------------------------------------------------
# Contraseñas
# ---------------------------------------------------------------------------
def _bytes_password(password: str) -> bytes:
    # bcrypt solo admite 72 bytes
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bytes_password(password), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bytes_password(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Tokens JWT
# ---------------------------------------------------------------------------
def crear_token(usuario_id: int, tipo: str = TIPO_ACCESS) -> str:
    """Firma un JWT. El claim ``tipo`` distingue access de refresh."""
    ahora = datetime.now(timezone.utc)
    validez = MINUTOS_TOKEN if tipo == TIPO_ACCESS else MINUTOS_REFRESH
    payload = {
        "sub": str(usuario_id),
        "tipo": tipo,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=validez),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def crear_refresh_token(usuario_id: int) -> str:
    """Token largo para renovar la sesión sin volver a pasar la contraseña."""
    return crear_token(usuario_id, TIPO_REFRESH)


def decodificar_token(token: str, tipo: str = TIPO_ACCESS) -> int:
    """Devuelve el id de usuario o lanza 401 si el token no es válido.

    Además comprueba que el token sea del ``tipo`` esperado: un refresh token
    no sirve como access token (ni al revés). Los tokens antiguos, sin el
    claim ``tipo``, se tratan como access.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("tipo", TIPO_ACCESS) != tipo:
            raise jwt.InvalidTokenError("tipo de token no válido")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o caducado",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Dependencias de FastAPI
# ---------------------------------------------------------------------------
def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """Devuelve el usuario autenticado o lanza 401."""
    if credenciales is None or not credenciales.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado: falta el token Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.get(Usuario, decodificar_token(credenciales.credentials))
    if usuario is None or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario del token no existe o está desactivado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def usuario_del_refresh(token: str, db: Session) -> Usuario:
    """Valida un refresh token y devuelve su usuario (o lanza 401)."""
    usuario = db.get(Usuario, decodificar_token(token, TIPO_REFRESH))
    if usuario is None or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token de una cuenta inexistente o desactivada",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


# ---------------------------------------------------------------------------
# Permisos por rol
# ---------------------------------------------------------------------------
def es_admin(usuario: Usuario) -> bool:
    """True si la cuenta tiene rol de administrador."""
    return usuario.rol == ROL_ADMIN


def puede_gestionar(usuario: Usuario) -> bool:
    """True si la cuenta puede gestionar el catálogo (gestor o admin)."""
    return usuario.rol in (ROL_GESTOR, ROL_ADMIN)


def requiere_gestor(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Permite gestionar el catálogo: administradores y gestores."""
    if not puede_gestionar(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Necesitas permiso de gestor o administrador para esta acción",
        )
    return usuario


def requiere_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Permite administrar la plataforma: solo administradores."""
    if not es_admin(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede realizar esta acción",
        )
    return usuario
