"""Añade datos de prueba de la saga Trails (The Legend of Heroes).

Idempotente: se puede ejecutar tantas veces como se quiera; solo inserta
lo que aún no exista. Uso:

    python -m app.datos_prueba
"""
from datetime import date

from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine, migrar_colecciones
from app.models import (
    Desarrolladora,
    Genero,
    ItemColeccion,
    Plataforma,
    Videojuego,
)
from app.seed import asegurar_admin

FALCOM = {
    "nombre": "Nihon Falcom",
    "pais": "Japón",
    "web": "https://www.falcom.co.jp",
}

GENEROS_NUEVOS = [
    {
        "nombre": "JRPG",
        "descripcion": "Rol japonés: combate por turnos, historia épica y personajes carismáticos.",
    },
]

PLATAFORMAS_NUEVAS = ["PC", "PlayStation 4", "Nintendo Switch", "Steam Deck"]

# (titulo, anio, pegi, puntuacion, plataforma, descripcion)
JUEGOS = [
    (
        "The Legend of Heroes: Trails in the Sky FC",
        2014, "PEGI 12", 8.8, ["PC", "Steam Deck"],
        "Estelle y Joshua Bright, aprendices de brazo divino, recorren el "
        "reino de Liberl en busca del maestro desaparecido. El comienzo de "
        "la saga Trails: un elenco inolvidable, combate por turnos con "
        "movimiento táctico en malla y un mundo que se siente vivo.",
    ),
    (
        "The Legend of Heroes: Trails in the Sky SC",
        2015, "PEGI 12", 9.0, ["PC", "Steam Deck"],
        "La continuación directa de FC, con Estelle al mando de su propia "
        "misión. Amplía el sistema orbal, añade combate aéreo y cierra el "
        "arco de los Bright con uno de los mejores finales de la saga.",
    ),
    (
        "The Legend of Heroes: Trails in the Sky the 3rd",
        2017, "PEGI 12", 8.5, ["PC", "Steam Deck"],
        "Kevin Graham y Ries Argent exploran el Inframundo, un espacio de "
        "recuerdos y secretos. Episodios centrados en personajes secundarios, "
        "mazmorras clásicas y la mitología oculta de la Iglesia.",
    ),
    (
        "The Legend of Heroes: Trails from Zero",
        2022, "PEGI 12", 8.6,
        ["PC", "PlayStation 4", "Nintendo Switch", "Steam Deck"],
        "Lloyd Bannings, detective novato, se integra en la SSS, la unidad "
        "especial de Crossbell, la ciudad-estado atrapada entre Erebonia y "
        "Calvard. Crímenes, conspiración y un equipo que se convierte en familia.",
    ),
    (
        "The Legend of Heroes: Trails to Azure",
        2023, "PEGI 12", 8.9,
        ["PC", "PlayStation 4", "Nintendo Switch", "Steam Deck"],
        "La SSS se enfrenta al Sindicato y a la corrupción endémica de "
        "Crossbell. Combate orbal mejorado con el sistema CB y uno de los "
        "desenlaces más emotivos de toda la serie.",
    ),
    (
        "The Legend of Heroes: Trails of Cold Steel",
        2017, "PEGI 12", 8.6, ["PC", "PlayStation 4"],
        "Rean Schwarzer entra en la recién creada Clase VII de la Academia "
        "Militar de Thors, donde estudiantes nobles y plebeyos aprenden "
        "juntos. Presenta los Panzer Soldat, los mechas orbales de Erebonia.",
    ),
    (
        "The Legend of Heroes: Trails of Cold Steel II",
        2017, "PEGI 12", 8.4, ["PC", "PlayStation 4"],
        "La guerra civil estalla en Erebonia tras el incidente de Thors. "
        "Rean vuelve a casa al mando de su divisa para reunir a sus "
        "compañeros y frenar a quienes quieren quemar el país.",
    ),
    (
        "The Legend of Heroes: Trails of Cold Steel III",
        2019, "PEGI 16", 8.3, ["PC", "PlayStation 4"],
        "Rean regresa como profesor a la Sede de Thors, dirigiendo a la "
        "nueva Clase VII. La tensión con la nobleza crece y los generales "
        "del Trono de Hierro empiezan a mover sus piezas.",
    ),
    (
        "The Legend of Heroes: Trails of Cold Steel IV",
        2020, "PEGI 16", 8.2,
        ["PC", "PlayStation 4", "Nintendo Switch"],
        "El cierre de la Guerra Civil Ereboniana: Clase VII antigua y nueva "
        "se unen para rescatar a Rean y enfrentarse al Emperador Osbourne "
        "y al monstruo que amenaza el continente.",
    ),
    (
        "The Legend of Heroes: Trails into Reverie",
        2023, "PEGI 16", 8.7,
        ["PC", "PlayStation 4", "Nintendo Switch"],
        "Lloyd, Rean y un tercer protagonista inesperado se cruzan en el "
        "Reverie, una máquina que conecta recuerdos. El gran cruce de las "
        "sagas de Crossbell y Erebonia, con contenido extra desbloqueable.",
    ),
    (
        "The Legend of Heroes: Trails through Daybreak",
        2024, "PEGI 16", 8.6,
        ["PC", "PlayStation 4", "Nintendo Switch"],
        "Van Arkride, enlace privado en la república de Calvard, acepta un "
        "caso que lo arrastra a los experimentos con la oscuridad y a los "
        "secretos del nuevo continente. El comienzo de una nueva era.",
    ),
]

# Datos de la colección personal (juego, plataforma, resto de campos)
COLECCION = [
    {
        "titulo": "The Legend of Heroes: Trails in the Sky FC",
        "plataforma": "PC",
        "estado": "digital",
        "fecha_compra": date(2023, 4, 12),
        "precio_compra": 19.99,
        "valoracion": 9,
        "favorito": True,
        "notas": "GOTY en Steam. Empezado por pura recomendación.",
    },
    {
        "titulo": "The Legend of Heroes: Trails from Zero",
        "plataforma": "Nintendo Switch",
        "estado": "bueno",
        "fecha_compra": date(2022, 10, 1),
        "precio_compra": 39.99,
        "valoracion": 8,
        "favorito": False,
        "notas": "Edición física europea.",
    },
    {
        "titulo": "The Legend of Heroes: Trails of Cold Steel",
        "plataforma": "PlayStation 4",
        "estado": "como nuevo",
        "fecha_compra": date(2019, 6, 20),
        "precio_compra": 24.99,
        "valoracion": 9,
        "favorito": False,
        "notas": None,
    },
    {
        "titulo": "The Legend of Heroes: Trails through Daybreak",
        "plataforma": "PC",
        "estado": "digital",
        "fecha_compra": date(2024, 7, 15),
        "precio_compra": 49.99,
        "valoracion": 10,
        "favorito": True,
        "notas": "Estreno en Steam con banda sonora incluida.",
    },
]


def _url_portada(texto: str) -> str:
    limpio = texto.replace(":", "").replace("|", "")
    return (
        "https://placehold.co/600x800/1f2937/f9fafb?text="
        + limpio.replace(" ", "+")
    )


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Asegura el esquema de autenticación y la cuenta admin por defecto.
        admin = asegurar_admin(db)
        migrar_colecciones(admin.id)

        # --- Género JRPG ---------------------------------------------------
        genero_jrpg = db.scalar(
            select(Genero).where(func.lower(Genero.nombre) == "jrpg")
        )
        if genero_jrpg is None:
            genero_jrpg = Genero(**GENEROS_NUEVOS[0])
            db.add(genero_jrpg)
            db.flush()

        genero_rpg = db.scalar(
            select(Genero).where(func.lower(Genero.nombre) == "rpg")
        )

        # --- Desarrolladora ------------------------------------------------
        falcom = db.scalar(
            select(Desarrolladora).where(
                func.lower(Desarrolladora.nombre) == FALCOM["nombre"].lower()
            )
        )
        if falcom is None:
            falcom = Desarrolladora(**FALCOM)
            db.add(falcom)
            db.flush()

        # --- Plataformas ---------------------------------------------------
        plataformas = {}
        for nombre in PLATAFORMAS_NUEVAS:
            plat = db.scalar(
                select(Plataforma).where(
                    func.lower(Plataforma.nombre) == nombre.lower()
                )
            )
            if plat is None:
                plat = Plataforma(nombre=nombre)
                db.add(plat)
                db.flush()
            plataformas[nombre] = plat

        # --- Juegos --------------------------------------------------------
        creados = 0
        juegos = {}
        for titulo, anio, pegi, puntuacion, nombres_plat, descripcion in JUEGOS:
            existente = db.scalar(
                select(Videojuego).where(
                    func.lower(Videojuego.titulo) == titulo.lower()
                )
            )
            if existente is not None:
                juegos[titulo] = existente
                continue

            generos = [genero_jrpg]
            if genero_rpg is not None:
                generos.append(genero_rpg)

            juego = Videojuego(
                titulo=titulo,
                descripcion=descripcion,
                caratula_url=_url_portada(titulo),
                anio_lanzamiento=anio,
                clasificacion=pegi,
                puntuacion=puntuacion,
                desarrolladora=falcom,
                plataformas=[plataformas[n] for n in nombres_plat],
                generos=generos,
            )
            db.add(juego)
            db.flush()
            juegos[titulo] = juego
            creados += 1

        # --- Colección -----------------------------------------------------
        anadidos = 0
        for datos in COLECCION:
            juego = juegos.get(datos["titulo"])
            if juego is None:
                continue
            plat = plataformas.get(datos["plataforma"])
            repetido = db.scalar(
                select(ItemColeccion).where(
                    ItemColeccion.usuario_id == admin.id,
                    ItemColeccion.videojuego_id == juego.id,
                    ItemColeccion.plataforma_id == plat.id,
                )
            )
            if repetido is not None:
                continue
            db.add(
                ItemColeccion(
                    usuario_id=admin.id,
                    videojuego=juego,
                    plataforma=plat,
                    estado=datos["estado"],
                    fecha_compra=datos["fecha_compra"],
                    precio_compra=datos["precio_compra"],
                    valoracion=datos["valoracion"],
                    favorito=datos["favorito"],
                    notas=datos["notas"],
                )
            )
            anadidos += 1

        db.commit()
        print(f"Datos de prueba Trails: {creados} juegos nuevos, "
              f"{anadidos} ejemplares de coleccion nuevos.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
