"""Page Objects del panel "Ludoteca".

Encapsulan los selectores del frontend (``frontend/login.html``,
``frontend/index.html`` y lo que pinta ``frontend/app.js``) para que las
pruebas se lean como pasos de usuario y, si cambia el HTML, solo haya que
tocar este archivo.
"""
from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

ESPERA = 10  # segundos


class Pagina:
    def __init__(self, driver: WebDriver, base_url: str):
        self.driver = driver
        self.base_url = base_url
        self.wait = WebDriverWait(driver, ESPERA)

    def css(self, selector: str):
        return self.driver.find_element(By.CSS_SELECTOR, selector)

    def todos(self, selector: str):
        return self.driver.find_elements(By.CSS_SELECTOR, selector)

    def visible(self, selector: str):
        return self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
        )

    def clicable(self, selector: str):
        return self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))

    def escribir(self, selector: str, texto: str):
        campo = self.visible(selector)
        campo.clear()
        campo.send_keys(texto)
        return campo

    def aceptar_confirm(self):
        """Acepta el ``confirm()`` nativo del navegador."""
        self.wait.until(EC.alert_is_present()).accept()

    def toast_con(self, texto: str):
        """Espera a que aparezca un toast que contenga ``texto``."""
        self.wait.until(
            lambda d: any(texto in t.text for t in d.find_elements(By.CSS_SELECTOR, "#toasts .toast"))
        )

    def local_storage(self, clave: str):
        return self.driver.execute_script("return localStorage.getItem(arguments[0]);", clave)


class PantallaLogin(Pagina):
    RUTA = "/panel/login.html"

    def abrir(self):
        self.driver.get(self.base_url + self.RUTA)
        self.visible("#form-login")
        return self

    def entrar(self, email: str, password: str):
        self.escribir("#form-login input[name=email]", email)
        self.escribir("#form-login input[name=password]", password)
        self.clicable("#form-login button[type=submit]").click()

    def registrar(self, nombre: str, email: str, password: str):
        self.clicable("#tab-registro").click()
        self.visible("#form-registro")
        self.escribir("#form-registro input[name=nombre]", nombre)
        self.escribir("#form-registro input[name=email]", email)
        self.escribir("#form-registro input[name=password]", password)
        self.clicable("#form-registro button[type=submit]").click()

    def aviso(self) -> str:
        return self.visible("#auth-aviso").text


class Panel(Pagina):
    RUTA = "/panel/"

    # ---------- Estado general ----------
    def esperar_cargado(self):
        """Espera a estar en el panel con el catálogo pintado y la API conectada."""
        self.wait.until(EC.url_contains("/panel/"))
        self.wait.until(lambda d: "login" not in d.current_url)
        self.visible("#usuario-chip")
        self.esperar_catalogo()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "pie-estado"), "API conectada"))
        return self

    def esperar_catalogo(self):
        """Espera a que desaparezcan los esqueletos de carga del catálogo."""
        self.wait.until(lambda d: not d.find_elements(By.CSS_SELECTOR, "#grid-catalogo .skeleton"))

    def nombre_usuario(self) -> str:
        return self.css("#usuario-nombre").text

    def rol_usuario(self) -> str:
        # textContent: el CSS lo muestra en mayúsculas (text-transform).
        return self.css("#usuario-rol").get_attribute("textContent").strip()

    def ir_a(self, pestana: str):
        self.clicable(f'.tab[data-tab="{pestana}"]').click()
        self.visible(f"#tab-{pestana}")

    # ---------- Catálogo ----------
    def contador_catalogo(self) -> int:
        self.wait.until(lambda d: d.find_element(By.ID, "contador-catalogo").text.isdigit())
        return int(self.css("#contador-catalogo").text)

    def titulos_catalogo(self) -> list[str]:
        self.esperar_catalogo()
        return [e.text for e in self.todos("#grid-catalogo .card.juego .titulo")]

    def buscar(self, texto: str):
        anterior = self.css("#contador-catalogo").text
        self.escribir("#buscar-catalogo", texto)
        # La búsqueda va con debounce (350 ms): esperamos a que cambie el grid.
        self.wait.until(lambda d: d.find_element(By.ID, "contador-catalogo").text != anterior
                        or d.find_elements(By.CSS_SELECTOR, "#grid-catalogo .skeleton"))
        self.esperar_catalogo()

    def filtrar_genero(self, genero: str):
        self.wait.until(lambda d: len(Select(d.find_element(By.ID, "filtro-genero")).options) > 1)
        Select(self.css("#filtro-genero")).select_by_value(genero)
        self.esperar_catalogo()

    def abrir_ficha(self, titulo: str):
        tarjetas = [c for c in self.todos("#grid-catalogo .card.juego")
                    if c.find_element(By.CSS_SELECTOR, ".titulo").text == titulo]
        assert tarjetas, f"No hay tarjeta para «{titulo}»"
        # La tarjeta entera abre la ficha; se hace click por JS porque el
        # botón "Ver ficha" solo aparece con :hover.
        self.driver.execute_script("arguments[0].click();", tarjetas[0])
        self.visible("#modal-detalle .ficha h2")
        return self.css("#modal-detalle .ficha h2").text

    # ---------- Ficha ----------
    def anadir_a_coleccion(self, estado="bueno", valoracion="9", precio="19.99", favorito=True):
        Select(self.css("#form-anadir select[name=estado]")).select_by_value(estado)
        self.escribir("#form-anadir input[name=valoracion]", valoracion)
        self.escribir("#form-anadir input[name=precio_compra]", precio)
        if favorito:
            self.css("#form-anadir input[name=favorito]").click()
        self.css("#form-anadir button[type=submit]").click()

    # ---------- Colección ----------
    def titulos_coleccion(self) -> list[str]:
        self.wait.until(lambda d: not d.find_elements(By.CSS_SELECTOR, "#grid-coleccion .skeleton"))
        return [e.text for e in self.todos("#grid-coleccion .card.coleccion .titulo")]

    # ---------- Formulario de juego (gestor/admin) ----------
    def crear_juego(self, titulo: str, anio: int, caratula: str, descripcion: str):
        self.clicable("#btn-nuevo").click()
        self.visible("#form-juego")
        self.escribir("#form-juego input[name=titulo]", titulo)
        self.escribir("#form-juego input[name=anio_lanzamiento]", str(anio))
        self.escribir("#form-juego input[name=caratula_url]", caratula)
        self.escribir("#form-juego textarea[name=descripcion]", descripcion)
        # Marca la primera plataforma y el primer género disponibles. El
        # checkbox está oculto por CSS (chip), así que se pulsa su etiqueta.
        self.css('#form-juego label.chip-opt:has(input[name="plataformas_ids"]) span').click()
        self.css('#form-juego label.chip-opt:has(input[name="generos_ids"]) span').click()
        self.css("#form-juego button[type=submit]").click()

    # ---------- Sesión ----------
    def cambiar_password(self, actual: str, nueva: str, confirmar: str | None = None):
        self.clicable("#btn-password").click()
        self.visible("#form-password")
        self.escribir("#form-password input[name=password_actual]", actual)
        self.escribir("#form-password input[name=password_nueva]", nueva)
        self.escribir("#form-password input[name=confirmar]", confirmar or nueva)
        self.css("#form-password button[type=submit]").click()

    def salir(self):
        self.clicable("#btn-salir").click()
        self.aceptar_confirm()
        self.wait.until(EC.url_contains("login.html"))
