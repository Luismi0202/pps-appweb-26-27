"""Simulación de un ataque DoS de capa de aplicación con Locust (solo LOCAL).

Mezcla dos tipos de usuario contra la misma API:

- ``Legitimo``: personas normales. Cada una tiene su **propia IP** (simulada
  con ``X-Forwarded-For``), entra una vez y navega por el catálogo con pausas.
- ``Atacante`` (5 usuarios fijos, **misma IP** 203.0.113.66, sin pausas):
  inunda el login con contraseñas falsas (fuerza bruta, cada intento cuesta un
  bcrypt) y la API con peticiones. Sus peticiones llevan el prefijo
  ``[ATAQUE]`` en las estadísticas.

Se compara el servidor **con** y **sin** la protección de ``app/anti_ddos.py``.
Hace falta arrancarlo fiándose de ``X-Forwarded-For`` (``--proxies 1``):

    python tests/servidor_aislado.py --port 8765 --proxies 1 --anti-ddos   # protegido
    python tests/servidor_aislado.py --port 8765 --proxies 1               # sin protección

    locust -f tests/estres/locustfile_ddos.py --host http://127.0.0.1:8765 \
        --headless -u 55 -r 10 -t 60s --csv tests/estres/resultados/ddos_con

⚠️ No lanzar contra producción: es, literalmente, un ataque.
"""
from __future__ import annotations

import itertools
import os
import random

from locust import HttpUser, between, constant, task

ADMIN_EMAIL = os.getenv("LUDOTECA_ADMIN_EMAIL", "admin@ludoteca.local")
ADMIN_PASSWORD = os.getenv("LUDOTECA_ADMIN_PASSWORD", "admin123")
IP_ATACANTE = "203.0.113.66"
_ips = (f"198.51.{a}.{b}" for a, b in itertools.product(range(100, 120), range(1, 255)))


class Legitimo(HttpUser):
    weight = 10
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers["X-Forwarded-For"] = next(_ips)
        r = self.client.post("/api/auth/login",
                             json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if r.status_code == 200:
            self.client.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    @task(4)
    def catalogo(self):
        self.client.get("/api/videojuegos?por_pagina=12", name="/api/videojuegos")

    @task(2)
    def buscar(self):
        q = random.choice(["zelda", "mario", "ring", "hades"])
        self.client.get(f"/api/videojuegos?q={q}", name="/api/videojuegos?q=")

    @task(2)
    def ficha(self):
        self.client.get(f"/api/videojuegos/{random.randint(1, 10)}", name="/api/videojuegos/{id}")

    @task(1)
    def estadisticas(self):
        self.client.get("/api/estadisticas/resumen")


class Atacante(HttpUser):
    fixed_count = 5           # siempre 5, aunque se pidan más usuarios
    wait_time = constant(0)   # sin pausa: tan rápido como pueda

    def on_start(self):
        self.client.headers["X-Forwarded-For"] = IP_ATACANTE

    @task(3)
    def fuerza_bruta(self):
        self.client.post("/api/auth/login",
                         json={"email": ADMIN_EMAIL, "password": f"intento{random.randint(0, 10**6)}"},
                         name="[ATAQUE] POST /api/auth/login")

    @task(1)
    def inundar(self):
        self.client.get("/api/videojuegos", name="[ATAQUE] GET /api/videojuegos")
