"""Levanta la API en un directorio temporal para no tocar la BD del repositorio.

La aplicación usa ``sqlite:///./coleccion_videojuegos.db`` (ruta relativa al
directorio de trabajo), así que basta con arrancar Uvicorn desde una carpeta
temporal: la BD se crea allí desde cero con los datos de ejemplo (seed) y el
``coleccion_videojuegos.db`` versionado en Git queda intacto.

Uso directo (por ejemplo, antes de lanzar Locust):

    python tests/servidor_aislado.py --port 8765 [--workers 1]

Lo usan también las pruebas funcionales (``tests/funcionales/conftest.py``).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parent.parent  # .../APPWEB_AUTH


def esperar_salud(base_url: str, timeout: float = 30.0) -> None:
    """Espera a que ``/api/salud`` responda 200 o lanza ``RuntimeError``."""
    limite = time.monotonic() + timeout
    ultimo_error: Exception | None = None
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(base_url + "/api/salud", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception as e:  # noqa: BLE001 - aún arrancando
            ultimo_error = e
        time.sleep(0.3)
    raise RuntimeError(f"La API no respondió en {timeout}s: {ultimo_error}")


def _inicializar_bd(carpeta: str) -> None:
    """Crea la BD con el seed ejecutando el arranque (lifespan) de la app."""
    codigo = (
        "import asyncio, sys; sys.path.insert(0, sys.argv[1]);"
        "from app.main import app, lifespan\n"
        "async def f():\n"
        "    async with lifespan(app): pass\n"
        "asyncio.run(f())"
    )
    subprocess.run([sys.executable, "-c", codigo, str(RAIZ_APP)], cwd=carpeta, check=True)


def arrancar(port: int, workers: int = 1, log=None, anti_ddos: bool = False,
             limit_concurrency: int | None = None, proxies: int = 0):
    """Arranca Uvicorn en una carpeta temporal. Devuelve ``(proceso, carpeta)``.

    - ``anti_ddos``: activa los límites por IP de ``app/anti_ddos.py``. Por
      defecto se desactivan, porque las pruebas de carga lanzan cientos de
      usuarios desde la misma IP (127.0.0.1) y se bloquearían.
    - ``limit_concurrency``: máximo de conexiones a la vez (Uvicorn responde
      503 al resto en vez de encolarlas).
    - ``proxies``: valor de ``LUDOTECA_PROXIES_CONFIABLES`` (para simular
      IPs distintas con ``X-Forwarded-For`` en las pruebas anti-DDoS).
    """
    carpeta = tempfile.mkdtemp(prefix="ludoteca_pruebas_")
    if workers > 1:
        # Con varios procesos y la BD vacía, todos ejecutan el seed a la vez y
        # chocan creando la cuenta admin (UNIQUE constraint failed). Se crea
        # la BD primero con un único proceso y luego se arranca con N.
        _inicializar_bd(carpeta)
    comando = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--app-dir", str(RAIZ_APP),
        "--host", "127.0.0.1", "--port", str(port),
        "--workers", str(workers),
        "--log-level", "warning",
    ]
    if limit_concurrency:
        comando += ["--limit-concurrency", str(limit_concurrency)]
    entorno = dict(os.environ)
    entorno.setdefault("LUDOTECA_SECRET_KEY", "clave-solo-para-pruebas-automaticas")
    entorno["LUDOTECA_ANTI_DDOS"] = "1" if anti_ddos else "0"
    entorno["LUDOTECA_PROXIES_CONFIABLES"] = str(proxies)
    proceso = subprocess.Popen(
        comando, cwd=carpeta, env=entorno,
        stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        esperar_salud(f"http://127.0.0.1:{port}")
    except Exception:
        parar(proceso, carpeta)
        raise
    return proceso, carpeta


def parar(proceso, carpeta) -> None:
    proceso.terminate()
    try:
        proceso.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proceso.kill()
    shutil.rmtree(carpeta, ignore_errors=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--anti-ddos", action="store_true",
                   help="activa los límites por IP (app/anti_ddos.py)")
    p.add_argument("--limit-concurrency", type=int, default=None,
                   help="máx. conexiones simultáneas; Uvicorn responde 503 al resto")
    p.add_argument("--proxies", type=int, default=0,
                   help="LUDOTECA_PROXIES_CONFIABLES (1 = fiarse de X-Forwarded-For)")
    args = p.parse_args()
    proceso, carpeta = arrancar(args.port, args.workers, log=sys.stdout,
                                anti_ddos=args.anti_ddos,
                                limit_concurrency=args.limit_concurrency,
                                proxies=args.proxies)
    print(f"API de pruebas en http://127.0.0.1:{args.port}  (BD en {carpeta})")
    print("Ctrl+C para pararla y borrar la BD temporal.")
    try:
        proceso.wait()
    except KeyboardInterrupt:
        pass
    finally:
        parar(proceso, carpeta)


if __name__ == "__main__":
    main()
