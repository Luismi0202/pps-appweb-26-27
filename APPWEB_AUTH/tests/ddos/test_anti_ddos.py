"""Pruebas de la protección anti-DDoS (``app/anti_ddos.py``).

Se monta el middleware real sobre una mini-app con rutas que imitan a las de
la Ludoteca, para poder lanzar cientos de peticiones en milisegundos sin
base de datos. La prueba con la app completa bajo carga real está en
``tests/estres/locustfile_ddos.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.anti_ddos import AntiDDoS  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    for var in ("LUDOTECA_ANTI_DDOS", "LUDOTECA_PROXIES_CONFIABLES", "LUDOTECA_LIMITE_GENERAL",
                "LUDOTECA_LIMITE_AUTH", "LUDOTECA_MAX_CUERPO_KB"):
        monkeypatch.delenv(var, raising=False)  # valores por defecto
    app = FastAPI()
    app.add_middleware(AntiDDoS)

    @app.get("/api/salud")
    def salud():
        return {"estado": "ok"}

    @app.post("/api/auth/login")
    def login():
        return {"detail": "Email o contraseña incorrectos"}

    @app.post("/api/auth/refresh")
    def refresh():
        return {"ok": True}

    @app.get("/api/auth/oauth/proveedores")
    def proveedores():
        return {"google": False, "github": False}

    @app.post("/api/videojuegos")
    def crear():
        return {"ok": True}

    return TestClient(app)


def _rafaga(cliente, n, metodo="get", ruta="/api/salud", **kw):
    return [getattr(cliente, metodo)(ruta, **kw).status_code for _ in range(n)]


# ---------------------------------------------------------------------------
# 1. Inundación de peticiones desde una IP
# ---------------------------------------------------------------------------
def test_inundacion_desde_una_ip_recibe_429(cliente):
    codigos = _rafaga(cliente, 320)
    assert codigos[:300] == [200] * 300  # límite general por defecto: 300/min
    assert set(codigos[300:]) == {429}


def test_el_429_lleva_retry_after_y_mensaje(cliente):
    _rafaga(cliente, 300)
    r = cliente.get("/api/salud")
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert "Demasiadas peticiones" in r.json()["detail"]


def test_limite_configurable(cliente, monkeypatch):
    monkeypatch.setenv("LUDOTECA_LIMITE_GENERAL", "10")
    codigos = _rafaga(cliente, 12)
    assert codigos.count(200) == 10 and codigos.count(429) == 2


def test_se_recupera_al_pasar_la_ventana(cliente, monkeypatch):
    import app.anti_ddos as modulo

    reloj = [1000.0]
    monkeypatch.setattr(modulo.time, "monotonic", lambda: reloj[0])
    monkeypatch.setenv("LUDOTECA_LIMITE_GENERAL", "5")
    assert _rafaga(cliente, 6)[-1] == 429
    reloj[0] += 61  # pasa un minuto
    assert cliente.get("/api/salud").status_code == 200


# ---------------------------------------------------------------------------
# 2. Fuerza bruta contra el login
# ---------------------------------------------------------------------------
def test_fuerza_bruta_de_login_se_corta_a_los_20_intentos(cliente):
    cuerpo = {"email": "admin@ludoteca.local", "password": "probando"}
    codigos = _rafaga(cliente, 25, "post", "/api/auth/login", json=cuerpo)
    assert codigos[:20] == [200] * 20
    assert set(codigos[20:]) == {429}
    r = cliente.post("/api/auth/login", json=cuerpo)
    assert "inicio de sesión" in r.json()["detail"]


def test_bloqueo_de_login_no_afecta_al_resto_de_la_api(cliente):
    _rafaga(cliente, 25, "post", "/api/auth/login", json={})
    assert cliente.get("/api/salud").status_code == 200
    assert cliente.post("/api/auth/refresh").status_code == 200  # refresh no cuenta como intento
    assert cliente.get("/api/auth/oauth/proveedores").status_code == 200


# ---------------------------------------------------------------------------
# 3. IPs distintas y X-Forwarded-For
# ---------------------------------------------------------------------------
def test_sin_proxy_no_se_puede_falsear_la_ip(cliente):
    """Con 0 proxies se ignora X-Forwarded-For: cambiarla no salta el límite."""
    codigos = [cliente.post("/api/auth/login", json={},
                            headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
               for i in range(25)]
    assert codigos.count(429) == 5


def test_detras_de_proxy_cada_cliente_tiene_su_limite(cliente, monkeypatch):
    monkeypatch.setenv("LUDOTECA_PROXIES_CONFIABLES", "1")
    atacante = {"X-Forwarded-For": "203.0.113.66"}
    legitimo = {"X-Forwarded-For": "198.51.100.7"}
    assert _rafaga(cliente, 25, "post", "/api/auth/login", json={}, headers=atacante)[-1] == 429
    # El usuario legítimo, desde otra IP, entra sin problema.
    assert cliente.post("/api/auth/login", json={}, headers=legitimo).status_code == 200


def test_detras_de_proxy_se_usa_la_ip_que_anade_el_proxy(cliente, monkeypatch):
    """Si el atacante manda su propia X-Forwarded-For, el proxy añade la real al
    final: con 1 proxy de confianza se cuenta la última, no la inventada."""
    monkeypatch.setenv("LUDOTECA_PROXIES_CONFIABLES", "1")
    codigos = [cliente.post("/api/auth/login", json={},
                            headers={"X-Forwarded-For": f"1.1.1.{i}, 203.0.113.66"}).status_code
               for i in range(25)]
    assert codigos.count(429) == 5


# ---------------------------------------------------------------------------
# 4. Cuerpos enormes
# ---------------------------------------------------------------------------
def test_cuerpo_demasiado_grande_413(cliente):
    enorme = b"x" * (1024 * 1024 + 1)
    r = cliente.post("/api/videojuegos", content=enorme,
                     headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_cuerpo_normal_pasa(cliente):
    assert cliente.post("/api/videojuegos", json={"titulo": "x" * 1000}).status_code == 200


# ---------------------------------------------------------------------------
# 5. Interruptor
# ---------------------------------------------------------------------------
def test_se_puede_desactivar(cliente, monkeypatch):
    monkeypatch.setenv("LUDOTECA_ANTI_DDOS", "0")
    assert set(_rafaga(cliente, 350)) == {200}
