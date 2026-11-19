"""Protección básica frente a abusos y DoS/DDoS de capa de aplicación.

Middleware ASGI (va antes que cualquier endpoint) con tres defensas:

1. **Límite general por IP**: como mucho ``LUDOTECA_LIMITE_GENERAL`` peticiones
   por minuto desde la misma IP (por defecto 300). Frena inundaciones de
   peticiones de un mismo origen.
2. **Límite de autenticación por IP**: como mucho ``LUDOTECA_LIMITE_AUTH``
   intentos por minuto (por defecto 20) a login, registro e inicio con
   Google/GitHub. Son los endpoints más caros (bcrypt) y el objetivo de la
   fuerza bruta de contraseñas.
3. **Tamaño máximo del cuerpo**: peticiones de más de
   ``LUDOTECA_MAX_CUERPO_KB`` (por defecto 1024 KB) se rechazan con 413 sin
   leerlas.

Si se pasa un límite responde **429 Too Many Requests** con la cabecera
``Retry-After`` (segundos que faltan), sin llegar a tocar la base de datos ni
el *threadpool*, así que rechazar es muy barato.

Configuración (variables de entorno, se leen en cada petición):

- ``LUDOTECA_ANTI_DDOS=0`` desactiva todo (por defecto está activo).
- ``LUDOTECA_PROXIES_CONFIABLES``: nº de proxies delante de la app (por
  defecto 0). Con 0 se usa la IP de la conexión y se **ignora**
  ``X-Forwarded-For`` (si no, cualquiera podría falsearla para saltarse el
  límite). Detrás de un proxy (Render) hay que poner 1 (o los saltos que
  haya) para leer la IP real del cliente de esa cabecera.

Limitaciones: los contadores están en memoria de cada proceso (con
``--workers N`` el límite efectivo es N veces mayor) y no sustituyen a una
protección de red (CDN/WAF del hosting) frente a DDoS volumétricos.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque

VENTANA = 60.0  # segundos

RUTAS_AUTH = (
    "/api/auth/login",
    "/api/auth/registro",
    "/api/auth/oauth/",  # .../{proveedor}/login y callback
)


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


def _activo() -> bool:
    return os.getenv("LUDOTECA_ANTI_DDOS", "1").strip().lower() not in ("0", "false", "no")


class _VentanaDeslizante:
    """Cuenta peticiones por clave en el último minuto."""

    def __init__(self):
        self.marcas: dict[str, deque] = {}
        self._ultima_limpieza = time.monotonic()

    def registrar(self, clave: str, limite: int, ahora: float) -> float:
        """Apunta la petición. Devuelve 0 si se permite o los segundos de espera."""
        cola = self.marcas.setdefault(clave, deque())
        while cola and cola[0] <= ahora - VENTANA:
            cola.popleft()
        if len(cola) >= limite:
            return max(1.0, cola[0] + VENTANA - ahora)
        cola.append(ahora)
        self._limpiar(ahora)
        return 0.0

    def _limpiar(self, ahora: float) -> None:
        # Evita que la memoria crezca con IPs que ya no vuelven.
        if ahora - self._ultima_limpieza < VENTANA:
            return
        self._ultima_limpieza = ahora
        for clave in [c for c, q in self.marcas.items() if not q or q[-1] <= ahora - VENTANA]:
            del self.marcas[clave]

    def reiniciar(self) -> None:
        self.marcas.clear()


class AntiDDoS:
    """Middleware ASGI. Uso: ``app.add_middleware(AntiDDoS)``."""

    def __init__(self, app):
        self.app = app
        self.contador = _VentanaDeslizante()

    # --- IP del cliente -------------------------------------------------
    @staticmethod
    def ip_cliente(scope) -> str:
        saltos = _entero("LUDOTECA_PROXIES_CONFIABLES", 0)
        if saltos > 0:
            for nombre, valor in scope.get("headers", []):
                if nombre == b"x-forwarded-for":
                    ips = [p.strip() for p in valor.decode("latin-1").split(",") if p.strip()]
                    if ips:
                        # La IP añadida por el último proxy de confianza.
                        return ips[-saltos] if len(ips) >= saltos else ips[0]
        cliente = scope.get("client")
        return cliente[0] if cliente else "desconocida"

    # --- Respuestas de rechazo ------------------------------------------
    @staticmethod
    async def _responder(send, codigo: int, mensaje: str, espera: float | None = None):
        cuerpo = json.dumps({"detail": mensaje}).encode("utf-8")
        cabeceras = [(b"content-type", b"application/json"),
                     (b"content-length", str(len(cuerpo)).encode())]
        if espera is not None:
            cabeceras.append((b"retry-after", str(math.ceil(espera)).encode()))
        await send({"type": "http.response.start", "status": codigo, "headers": cabeceras})
        await send({"type": "http.response.body", "body": cuerpo})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _activo():
            return await self.app(scope, receive, send)

        # 3. Cuerpo demasiado grande (se mira Content-Length, sin leerlo).
        maximo = _entero("LUDOTECA_MAX_CUERPO_KB", 1024) * 1024
        for nombre, valor in scope.get("headers", []):
            if nombre == b"content-length":
                try:
                    if int(valor) > maximo:
                        return await self._responder(
                            send, 413, f"El cuerpo de la petición supera {maximo // 1024} KB")
                except ValueError:
                    return await self._responder(send, 400, "Content-Length no válido")

        ip = self.ip_cliente(scope)
        ahora = time.monotonic()
        ruta = scope.get("path", "")

        # 2. Autenticación: límite estricto (fuerza bruta, coste de bcrypt).
        if scope.get("method") in ("POST", "GET") and ruta.startswith(RUTAS_AUTH) \
                and not ruta.endswith("/proveedores"):
            espera = self.contador.registrar(f"auth|{ip}", _entero("LUDOTECA_LIMITE_AUTH", 20), ahora)
            if espera:
                return await self._responder(
                    send, 429, "Demasiados intentos de inicio de sesión. Espera un poco.", espera)

        # 1. Límite general por IP.
        espera = self.contador.registrar(f"todo|{ip}", _entero("LUDOTECA_LIMITE_GENERAL", 300), ahora)
        if espera:
            return await self._responder(
                send, 429, "Demasiadas peticiones desde tu conexión. Espera un poco.", espera)

        return await self.app(scope, receive, send)
