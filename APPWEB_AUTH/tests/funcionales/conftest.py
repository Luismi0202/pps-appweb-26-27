"""Fixtures de las pruebas funcionales (Selenium + pytest).

- ``base_url``: si existe la variable ``LUDOTECA_BASE_URL`` se prueba contra
  ese servidor (p. ej. el despliegue de Render); si no, se arranca la API en
  un puerto libre con una BD temporal (ver ``tests/servidor_aislado.py``).
- ``navegador``: Chrome (por defecto sin interfaz). ``LUDOTECA_HEADLESS=0``
  abre la ventana para ver la prueba en directo. Selenium Manager descarga
  el chromedriver adecuado automáticamente.
"""
from __future__ import annotations

import os
import socket
import sys
import uuid
from pathlib import Path

import pytest
from selenium import webdriver

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import servidor_aislado  # noqa: E402

from paginas import Panel, PantallaLogin  # noqa: E402

CAPTURAS = Path(__file__).resolve().parent / "capturas"

ADMIN_EMAIL = "admin@ludoteca.local"
ADMIN_PASSWORD = "admin123"


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    externo = os.getenv("LUDOTECA_BASE_URL")
    if externo:
        yield externo.rstrip("/")
        return
    puerto = _puerto_libre()
    proceso, carpeta = servidor_aislado.arrancar(puerto)
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor_aislado.parar(proceso, carpeta)


@pytest.fixture
def navegador(request):
    opciones = webdriver.ChromeOptions()
    if os.getenv("LUDOTECA_HEADLESS", "1") != "0":
        opciones.add_argument("--headless=new")
    opciones.add_argument("--window-size=1366,900")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opciones)
    driver.implicitly_wait(0)
    yield driver
    # Captura de pantalla si la prueba ha fallado (útil en CI).
    informe = getattr(request.node, "rep_call", None)
    if informe is not None and informe.failed:
        CAPTURAS.mkdir(exist_ok=True)
        driver.save_screenshot(str(CAPTURAS / f"{request.node.name}.png"))
    driver.quit()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    resultado = yield
    informe = resultado.get_result()
    setattr(item, f"rep_{informe.when}", informe)


@pytest.fixture
def login(navegador, base_url):
    return PantallaLogin(navegador, base_url)


@pytest.fixture
def panel_admin(login, navegador, base_url) -> Panel:
    """Panel con la sesión del administrador de ejemplo ya iniciada."""
    login.abrir()
    login.entrar(ADMIN_EMAIL, ADMIN_PASSWORD)
    panel = Panel(navegador, base_url)
    panel.esperar_cargado()
    return panel


@pytest.fixture
def credenciales_nuevas():
    """Email/contraseña únicos para registrar una cuenta en cada prueba."""
    sufijo = uuid.uuid4().hex[:8]
    return {
        "nombre": f"Tester {sufijo}",
        "email": f"selenium_{sufijo}@pruebas.test",
        "password": "secreto123",
    }


@pytest.fixture
def panel_usuario(login, navegador, base_url, credenciales_nuevas) -> Panel:
    """Panel con una cuenta nueva de rol ``usuario`` (colección vacía)."""
    login.abrir()
    login.registrar(**credenciales_nuevas)
    panel = Panel(navegador, base_url)
    panel.esperar_cargado()
    return panel
