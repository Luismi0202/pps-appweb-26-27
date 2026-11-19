"""Inicio de sesión y registro con Google y GitHub (OAuth 2.0).

Es **otra forma de entrar**, no sustituye al login con email y contraseña:
al terminar, la API emite exactamente el mismo par de JWT (access + refresh,
con la ``token_version`` de la cuenta) que ``POST /api/auth/login``, así que
el resto de la aplicación (panel, refresh, roles, cambio de contraseña…)
funciona igual.

Flujo (*Authorization Code*, en el servidor):

1. El panel enlaza a ``GET /api/auth/oauth/{proveedor}/login``.
2. La API redirige a Google/GitHub con un ``state`` firmado (anti-CSRF) y
   guarda su *nonce* en una cookie ``HttpOnly`` de 10 minutos.
3. El proveedor vuelve a ``GET /api/auth/oauth/{proveedor}/callback`` con un
   ``code``. La API comprueba el ``state`` contra la cookie, cambia el
   ``code`` por un token del proveedor y pide el perfil (id + email
   verificado).
4. Busca la cuenta vinculada; si no existe, la vincula al usuario con ese
   email (si ya tenía cuenta) o crea un usuario nuevo con rol ``usuario``.
5. Redirige a ``/panel/login.html#oauth=<tokens>``. Los tokens van en el
   *fragmento* de la URL, que el navegador nunca envía a ningún servidor, y
   ``frontend/oauth.js`` los guarda igual que el login normal.

Configuración (variables de entorno; si faltan, ese botón no aparece):

- ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``
- ``GITHUB_CLIENT_ID`` / ``GITHUB_CLIENT_SECRET``
- ``LUDOTECA_PUBLIC_URL`` (opcional): URL pública, p. ej.
  ``https://pps-appweb-26-27-sju7.onrender.com``. Sirve para construir la
  *redirect URI* exacta registrada en el proveedor; si no se define se usa la
  URL con la que llega la petición.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.models_oauth import PROVEEDOR_GITHUB, PROVEEDOR_GOOGLE, CuentaOAuth
from app.routers.auth import _respuesta_token  # mismos JWT que el login normal
from app.seguridad import ALGORITHM, SECRET_KEY, hash_password

router = APIRouter(prefix="/api/auth/oauth", tags=["0. Autenticación"])

COOKIE_STATE = "ludoteca_oauth_state"
MINUTOS_STATE = 10
TIMEOUT_HTTP = 10  # segundos para hablar con Google/GitHub
PAGINA_LOGIN = "/panel/login.html"

PROVEEDORES = {
    PROVEEDOR_GOOGLE: {
        "nombre": "Google",
        "env_id": "GOOGLE_CLIENT_ID",
        "env_secret": "GOOGLE_CLIENT_SECRET",
        "autorizar": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    PROVEEDOR_GITHUB: {
        "nombre": "GitHub",
        "env_id": "GITHUB_CLIENT_ID",
        "env_secret": "GITHUB_CLIENT_SECRET",
        "autorizar": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "read:user user:email",
    },
}


class ErrorOAuth(Exception):
    """Error que se muestra al usuario en la pantalla de login."""


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def _credenciales(proveedor: str) -> tuple[str, str] | None:
    conf = PROVEEDORES[proveedor]
    client_id = os.getenv(conf["env_id"], "").strip()
    client_secret = os.getenv(conf["env_secret"], "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def _conf(proveedor: str) -> dict:
    if proveedor not in PROVEEDORES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Proveedor desconocido: {proveedor}")
    return PROVEEDORES[proveedor]


def _redirect_uri(request: Request, proveedor: str) -> str:
    base = os.getenv("LUDOTECA_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/api/auth/oauth/{proveedor}/callback"


# ---------------------------------------------------------------------------
# State anti-CSRF: JWT firmado con la clave de la app + nonce en cookie
# ---------------------------------------------------------------------------
def _crear_state(proveedor: str, nonce: str) -> str:
    ahora = datetime.now(timezone.utc)
    datos = {
        "tipo": "oauth_state",
        "prov": proveedor,
        "nonce": nonce,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=MINUTOS_STATE),
    }
    return jwt.encode(datos, SECRET_KEY, algorithm=ALGORITHM)


def _validar_state(state: str | None, proveedor: str, nonce_cookie: str | None) -> None:
    if not state or not nonce_cookie:
        raise ErrorOAuth("La sesión de inicio con el proveedor ha caducado. Inténtalo de nuevo.")
    try:
        datos = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise ErrorOAuth("Petición de inicio de sesión no válida o caducada. Inténtalo de nuevo.")
    if (
        datos.get("tipo") != "oauth_state"
        or datos.get("prov") != proveedor
        or not secrets.compare_digest(str(datos.get("nonce", "")), nonce_cookie)
    ):
        raise ErrorOAuth("Petición de inicio de sesión no válida. Inténtalo de nuevo.")


# ---------------------------------------------------------------------------
# HTTP con los proveedores (urllib: sin dependencias nuevas)
# ---------------------------------------------------------------------------
def _peticion_json(url: str, *, datos: dict | None = None, token: str | None = None) -> dict | list:
    cabeceras = {"Accept": "application/json", "User-Agent": "Ludoteca-OAuth"}
    cuerpo = None
    if datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode("utf-8")
        cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras,
                                 method="POST" if cuerpo is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise ErrorOAuth("No se pudo contactar con el proveedor. Inténtalo más tarde.") from e


def _intercambiar_codigo(proveedor: str, code: str, redirect_uri: str) -> str:
    """Cambia el ``code`` de la redirección por un access token del proveedor."""
    client_id, client_secret = _credenciales(proveedor)
    respuesta = _peticion_json(PROVEEDORES[proveedor]["token"], datos={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    token = respuesta.get("access_token") if isinstance(respuesta, dict) else None
    if not token:
        raise ErrorOAuth("El proveedor no aceptó el inicio de sesión. Inténtalo de nuevo.")
    return token


def _perfil(proveedor: str, token: str) -> dict:
    """Devuelve ``{"sub", "email", "nombre"}`` con un email **verificado**."""
    nombre_prov = PROVEEDORES[proveedor]["nombre"]
    if proveedor == PROVEEDOR_GOOGLE:
        datos = _peticion_json("https://openidconnect.googleapis.com/v1/userinfo", token=token)
        email = datos.get("email") if datos.get("email_verified") else None
        sub, nombre = datos.get("sub"), datos.get("name") or datos.get("given_name")
    else:  # GitHub
        datos = _peticion_json("https://api.github.com/user", token=token)
        sub, nombre = datos.get("id"), datos.get("name") or datos.get("login")
        correos = _peticion_json("https://api.github.com/user/emails", token=token)
        verificados = [c for c in correos if isinstance(c, dict) and c.get("verified")] \
            if isinstance(correos, list) else []
        principal = next((c for c in verificados if c.get("primary")), None)
        email = (principal or (verificados[0] if verificados else {})).get("email")

    if not sub:
        raise ErrorOAuth(f"{nombre_prov} no devolvió un identificador de cuenta.")
    if not email:
        raise ErrorOAuth(f"Tu cuenta de {nombre_prov} no tiene un email verificado.")
    return {"sub": str(sub), "email": email.strip().lower(), "nombre": nombre}


# ---------------------------------------------------------------------------
# Cuenta local: buscar vínculo, vincular por email o crear usuario
# ---------------------------------------------------------------------------
def _nombre_valido(nombre: str | None, email: str) -> str:
    nombre = (nombre or "").strip() or email.split("@")[0]
    nombre = nombre[:50]
    return nombre if len(nombre) >= 2 else (nombre + "_jugador")[:50]


def _usuario_para(db: Session, proveedor: str, perfil: dict) -> Usuario:
    vinculo = db.scalar(select(CuentaOAuth).where(
        CuentaOAuth.proveedor == proveedor, CuentaOAuth.sub == perfil["sub"]))
    if vinculo is not None:
        usuario = db.get(Usuario, vinculo.usuario_id)
        if usuario is not None:
            return usuario
        # Vínculo huérfano (BD sin claves foráneas activas): se descarta.
        db.delete(vinculo)
        db.flush()

    # ¿Ya tenía cuenta con ese email (registrada con contraseña o con el otro
    # proveedor)? Se vincula: el email está verificado por el proveedor.
    usuario = db.scalar(select(Usuario).where(func.lower(Usuario.email) == perfil["email"]))
    if usuario is None:
        usuario = Usuario(
            nombre=_nombre_valido(perfil["nombre"], perfil["email"]),
            email=perfil["email"],
            # Contraseña aleatoria que nadie conoce: la cuenta entra con el
            # proveedor. Si se quiere entrar también con email/contraseña, un
            # admin puede restablecérsela desde la pestaña Usuarios.
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(usuario)
        db.flush()

    db.add(CuentaOAuth(usuario_id=usuario.id, proveedor=proveedor,
                       sub=perfil["sub"], email=perfil["email"]))
    db.commit()
    db.refresh(usuario)
    return usuario


# ---------------------------------------------------------------------------
# Respuestas hacia el panel
# ---------------------------------------------------------------------------
def _volver_al_login(fragmento: str) -> RedirectResponse:
    resp = RedirectResponse(f"{PAGINA_LOGIN}#{fragmento}", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(COOKIE_STATE, path="/api/auth/oauth")
    return resp


def _error(mensaje: str) -> RedirectResponse:
    return _volver_al_login("oauth_error=" + urllib.parse.quote(mensaje))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/proveedores", summary="Proveedores de login social configurados")
def proveedores():
    """Indica qué botones ("Continuar con Google/GitHub") debe mostrar el panel."""
    return {p: _credenciales(p) is not None for p in PROVEEDORES}


@router.get(
    "/{proveedor}/login",
    summary="Iniciar sesión o registrarse con Google o GitHub",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
def oauth_login(proveedor: str, request: Request):
    """Redirige a la pantalla de consentimiento del proveedor.

    Ábrelo en el navegador (no desde Swagger): al terminar vuelves al panel
    con la sesión iniciada.
    """
    conf = _conf(proveedor)
    credenciales = _credenciales(proveedor)
    if credenciales is None:
        return _error(f"El inicio de sesión con {conf['nombre']} no está configurado.")

    nonce = secrets.token_urlsafe(24)
    parametros = {
        "client_id": credenciales[0],
        "redirect_uri": _redirect_uri(request, proveedor),
        "scope": conf["scope"],
        "state": _crear_state(proveedor, nonce),
    }
    if proveedor == PROVEEDOR_GOOGLE:
        parametros.update(response_type="code", prompt="select_account")
    else:
        parametros.update(allow_signup="true")

    resp = RedirectResponse(f"{conf['autorizar']}?{urllib.parse.urlencode(parametros)}",
                            status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    resp.set_cookie(
        COOKIE_STATE, nonce, max_age=MINUTOS_STATE * 60, httponly=True,
        samesite="lax", path="/api/auth/oauth",
        # Detrás del proxy de Render la app ve "http": se usa también la URL pública.
        secure=request.url.scheme == "https"
        or os.getenv("LUDOTECA_PUBLIC_URL", "").startswith("https://"),
    )
    return resp


@router.get(
    "/{proveedor}/callback",
    summary="Vuelta desde Google o GitHub (la llama el proveedor)",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
def oauth_callback(
    proveedor: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    conf = _conf(proveedor)
    if error:  # p. ej. el usuario pulsó "Cancelar" en el proveedor
        return _error(f"Inicio de sesión con {conf['nombre']} cancelado.")
    if _credenciales(proveedor) is None:
        return _error(f"El inicio de sesión con {conf['nombre']} no está configurado.")
    try:
        _validar_state(state, proveedor, request.cookies.get(COOKIE_STATE))
        if not code:
            raise ErrorOAuth("Falta el código de autorización del proveedor.")
        token = _intercambiar_codigo(proveedor, code, _redirect_uri(request, proveedor))
        perfil = _perfil(proveedor, token)
        usuario = _usuario_para(db, proveedor, perfil)
    except ErrorOAuth as e:
        return _error(str(e))

    if not usuario.activo:
        return _error("La cuenta está desactivada")

    tokens = _respuesta_token(usuario).model_dump(mode="json")
    carga = base64.urlsafe_b64encode(json.dumps(tokens).encode("utf-8")).decode("ascii").rstrip("=")
    return _volver_al_login("oauth=" + carga)
