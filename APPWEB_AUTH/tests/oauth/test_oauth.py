"""Pruebas del login con Google y GitHub (``app/routers/oauth.py``).

Google y GitHub se **simulan**: se sustituye ``_peticion_json`` (la única
función que habla con ellos) por respuestas preparadas. Todo lo demás es
real: la app FastAPI con su lifespan, la BD SQLite (temporal), el ``state``
firmado, la cookie, la creación/vinculación de cuentas y los JWT que se
emiten, que luego se usan contra la API como en el panel.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
from pathlib import Path

import pytest

RAIZ_APP = Path(__file__).resolve().parents[2]
PUBLICA = "http://ludoteca.test"  # http: TestClient no devuelve cookies Secure


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    """App real con BD temporal y los dos proveedores configurados."""
    carpeta = tmp_path_factory.mktemp("bd_oauth")
    anterior = os.getcwd()
    os.chdir(carpeta)  # la app abre ./coleccion_videojuegos.db
    entorno = {
        "GOOGLE_CLIENT_ID": "google-id-prueba", "GOOGLE_CLIENT_SECRET": "google-secreto",
        "GITHUB_CLIENT_ID": "github-id-prueba", "GITHUB_CLIENT_SECRET": "github-secreto",
        "LUDOTECA_PUBLIC_URL": PUBLICA,
        # Todas las peticiones salen de la misma IP: sin límites anti-DDoS
        # (se prueban aparte en tests/ddos).
        "LUDOTECA_ANTI_DDOS": "0",
    }
    os.environ.update(entorno)
    sys.path.insert(0, str(RAIZ_APP))
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
    for clave in entorno:
        os.environ.pop(clave, None)
    os.chdir(anterior)


@pytest.fixture
def proveedor_falso(monkeypatch):
    """Sustituye a Google/GitHub. Devuelve el dict de perfiles a modificar."""
    from app.routers import oauth

    perfil = {
        "google": {"sub": "g-123", "email": "ana@gmail.test", "email_verified": True, "name": "Ana Google"},
        "github": {"id": 4242, "login": "pepe-gh", "name": None},
        "github_emails": [
            {"email": "pepe.secundario@gh.test", "primary": False, "verified": True},
            {"email": "pepe@gh.test", "primary": True, "verified": True},
        ],
        "llamadas": [],
    }

    def falso(url, *, datos=None, token=None):
        perfil["llamadas"].append((url, datos, token))
        if url.endswith("/token") or url.endswith("/access_token"):
            assert datos["code"] == "codigo-valido"
            assert datos["redirect_uri"].startswith(PUBLICA + "/api/auth/oauth/")
            return {"access_token": "token-del-proveedor"}
        assert token == "token-del-proveedor"
        if "googleapis" in url:
            return perfil["google"]
        if url.endswith("/user/emails"):
            return perfil["github_emails"]
        if url.endswith("/user"):
            return perfil["github"]
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(oauth, "_peticion_json", falso)
    return perfil


def _iniciar(cliente, proveedor):
    """Paso 1: /login. Devuelve el ``state`` que iría al proveedor."""
    r = cliente.get(f"/api/auth/oauth/{proveedor}/login", follow_redirects=False)
    assert r.status_code == 307
    destino = urllib.parse.urlparse(r.headers["location"])
    params = dict(urllib.parse.parse_qsl(destino.query))
    return destino, params


def _volver(cliente, proveedor, **params):
    """Paso 3: el proveedor redirige al callback. Devuelve el fragmento."""
    r = cliente.get(f"/api/auth/oauth/{proveedor}/callback", params=params, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/panel/login.html#")
    return dict(urllib.parse.parse_qsl(r.headers["location"].split("#", 1)[1]))


def _sesion(fragmento):
    carga = fragmento["oauth"]
    return json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))


def _login_completo(cliente, proveedor):
    _, params = _iniciar(cliente, proveedor)
    return _volver(cliente, proveedor, code="codigo-valido", state=params["state"])


# ---------------------------------------------------------------------------
def test_proveedores_configurados(cliente):
    assert cliente.get("/api/auth/oauth/proveedores").json() == {"google": True, "github": True}


@pytest.mark.parametrize("proveedor,host,scope", [
    ("google", "accounts.google.com", "openid email profile"),
    ("github", "github.com", "read:user user:email"),
])
def test_login_redirige_al_proveedor(cliente, proveedor, host, scope):
    destino, params = _iniciar(cliente, proveedor)
    assert destino.netloc == host
    assert params["client_id"] == f"{proveedor}-id-prueba"
    assert params["redirect_uri"] == f"{PUBLICA}/api/auth/oauth/{proveedor}/callback"
    assert params["scope"] == scope
    assert params["state"].count(".") == 2  # JWT firmado
    assert cliente.cookies.get("ludoteca_oauth_state")


def test_google_registra_usuario_nuevo_y_emite_los_mismos_jwt(cliente, proveedor_falso):
    sesion = _sesion(_login_completo(cliente, "google"))
    assert set(sesion) >= {"access_token", "refresh_token", "token_type", "usuario"}
    assert sesion["usuario"]["email"] == "ana@gmail.test"
    assert sesion["usuario"]["nombre"] == "Ana Google"
    assert sesion["usuario"]["rol"] == "usuario"

    # El access token sirve en la API igual que el del login con contraseña…
    yo = cliente.get("/api/auth/yo", headers={"Authorization": "Bearer " + sesion["access_token"]})
    assert yo.status_code == 200 and yo.json()["email"] == "ana@gmail.test"
    col = cliente.get("/api/colecciones", headers={"Authorization": "Bearer " + sesion["access_token"]})
    assert col.status_code == 200 and col.json()["total"] == 0
    # …y el refresh token renueva la sesión con el endpoint de siempre.
    ref = cliente.post("/api/auth/refresh", json={"refresh_token": sesion["refresh_token"]})
    assert ref.status_code == 200


def test_segundo_login_reutiliza_la_misma_cuenta(cliente, proveedor_falso):
    primero = _sesion(_login_completo(cliente, "google"))
    segundo = _sesion(_login_completo(cliente, "google"))
    assert primero["usuario"]["id"] == segundo["usuario"]["id"]


def test_github_usa_el_email_principal_verificado_y_el_login_como_nombre(cliente, proveedor_falso):
    sesion = _sesion(_login_completo(cliente, "github"))
    assert sesion["usuario"]["email"] == "pepe@gh.test"
    assert sesion["usuario"]["nombre"] == "pepe-gh"


def test_vincula_con_cuenta_existente_del_mismo_email(cliente, proveedor_falso):
    """El admin (registrado con contraseña) entra con Google y sigue siendo admin."""
    proveedor_falso["google"] = {"sub": "g-admin", "email": "admin@ludoteca.local",
                                 "email_verified": True, "name": "Otro nombre"}
    sesion = _sesion(_login_completo(cliente, "google"))
    assert sesion["usuario"]["email"] == "admin@ludoteca.local"
    assert sesion["usuario"]["rol"] == "admin"
    assert sesion["usuario"]["nombre"] == "admin"  # no se pisa su nombre
    # El login de siempre sigue funcionando para esa cuenta.
    r = cliente.post("/api/auth/login", json={"email": "admin@ludoteca.local", "password": "admin123"})
    assert r.status_code == 200 and r.json()["usuario"]["id"] == sesion["usuario"]["id"]


def test_la_misma_persona_puede_entrar_con_google_y_con_github(cliente, proveedor_falso):
    proveedor_falso["google"] = {"sub": "g-pepe", "email": "pepe@gh.test",
                                 "email_verified": True, "name": "Pepe"}
    por_github = _sesion(_login_completo(cliente, "github"))
    por_google = _sesion(_login_completo(cliente, "google"))
    assert por_github["usuario"]["id"] == por_google["usuario"]["id"]


def test_email_sin_verificar_se_rechaza(cliente, proveedor_falso):
    proveedor_falso["google"] = {"sub": "g-x", "email": "x@x.test", "email_verified": False}
    fragmento = _login_completo(cliente, "google")
    assert "oauth" not in fragmento
    assert "email verificado" in fragmento["oauth_error"]


def test_github_sin_emails_verificados_se_rechaza(cliente, proveedor_falso):
    proveedor_falso["github"] = {"id": 999, "login": "sin-email"}
    proveedor_falso["github_emails"] = [{"email": "a@b.test", "primary": True, "verified": False}]
    assert "email verificado" in _login_completo(cliente, "github")["oauth_error"]


def test_state_manipulado_se_rechaza(cliente, proveedor_falso):
    _, params = _iniciar(cliente, "google")
    fragmento = _volver(cliente, "google", code="codigo-valido", state=params["state"] + "x")
    assert "oauth_error" in fragmento
    assert proveedor_falso["llamadas"] == []  # ni siquiera se llama al proveedor


def test_state_de_otro_proveedor_se_rechaza(cliente, proveedor_falso):
    _, params = _iniciar(cliente, "github")
    fragmento = _volver(cliente, "google", code="codigo-valido", state=params["state"])
    assert "oauth_error" in fragmento


def test_sin_cookie_del_navegador_se_rechaza(cliente, proveedor_falso):
    """Protección CSRF: el state solo vale en el navegador que inició el login."""
    _, params = _iniciar(cliente, "google")
    cliente.cookies.clear()
    fragmento = _volver(cliente, "google", code="codigo-valido", state=params["state"])
    assert "oauth_error" in fragmento


def test_cookie_secure_con_url_publica_https(cliente, monkeypatch):
    """En Render (https detrás de proxy) la cookie del state debe ir con Secure."""
    monkeypatch.setenv("LUDOTECA_PUBLIC_URL", "https://ludoteca.test")
    r = cliente.get("/api/auth/oauth/google/login", follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_cancelar_en_el_proveedor(cliente):
    fragmento = _volver(cliente, "github", error="access_denied")
    assert "cancelado" in fragmento["oauth_error"]


def test_proveedor_desconocido_404(cliente):
    assert cliente.get("/api/auth/oauth/facebook/login", follow_redirects=False).status_code == 404


def test_borrar_usuario_borra_su_vinculo(cliente, proveedor_falso):
    proveedor_falso["google"] = {"sub": "g-borrable", "email": "borrable@gmail.test",
                                 "email_verified": True, "name": "Borrable"}
    antes = _sesion(_login_completo(cliente, "google"))["usuario"]["id"]

    admin = cliente.post("/api/auth/login", json={"email": "admin@ludoteca.local",
                                                  "password": "admin123"}).json()["access_token"]
    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.models_oauth import CuentaOAuth

    def vinculos():
        with SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(CuentaOAuth)
                             .where(CuentaOAuth.sub == "g-borrable"))

    assert vinculos() == 1
    r = cliente.delete(f"/api/usuarios/{antes}", headers={"Authorization": "Bearer " + admin})
    assert r.status_code == 200
    assert vinculos() == 0  # ON DELETE CASCADE

    # Puede volver a entrar: se crea una cuenta nueva (vacía) con su vínculo.
    sesion = _sesion(_login_completo(cliente, "google"))
    assert sesion["usuario"]["email"] == "borrable@gmail.test"
    assert vinculos() == 1


def test_proveedor_sin_configurar(cliente, monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_SECRET")
    assert cliente.get("/api/auth/oauth/proveedores").json()["github"] is False
    r = cliente.get("/api/auth/oauth/github/login", follow_redirects=False)
    assert r.status_code == 303
    assert "no%20est%C3%A1%20configurado" in r.headers["location"]
