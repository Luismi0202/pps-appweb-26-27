"""Pruebas funcionales de la pantalla de acceso (login / registro / sesión)."""
from selenium.webdriver.support import expected_conditions as EC

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from paginas import Panel, PantallaLogin


def test_panel_sin_sesion_redirige_al_login(navegador, base_url):
    navegador.get(base_url + "/panel/")
    PantallaLogin(navegador, base_url).wait.until(EC.url_contains("/panel/login.html"))
    assert "Entrar" in navegador.title


def test_login_con_password_incorrecta_muestra_error(login, navegador):
    login.abrir()
    login.entrar(ADMIN_EMAIL, "esta-no-es")
    assert login.aviso(), "Debe mostrarse un aviso de error"
    assert "login.html" in navegador.current_url
    assert login.local_storage("ludoteca_token") is None


def test_login_admin_entra_al_panel_con_permisos(panel_admin: Panel):
    assert panel_admin.nombre_usuario() == "admin"
    assert panel_admin.rol_usuario() == "Administrador"
    # Un admin ve el botón de crear juegos y la pestaña de usuarios.
    assert panel_admin.css("#btn-nuevo").is_displayed()
    assert panel_admin.css("#tab-btn-usuarios").is_displayed()
    # Se guardan el access token y el refresh token (JWT con 3 partes).
    assert panel_admin.local_storage("ludoteca_token").count(".") == 2
    assert panel_admin.local_storage("ludoteca_refresh").count(".") == 2


def test_registro_crea_cuenta_con_rol_usuario(panel_usuario: Panel, credenciales_nuevas):
    assert panel_usuario.nombre_usuario() == credenciales_nuevas["nombre"]
    assert panel_usuario.rol_usuario() == "Usuario"
    # Un usuario normal NO puede gestionar el catálogo ni ver las cuentas.
    assert not panel_usuario.css("#btn-nuevo").is_displayed()
    assert not panel_usuario.css("#tab-btn-usuarios").is_displayed()


def test_registro_con_email_duplicado_muestra_error(login):
    login.abrir()
    login.registrar("Otro admin", ADMIN_EMAIL, "secreto123")
    assert login.aviso(), "Debe avisar de que el email ya existe"


def test_cerrar_sesion_borra_tokens(panel_admin: Panel):
    panel_admin.salir()
    assert panel_admin.local_storage("ludoteca_token") is None
    assert panel_admin.local_storage("ludoteca_refresh") is None


def test_cambiar_password_y_volver_a_entrar(panel_usuario: Panel, credenciales_nuevas, navegador, base_url):
    nueva = "otraClave456"
    panel_usuario.cambiar_password(credenciales_nuevas["password"], nueva)
    panel_usuario.toast_con("Contraseña actualizada")
    panel_usuario.salir()

    login = PantallaLogin(navegador, base_url)
    login.abrir()
    login.entrar(credenciales_nuevas["email"], credenciales_nuevas["password"])
    assert login.aviso(), "La contraseña antigua ya no debe servir"

    login.entrar(credenciales_nuevas["email"], nueva)
    Panel(navegador, base_url).esperar_cargado()


def test_cambiar_password_sin_coincidir_no_envia(panel_usuario: Panel):
    panel_usuario.cambiar_password("secreto123", "nueva12345", confirmar="distinta999")
    panel_usuario.toast_con("no coinciden")
    assert panel_usuario.css("#modal-password").is_displayed()
