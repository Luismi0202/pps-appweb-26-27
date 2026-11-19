"""Pruebas de carga y estrés de la API con Locust.

Simula tres perfiles de usuario que hacen lo mismo que el panel web:

- ``Visitante`` (peso 6): inicia sesión una vez y navega por el catálogo
  (listado, búsqueda, filtros, fichas) y las estadísticas. Es el tráfico
  mayoritario y casi todo lecturas.
- ``Coleccionista`` (peso 3): se registra con una cuenta nueva y gestiona su
  colección (añade, edita, marca favorito, lista y borra ejemplares).
- ``Inicios de sesión`` (peso 1): solo hace login/refresh. El login usa bcrypt,
  que es caro en CPU a propósito, así que este perfil mide el coste de la
  autenticación.

Ejecución con interfaz web (http://localhost:8089):

    locust -f tests/estres/locustfile.py --host http://127.0.0.1:8765

Ejecución sin interfaz (la que se ha usado para el documento):

    locust -f tests/estres/locustfile.py --host http://127.0.0.1:8765 \
        --headless -u 50 -r 5 -t 1m --csv resultados/carga_50

Variables de entorno opcionales: ``LUDOTECA_ADMIN_EMAIL`` y
``LUDOTECA_ADMIN_PASSWORD`` (por defecto, la cuenta de ejemplo del seed).
"""
from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, events, task

ADMIN_EMAIL = os.getenv("LUDOTECA_ADMIN_EMAIL", "admin@ludoteca.local")
ADMIN_PASSWORD = os.getenv("LUDOTECA_ADMIN_PASSWORD", "admin123")

BUSQUEDAS = ["zelda", "mario", "ring", "knight", "god", "witcher", "hades", "celeste"]
GENEROS = ["Acción", "Aventura", "RPG", "Plataformas", "Metroidvania", "Indie"]
PLATAFORMAS = ["PC", "PlayStation 5", "Nintendo Switch", "Steam Deck"]
ESTADOS = ["nuevo", "como nuevo", "bueno", "aceptable", "digital"]

# Ids de juegos del catálogo, se rellenan al arrancar la prueba.
IDS_JUEGOS: list[int] = []


@events.test_start.add_listener
def cargar_catalogo(environment, **_kwargs):
    """Obtiene los ids reales del catálogo antes de lanzar usuarios."""
    import requests

    host = environment.host.rstrip("/")
    r = requests.post(f"{host}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    r.raise_for_status()
    token = r.json()["access_token"]
    datos = requests.get(f"{host}/api/videojuegos?por_pagina=100",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
    IDS_JUEGOS[:] = [j["id"] for j in datos["items"]]
    print(f"[locust] Catálogo con {len(IDS_JUEGOS)} juegos")


class UsuarioAutenticado(HttpUser):
    abstract = True
    wait_time = between(1, 3)  # "tiempo de pensar" entre acciones

    def autenticar(self, respuesta_json):
        self.token = respuesta_json["access_token"]
        self.refresh = respuesta_json["refresh_token"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    def login(self, email, password):
        with self.client.post("/api/auth/login", json={"email": email, "password": password},
                              name="/api/auth/login", catch_response=True) as r:
            if r.status_code == 200:
                self.autenticar(r.json())
                r.success()
            else:
                r.failure(f"login {r.status_code}")


class Visitante(UsuarioAutenticado):
    weight = 6

    def on_start(self):
        self.login(ADMIN_EMAIL, ADMIN_PASSWORD)

    @task(5)
    def listar_catalogo(self):
        pagina = random.choice([1, 1, 1, 2])
        orden = random.choice(["recientes", "titulo-asc", "anio-desc"])
        self.client.get(f"/api/videojuegos?pagina={pagina}&por_pagina=12&orden={orden}",
                        name="/api/videojuegos")

    @task(3)
    def buscar(self):
        self.client.get(f"/api/videojuegos?q={random.choice(BUSQUEDAS)}&por_pagina=12",
                        name="/api/videojuegos?q=")

    @task(2)
    def filtrar(self):
        self.client.get(
            f"/api/videojuegos?genero={random.choice(GENEROS)}"
            f"&plataforma={random.choice(PLATAFORMAS)}&por_pagina=12",
            name="/api/videojuegos?genero&plataforma")

    @task(4)
    def ver_ficha(self):
        if IDS_JUEGOS:
            self.client.get(f"/api/videojuegos/{random.choice(IDS_JUEGOS)}",
                            name="/api/videojuegos/{id}")

    @task(1)
    def filtros_del_panel(self):
        # Lo que pide el panel al cargar (selects de filtros).
        for ruta in ("/api/plataformas", "/api/generos", "/api/desarrolladoras"):
            self.client.get(ruta)

    @task(1)
    def estadisticas(self):
        for ruta in ("resumen", "por-genero", "por-plataforma", "por-estado", "top-valoraciones"):
            self.client.get(f"/api/estadisticas/{ruta}", name="/api/estadisticas/*")

    @task(1)
    def salud(self):
        self.client.get("/api/salud")


class Coleccionista(UsuarioAutenticado):
    weight = 3

    def on_start(self):
        sufijo = uuid.uuid4().hex[:10]
        with self.client.post("/api/auth/registro", name="/api/auth/registro",
                              json={"nombre": f"Carga {sufijo}",
                                    "email": f"carga_{sufijo}@pruebas.test",
                                    "password": "secreto123"},
                              catch_response=True) as r:
            if r.status_code == 201:
                self.autenticar(r.json())
                r.success()
            else:
                r.failure(f"registro {r.status_code}")
        self.mis_items: list[int] = []

    @task(3)
    def anadir_ejemplar(self):
        if not IDS_JUEGOS:
            return
        with self.client.post("/api/colecciones", name="/api/colecciones",
                              json={"videojuego_id": random.choice(IDS_JUEGOS),
                                    "plataforma_id": None,
                                    "estado": random.choice(ESTADOS),
                                    "valoracion": random.randint(1, 10),
                                    "precio_compra": round(random.uniform(5, 70), 2),
                                    "favorito": random.random() < 0.3},
                              catch_response=True) as r:
            if r.status_code == 201:
                self.mis_items.append(r.json()["id"])
            elif r.status_code == 409:
                r.success()  # ya lo tenía: es un resultado de negocio válido

    @task(4)
    def listar_coleccion(self):
        self.client.get("/api/colecciones?por_pagina=12", name="/api/colecciones")

    @task(2)
    def editar_ejemplar(self):
        if self.mis_items:
            self.client.put(f"/api/colecciones/{random.choice(self.mis_items)}",
                            json={"estado": random.choice(ESTADOS), "valoracion": random.randint(1, 10)},
                            name="/api/colecciones/{id}")

    @task(1)
    def favorito(self):
        if self.mis_items:
            self.client.patch(f"/api/colecciones/{random.choice(self.mis_items)}/favorito",
                              json={"favorito": random.random() < 0.5},
                              name="/api/colecciones/{id}/favorito")

    @task(1)
    def borrar_ejemplar(self):
        if self.mis_items:
            item = self.mis_items.pop(random.randrange(len(self.mis_items)))
            self.client.delete(f"/api/colecciones/{item}", name="/api/colecciones/{id}")

    @task(1)
    def resumen(self):
        self.client.get("/api/estadisticas/resumen", name="/api/estadisticas/*")


class InicioSesion(UsuarioAutenticado):
    weight = 1

    @task(3)
    def login_admin(self):
        self.login(ADMIN_EMAIL, ADMIN_PASSWORD)

    @task(1)
    def renovar(self):
        if not getattr(self, "refresh", None):
            return
        with self.client.post("/api/auth/refresh", json={"refresh_token": self.refresh},
                              name="/api/auth/refresh", catch_response=True) as r:
            if r.status_code == 200:
                self.autenticar(r.json())
            else:
                r.failure(f"refresh {r.status_code}")

    @task(1)
    def yo(self):
        if getattr(self, "token", None):
            self.client.get("/api/auth/yo")
