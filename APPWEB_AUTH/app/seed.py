"""Datos de ejemplo con los que se arranca la API si la BD está vacía."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import (
    ROL_ADMIN,
    Desarrolladora,
    Genero,
    ItemColeccion,
    Plataforma,
    Usuario,
    Videojuego,
)
from app.seguridad import hash_password

# Cuenta por defecto que recibe los datos de ejemplo (cámbiala en producción).
ADMIN_NOMBRE = "admin"
ADMIN_EMAIL = "admin@ludoteca.local"
ADMIN_PASSWORD = "admin123"

PLATAFORMAS = [
    {"nombre": "PC", "fabricante": "Varios", "anio_lanzamiento": 1971},
    {"nombre": "PlayStation 5", "fabricante": "Sony", "anio_lanzamiento": 2020},
    {"nombre": "PlayStation 4", "fabricante": "Sony", "anio_lanzamiento": 2013},
    {"nombre": "Xbox Series X|S", "fabricante": "Microsoft", "anio_lanzamiento": 2020},
    {"nombre": "Nintendo Switch", "fabricante": "Nintendo", "anio_lanzamiento": 2017},
    {"nombre": "Steam Deck", "fabricante": "Valve", "anio_lanzamiento": 2022},
]

GENEROS = [
    {"nombre": "Acción", "descripcion": "Juegos basados en reflejos y combate."},
    {"nombre": "Aventura", "descripcion": "Exploración, narrativa y resolución de puzzles."},
    {"nombre": "RPG", "descripcion": "Juegos de rol con progresión de personajes."},
    {"nombre": "Plataformas", "descripcion": "Saltos y precisión sobre plataformas."},
    {"nombre": "Metroidvania", "descripcion": "Mapas interconectados con exploración gradual."},
    {"nombre": "Indie", "descripcion": "Desarrollados por estudios independientes."},
    {"nombre": "Mundo abierto", "descripcion": "Mapas amplios con libertad de exploración."},
    {"nombre": "Sandbox", "descripcion": "Creatividad y construcción sin objetivos fijos."},
]

DESARROLLADORAS = [
    {"nombre": "FromSoftware", "pais": "Japón", "web": "https://www.fromsoftware.jp"},
    {"nombre": "Nintendo", "pais": "Japón", "web": "https://www.nintendo.com"},
    {"nombre": "Team Cherry", "pais": "Australia", "web": "https://teamcherry.com.au"},
    {"nombre": "CD Projekt Red", "pais": "Polonia", "web": "https://www.cdprojektred.com"},
    {"nombre": "Supergiant Games", "pais": "Estados Unidos", "web": "https://supergiantgames.com"},
    {"nombre": "Rockstar Games", "pais": "Estados Unidos", "web": "https://www.rockstargames.com"},
    {"nombre": "Mojang Studios", "pais": "Suecia", "web": "https://www.mojang.com"},
    {"nombre": "Santa Monica Studio", "pais": "Estados Unidos", "web": "https://sms.playstation.com"},
    {"nombre": "Extremely OK Games", "pais": "Estados Unidos", "web": None},
]

VIDEOJUEGOS = [
    {
        "titulo": "The Legend of Zelda: Breath of the Wild",
        "anio_lanzamiento": 2017,
        "clasificacion": "PEGI 12",
        "puntuacion": 9.7,
        "desarrolladora": "Nintendo",
        "plataformas": ["Nintendo Switch"],
        "generos": ["Aventura", "Mundo abierto"],
        "descripcion": (
            "Explora un Hyrule vasto y salvaje donde cada montaña, ruina y "
            "recoveco esconde un secreto. Sin caminos marcados: crea tu propia "
            "ruta, resuelve los santos a tu manera y derrota a Calamity Ganon. "
            "Una libertad de juego referente en el género de mundo abierto."
        ),
    },
    {
        "titulo": "Elden Ring",
        "anio_lanzamiento": 2022,
        "clasificacion": "PEGI 16",
        "puntuacion": 9.5,
        "desarrolladora": "FromSoftware",
        "plataformas": ["PC", "PlayStation 5", "Xbox Series X|S", "Steam Deck"],
        "generos": ["RPG", "Acción", "Mundo abierto"],
        "descripcion": (
            "Las Tierras Intermedias te esperan en este RPG de acción de mundo "
            "abierto creado junto a George R. R. Martin. Explora, combate a "
            "jefes colosales y forja tu propio camino hasta convertirte en el "
            "Señor Dolorador. Difícil, profundo y adictivo."
        ),
    },
    {
        "titulo": "Hollow Knight",
        "anio_lanzamiento": 2017,
        "clasificacion": "PEGI 12",
        "puntuacion": 9.2,
        "desarrolladora": "Team Cherry",
        "plataformas": ["PC", "Nintendo Switch"],
        "generos": ["Metroidvania", "Indie", "Acción"],
        "descripcion": (
            "Desciende a Hallownest, un reino de insectos en ruinas, en esta "
            "obra maestra del metroidvania. Combate elegante, exploración "
            "interconectada y una atmósfera melancólica que te enganchará "
            "durante decenas de horas."
        ),
    },
    {
        "titulo": "The Witcher 3: Wild Hunt",
        "anio_lanzamiento": 2015,
        "clasificacion": "PEGI 18",
        "puntuacion": 9.6,
        "desarrolladora": "CD Projekt Red",
        "plataformas": ["PC", "PlayStation 4", "Nintendo Switch"],
        "generos": ["RPG", "Mundo abierto", "Acción"],
        "descripcion": (
            "Geralt de Rivia busca a Ciri perseguido por la Cazadora Salvaje "
            "por un continente azotado por la guerra. Un RPG con misiones "
            "secundarias tan cuidadas como la historia principal, decisiones "
            "con consecuencias reales y cientos de horas de contenido."
        ),
    },
    {
        "titulo": "Super Mario Odyssey",
        "anio_lanzamiento": 2017,
        "clasificacion": "PEGI 7",
        "puntuacion": 9.4,
        "desarrolladora": "Nintendo",
        "plataformas": ["Nintendo Switch"],
        "generos": ["Plataformas", "Aventura"],
        "descripcion": (
            "Bowser se lleva a Peach y Mario emprende un viaje por el mundo en "
            "la Odyssey. Con tu gorra viviente Cappy podrás poseer a casi "
            "cualquier cosa: un cañón, un tiranosaurio o una bomba. Plataformeo "
            "puro con más de 800 lunas que recolectar."
        ),
    },
    {
        "titulo": "Hades",
        "anio_lanzamiento": 2020,
        "clasificacion": "PEGI 12",
        "puntuacion": 9.3,
        "desarrolladora": "Supergiant Games",
        "plataformas": ["PC", "Nintendo Switch", "Steam Deck"],
        "generos": ["Indie", "Acción", "RPG"],
        "descripcion": (
            "Zagreo intenta escapar del Inframundo en este roguelike de acción "
            "donde cada intento muerte avanza la historia. Combate frenético, "
            "dioses que te otorgan poderes divinos y un arte rotundo. El "
            "mejor roguelike de su generación."
        ),
    },
    {
        "titulo": "Red Dead Redemption 2",
        "anio_lanzamiento": 2018,
        "clasificacion": "PEGI 18",
        "puntuacion": 9.5,
        "desarrolladora": "Rockstar Games",
        "plataformas": ["PlayStation 4", "PC", "Xbox Series X|S"],
        "generos": ["Mundo abierto", "Acción", "Aventura"],
        "descripcion": (
            "1899: el fuera de la ley Arthur Morgan y la banda de Van der Linde "
            "huyen por el Oeste americano. Un mundo abierto de detalle "
            "obsesivo con una historia emocionante, cacerías, duelos y un "
            "modo en línea con misiones compartidas."
        ),
    },
    {
        "titulo": "Minecraft",
        "anio_lanzamiento": 2011,
        "clasificacion": "PEGI 7",
        "puntuacion": 9.0,
        "desarrolladora": "Mojang Studios",
        "plataformas": ["PC", "Nintendo Switch", "PlayStation 4"],
        "generos": ["Sandbox", "Indie", "Aventura"],
        "descripcion": (
            "El juego de supervivencia y construcción más vendido de la "
            "historia. Rompe bloques, crea objetos, explora biomas infinitos "
            "y sobrevive a las noches en solitario o con amigos en multijugador. "
            "Tu único límite es tu imaginación."
        ),
    },
    {
        "titulo": "Celeste",
        "anio_lanzamiento": 2018,
        "clasificacion": "PEGI 7",
        "puntuacion": 9.1,
        "desarrolladora": "Extremely OK Games",
        "plataformas": ["PC", "Nintendo Switch"],
        "generos": ["Plataformas", "Indie"],
        "descripcion": (
            "Madeline sube a la montaña Celeste con una historia sobre ansiedad "
            "y superación personal. Plataformeo preciso con salto, derrape y "
            "remonte, cientos de búsquedas opcionales y un modo assist para "
            "jugarlo a tu ritmo."
        ),
    },
    {
        "titulo": "God of War",
        "anio_lanzamiento": 2018,
        "clasificacion": "PEGI 18",
        "puntuacion": 9.4,
        "desarrolladora": "Santa Monica Studio",
        "plataformas": ["PlayStation 4", "PC"],
        "generos": ["Acción", "Aventura"],
        "descripcion": (
            "Kratos y su hijo Atreus emprenden un viaje por la mitología "
            "nórdica para esparcir las cenizas de su esposa. Combate brutal con "
            "el hacha Leviatán, cámaras planca sin cortes y una de las mejores "
            "relaciones padre-hijo de los videojuegos."
        ),
    },
]

COLECCION = [
    {
        "titulo": "The Legend of Zelda: Breath of the Wild",
        "plataforma": "Nintendo Switch",
        "estado": "bueno",
        "fecha_compra": "2018-03-03",
        "precio_compra": 54.99,
        "valoracion": 10,
        "favorito": True,
        "notas": "Edición física con caja. 120 santos completados.",
    },
    {
        "titulo": "Elden Ring",
        "plataforma": "PlayStation 5",
        "estado": "como nuevo",
        "fecha_compra": "2022-03-05",
        "precio_compra": 69.99,
        "valoracion": 10,
        "favorito": True,
        "notas": "Platinum desbloqueado. Expansiones pendientes.",
    },
    {
        "titulo": "Hollow Knight",
        "plataforma": "PC",
        "estado": "digital",
        "fecha_compra": "2020-12-26",
        "precio_compra": 14.99,
        "valoracion": 9,
        "favorito": True,
        "notas": "Comprado en oferta de Steam.",
    },
    {
        "titulo": "The Witcher 3: Wild Hunt",
        "plataforma": "Nintendo Switch",
        "estado": "bueno",
        "fecha_compra": "2021-07-15",
        "precio_compra": 29.99,
        "valoracion": 9,
        "favorito": False,
        "notas": "Cartucho con guía de 100 páginas.",
    },
    {
        "titulo": "Super Mario Odyssey",
        "plataforma": "Nintendo Switch",
        "estado": "bueno",
        "fecha_compra": "2019-11-28",
        "precio_compra": 49.99,
        "valoracion": 8,
        "favorito": False,
        "notas": None,
    },
    {
        "titulo": "God of War",
        "plataforma": "PC",
        "estado": "digital",
        "fecha_compra": "2023-01-19",
        "precio_compra": 59.99,
        "valoracion": 9,
        "favorito": False,
        "notas": "Steam, gráficos en máximo.",
    },
]


def asegurar_admin(db: Session) -> Usuario:
    """Devuelve (creándola si hace falta) la cuenta admin por defecto.

    Es la propietaria de los datos de ejemplo y de los ejemplares antiguos.
    """
    admin = db.scalar(select(Usuario).where(Usuario.email == ADMIN_EMAIL))
    if admin is None:
        admin = Usuario(
            nombre=ADMIN_NOMBRE,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            rol=ROL_ADMIN,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    elif admin.rol != ROL_ADMIN:
        # BD anterior al sistema de roles: la cuenta admin conserva sus permisos.
        admin.rol = ROL_ADMIN
        db.commit()
        db.refresh(admin)
    return admin


def asignar_huerfanos(db: Session, admin: Usuario) -> int:
    """Asigna a la cuenta admin los ejemplares que no tienen dueño."""
    resultado = db.execute(
        update(ItemColeccion)
        .where(ItemColeccion.usuario_id.is_(None))
        .values(usuario_id=admin.id)
    )
    db.commit()
    return resultado.rowcount or 0


def seed_si_vacio(db: Session, admin: Usuario | None = None) -> None:
    """Carga los datos de ejemplo solo si la tabla de videojuegos está vacía."""
    hay_datos = db.scalar(select(func.count()).select_from(Videojuego))
    if hay_datos:
        return

    if admin is None:
        admin = asegurar_admin(db)
    plataformas = {}
    for datos in PLATAFORMAS:
        obj = Plataforma(**datos)
        db.add(obj)
        plataformas[datos["nombre"]] = obj

    generos = {}
    for datos in GENEROS:
        obj = Genero(**datos)
        db.add(obj)
        generos[datos["nombre"]] = obj

    desarrolladoras = {}
    for datos in DESARROLLADORAS:
        obj = Desarrolladora(**datos)
        db.add(obj)
        desarrolladoras[datos["nombre"]] = obj

    db.flush()  # para obtener los IDs

    videojuegos = {}
    for datos in VIDEOJUEGOS:
        obj = Videojuego(
            titulo=datos["titulo"],
            descripcion=datos["descripcion"],
            caratula_url=(
                "https://placehold.co/600x800/1f2937/f9fafb?text="
                + datos["titulo"].replace(" ", "+").replace(":", "")
            ),
            anio_lanzamiento=datos["anio_lanzamiento"],
            clasificacion=datos["clasificacion"],
            puntuacion=datos["puntuacion"],
            desarrolladora=desarrolladoras.get(datos["desarrolladora"]),
            plataformas=[plataformas[n] for n in datos["plataformas"]],
            generos=[generos[n] for n in datos["generos"]],
        )
        db.add(obj)
        videojuegos[datos["titulo"]] = obj

    db.flush()

    from datetime import date

    for datos in COLECCION:
        db.add(
            ItemColeccion(
                usuario_id=admin.id,
                videojuego=videojuegos[datos["titulo"]],
                plataforma=plataformas[datos["plataforma"]],
                estado=datos["estado"],
                fecha_compra=date.fromisoformat(datos["fecha_compra"]),
                precio_compra=datos["precio_compra"],
                valoracion=datos["valoracion"],
                favorito=datos["favorito"],
                notas=datos["notas"],
            )
        )

    db.commit()
