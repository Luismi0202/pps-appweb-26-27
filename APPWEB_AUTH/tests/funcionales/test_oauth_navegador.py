"""Pruebas Selenium de la parte de navegador del login con Google/GitHub.

El viaje a Google/GitHub no se puede automatizar sin cuentas reales, así que
se prueba lo que pasa en NUESTRA página:

- los botones aparecen solo si el proveedor está configurado y apuntan a la API;
- al volver de la API con ``#oauth=<tokens>`` el panel arranca con sesión;
- al volver con ``#oauth_error=...`` se muestra el aviso.

(El intercambio con el proveedor se prueba en ``tests/oauth/test_oauth.py``.)
"""
import base64
import json
import os
import socket
import urllib.parse
import urllib.request

import pytest
import servidor_aislado
from selenium.webdriver.support import expected_conditions as EC

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from paginas import Panel, PantallaLogin


def _login_api(base_url):
    peticion = urllib.request.Request(
        base_url + "/api/auth/login",
        data=json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(peticion) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def url_con_proveedores():
    """Segundo servidor aislado con Google y GitHub configurados (ids falsos)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    claves = {"GOOGLE_CLIENT_ID": "id-g", "GOOGLE_CLIENT_SECRET": "s-g",
              "GITHUB_CLIENT_ID": "id-gh", "GITHUB_CLIENT_SECRET": "s-gh"}
    os.environ.update(claves)
    try:
        proceso, carpeta = servidor_aislado.arrancar(puerto)
    finally:
        for c in claves:
            os.environ.pop(c, None)
    yield f"http://127.0.0.1:{puerto}"
    servidor_aislado.parar(proceso, carpeta)


def test_sin_proveedores_no_se_ven_los_botones(login, base_url):
    if os.getenv("LUDOTECA_BASE_URL"):
        pytest.skip("Depende de la configuración del servidor remoto")
    login.abrir()
    login.wait.until(lambda d: d.execute_script(
        "return document.readyState === 'complete'"))
    assert not login.css("#auth-social").is_displayed()
    # El login de siempre sigue ahí.
    assert login.css("#form-login").is_displayed()


def test_con_proveedores_aparecen_los_botones(navegador, url_con_proveedores):
    login = PantallaLogin(navegador, url_con_proveedores).abrir()
    login.visible("#auth-social")
    google = login.visible("#btn-oauth-google")
    github = login.visible("#btn-oauth-github")
    assert google.get_attribute("href") == url_con_proveedores + "/api/auth/oauth/google/login"
    assert github.get_attribute("href") == url_con_proveedores + "/api/auth/oauth/github/login"
    # Visibles también en la pestaña "Crear cuenta": sirven para registrarse.
    login.clicable("#tab-registro").click()
    assert login.css("#btn-oauth-github").is_displayed()


def test_el_boton_lleva_a_github(navegador, url_con_proveedores):
    """El enlace llega a la API, que redirige al formulario de GitHub."""
    destino = {}

    class SinSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            destino["url"] = newurl
            return None

    abridor = urllib.request.build_opener(SinSeguir)
    try:
        abridor.open(url_con_proveedores + "/api/auth/oauth/github/login")
    except urllib.error.HTTPError as e:
        assert e.code == 307
    url = urllib.parse.urlparse(destino["url"])
    assert url.netloc == "github.com" and url.path == "/login/oauth/authorize"
    assert dict(urllib.parse.parse_qsl(url.query))["client_id"] == "id-gh"


def test_vuelta_con_tokens_entra_al_panel(navegador, base_url):
    sesion = _login_api(base_url)  # mismos tokens que emite el callback
    carga = base64.urlsafe_b64encode(json.dumps(sesion).encode()).decode().rstrip("=")
    navegador.get(f"{base_url}/panel/login.html#oauth={carga}")

    panel = Panel(navegador, base_url).esperar_cargado()
    assert panel.nombre_usuario() == "admin"
    assert "#oauth" not in navegador.current_url  # los tokens no se quedan en la URL
    assert panel.local_storage("ludoteca_token") == sesion["access_token"]
    assert panel.local_storage("ludoteca_refresh") == sesion["refresh_token"]


def test_vuelta_con_error_muestra_aviso(navegador, base_url):
    mensaje = "Tu cuenta de GitHub no tiene un email verificado."
    navegador.get(f"{base_url}/panel/login.html#oauth_error={urllib.parse.quote(mensaje)}")
    login = PantallaLogin(navegador, base_url)
    assert login.aviso() == mensaje
    login.wait.until(lambda d: "#" not in d.current_url)
    assert login.local_storage("ludoteca_token") is None
    login.wait.until(EC.visibility_of_element_located(("css selector", "#form-login")))
