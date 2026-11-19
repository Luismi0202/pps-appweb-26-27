"""Prueba de carga contra el despliegue de PRODUCCIÓN (Render).

Pensada para no hacer daño ni ensuciar la base de datos real:

- Por defecto **no inicia sesión ni escribe nada**: hace lo que haría un
  visitante anónimo (cargar el panel y sus estáticos, la portada de la API,
  la documentación OpenAPI, la comprobación de salud) y además pide el
  catálogo **sin token**, que debe responder 401 rápido (se cuenta como
  correcto: es la respuesta esperada y ejercita la capa de autenticación).
- Si se definen ``LUDOTECA_PROD_EMAIL`` y ``LUDOTECA_PROD_PASSWORD``, cada
  usuario inicia sesión una vez y navega por el catálogo con su token (solo
  lecturas). Úsalo con una cuenta de pruebas tuya.

Uso:

    locust -f tests/estres/locustfile_produccion.py \
        --host https://pps-appweb-26-27-sju7.onrender.com \
        --headless -u 10 -r 1 -t 60s --csv tests/estres/resultados/prod_10

El plan Free de Render tiene 0,1 CPU y se duerme tras 15 min: despiértalo
antes (abre /api/salud) y usa pocos usuarios.
"""
from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

EMAIL = os.getenv("LUDOTECA_PROD_EMAIL")
PASSWORD = os.getenv("LUDOTECA_PROD_PASSWORD")


class VisitanteProduccion(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        self.con_sesion = False
        if EMAIL and PASSWORD:
            r = self.client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
            if r.status_code == 200:
                self.client.headers["Authorization"] = "Bearer " + r.json()["access_token"]
                self.con_sesion = True

    @task(4)
    def pantalla_login(self):
        self.client.get("/panel/login.html")
        self.client.get("/panel/styles.css")
        self.client.get("/panel/auth.js")

    @task(2)
    def panel(self):
        self.client.get("/panel/", name="/panel/")
        self.client.get("/panel/app.js")

    @task(3)
    def salud(self):
        self.client.get("/api/salud")

    @task(1)
    def portada_api(self):
        self.client.get("/")

    @task(1)
    def openapi(self):
        self.client.get("/openapi.json")

    @task(3)
    def catalogo(self):
        if self.con_sesion:
            q = random.choice(["", "?q=zelda", "?genero=RPG", "?orden=titulo-asc"])
            self.client.get(f"/api/videojuegos{q}", name="/api/videojuegos")
        else:
            with self.client.get("/api/videojuegos", name="/api/videojuegos (sin token -> 401)",
                                 catch_response=True) as r:
                if r.status_code == 401:
                    r.success()
                else:
                    r.failure(f"se esperaba 401 y llegó {r.status_code}")
