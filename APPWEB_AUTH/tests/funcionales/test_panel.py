"""Pruebas funcionales del panel: catálogo, ficha, colección, estadísticas y roles."""
import uuid

from selenium.webdriver.common.by import By

from paginas import Panel


def test_catalogo_muestra_los_juegos(panel_admin: Panel):
    total = panel_admin.contador_catalogo()
    titulos = panel_admin.titulos_catalogo()
    assert total >= 10, "El seed carga 10 juegos de ejemplo"
    assert len(titulos) == min(total, 12)  # 12 por página
    assert "Elden Ring" in titulos or total > 12


def test_busqueda_por_titulo(panel_admin: Panel):
    panel_admin.buscar("mario")
    assert panel_admin.titulos_catalogo() == ["Super Mario Odyssey"]
    assert panel_admin.contador_catalogo() == 1


def test_busqueda_sin_resultados(panel_admin: Panel):
    panel_admin.buscar("zzz-no-existe-zzz")
    assert panel_admin.contador_catalogo() == 0
    assert "No hay juegos" in panel_admin.css("#grid-catalogo").text


def test_filtro_por_genero(panel_admin: Panel):
    panel_admin.filtrar_genero("Metroidvania")
    titulos = panel_admin.titulos_catalogo()
    assert "Hollow Knight" in titulos
    assert "Minecraft" not in titulos


def test_abrir_ficha_de_un_juego(panel_admin: Panel):
    titulo = panel_admin.abrir_ficha("Hades")
    assert titulo == "Hades"
    ficha = panel_admin.css("#modal-detalle .ficha").text
    assert "Supergiant Games" in ficha
    # El admin ve las acciones de gestión dentro de la ficha.
    assert panel_admin.css("#modal-detalle [data-editar]").is_displayed()


def test_usuario_no_ve_acciones_de_gestion_en_la_ficha(panel_usuario: Panel):
    panel_usuario.abrir_ficha("Hades")
    assert not panel_usuario.todos("#modal-detalle [data-editar]")
    assert not panel_usuario.todos("#modal-detalle [data-borrar]")


def test_usuario_anade_un_juego_a_su_coleccion(panel_usuario: Panel):
    panel_usuario.ir_a("coleccion")
    assert panel_usuario.titulos_coleccion() == [], "Una cuenta nueva empieza vacía"

    panel_usuario.ir_a("catalogo")
    panel_usuario.abrir_ficha("Celeste")
    panel_usuario.anadir_a_coleccion(estado="digital", valoracion="10", precio="19.99")
    panel_usuario.toast_con("añadido a tu colección")

    # Tras añadirlo, el panel salta solo a "Mi colección".
    panel_usuario.wait.until(lambda d: "Celeste" in panel_usuario.titulos_coleccion())
    kpis = panel_usuario.css("#coleccion-kpis").text
    assert "19.99 €" in kpis


def test_estadisticas_se_pintan(panel_admin: Panel):
    panel_admin.ir_a("estadisticas")
    panel_admin.wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "#stats-resumen .kpi"))
    assert len(panel_admin.todos("#stats-resumen .kpi")) == 6
    panel_admin.wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "#chart-generos .barra-relleno, #chart-generos *"))
    assert panel_admin.css("#top-valoraciones").text.strip()


def test_admin_ve_la_lista_de_usuarios(panel_admin: Panel):
    panel_admin.ir_a("usuarios")
    panel_admin.wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "#lista-usuarios .fila-usuario"))
    assert "admin@ludoteca.local" in panel_admin.css("#lista-usuarios").text
    assert int(panel_admin.css("#contador-usuarios").text) >= 1


def test_admin_crea_y_elimina_un_juego(panel_admin: Panel):
    titulo = f"Juego Selenium {uuid.uuid4().hex[:6]}"
    panel_admin.crear_juego(
        titulo=titulo, anio=2024,
        caratula="https://placehold.co/600x900?text=Selenium",
        descripcion="Juego creado automáticamente por la prueba funcional.",
    )
    panel_admin.toast_con("Juego creado")

    panel_admin.buscar(titulo)
    assert panel_admin.titulos_catalogo() == [titulo]

    panel_admin.abrir_ficha(titulo)
    panel_admin.clicable("#modal-detalle [data-borrar]").click()
    panel_admin.aceptar_confirm()
    panel_admin.toast_con("Juego eliminado")
    panel_admin.wait.until(lambda d: panel_admin.contador_catalogo() == 0)
