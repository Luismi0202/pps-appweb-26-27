"""Modelos ORM de la base de datos de la colección de videojuegos."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ---------------------------------------------------------------------------
# Tablas intermedias (relaciones muchos-a-muchos)
# ---------------------------------------------------------------------------
videojuego_plataforma = Table(
    "videojuego_plataforma",
    Base.metadata,
    Column(
        "videojuego_id",
        ForeignKey("videojuegos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "plataforma_id",
        ForeignKey("plataformas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

videojuego_genero = Table(
    "videojuego_genero",
    Base.metadata,
    Column(
        "videojuego_id",
        ForeignKey("videojuegos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genero_id",
        ForeignKey("generos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ---------------------------------------------------------------------------
# Usuarios (autenticación con JWT) y roles de la plataforma
# ---------------------------------------------------------------------------
ROL_USUARIO = "usuario"
ROL_GESTOR = "gestor"
ROL_ADMIN = "admin"
ROLES = (ROL_USUARIO, ROL_GESTOR, ROL_ADMIN)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(
        String(16), default=ROL_USUARIO, server_default=ROL_USUARIO
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Versión de los tokens JWT: cada cambio de contraseña la incrementa y
    # anula todos los tokens emitidos antes (las sesiones abiertas mueren).
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Borrar la cuenta arrastra sus ejemplares, igual que el videojuego
    # arrastra los suyos (la columna usuario_id también es CASCADE en la BD).
    items: Mapped[list["ItemColeccion"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )

    # --- Permisos (calculados a partir del rol) ---------------------------
    @property
    def es_admin(self) -> bool:
        """Compatibilidad: el antiguo booleano es_admin equivale a rol admin."""
        return self.rol == ROL_ADMIN

    @property
    def puede_gestionar(self) -> bool:
        """Gestores y administradores pueden tocar el catálogo."""
        return self.rol in (ROL_GESTOR, ROL_ADMIN)


# ---------------------------------------------------------------------------
# Desarrolladoras / editoras
# ---------------------------------------------------------------------------
class Desarrolladora(Base):
    __tablename__ = "desarrolladoras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    pais: Mapped[str | None] = mapped_column(String(80))
    web: Mapped[str | None] = mapped_column(String(255))

    videojuegos: Mapped[list["Videojuego"]] = relationship(
        back_populates="desarrolladora"
    )


# ---------------------------------------------------------------------------
# Plataformas
# ---------------------------------------------------------------------------
class Plataforma(Base):
    __tablename__ = "plataformas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    fabricante: Mapped[str | None] = mapped_column(String(100))
    anio_lanzamiento: Mapped[int | None] = mapped_column(Integer)

    videojuegos: Mapped[list["Videojuego"]] = relationship(
        secondary=videojuego_plataforma, back_populates="plataformas"
    )


# ---------------------------------------------------------------------------
# Géneros
# ---------------------------------------------------------------------------
class Genero(Base):
    __tablename__ = "generos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    descripcion: Mapped[str | None] = mapped_column(Text)

    videojuegos: Mapped[list["Videojuego"]] = relationship(
        secondary=videojuego_genero, back_populates="generos"
    )


# ---------------------------------------------------------------------------
# Videojuegos (el núcleo de la API)
# ---------------------------------------------------------------------------
class Videojuego(Base):
    __tablename__ = "videojuegos"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200), index=True)
    descripcion: Mapped[str] = mapped_column(Text)
    caratula_url: Mapped[str] = mapped_column(String(500))
    anio_lanzamiento: Mapped[int] = mapped_column(Integer, index=True)
    clasificacion: Mapped[str | None] = mapped_column(String(20))  # PEGI
    puntuacion: Mapped[float | None] = mapped_column(Float)  # media 0-10
    desarrolladora_id: Mapped[int | None] = mapped_column(
        ForeignKey("desarrolladoras.id", ondelete="SET NULL")
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    desarrolladora: Mapped[Desarrolladora | None] = relationship(
        back_populates="videojuegos"
    )
    plataformas: Mapped[list[Plataforma]] = relationship(
        secondary=videojuego_plataforma, back_populates="videojuegos"
    )
    generos: Mapped[list[Genero]] = relationship(
        secondary=videojuego_genero, back_populates="videojuegos"
    )
    colecciones: Mapped[list["ItemColeccion"]] = relationship(
        back_populates="videojuego", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Colección personal (ejemplares que posee el usuario)
# ---------------------------------------------------------------------------
class ItemColeccion(Base):
    __tablename__ = "colecciones"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "videojuego_id",
            "plataforma_id",
            name="uq_coleccion_usuario_juego_plataforma",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    videojuego_id: Mapped[int] = mapped_column(
        ForeignKey("videojuegos.id", ondelete="CASCADE"), index=True
    )
    plataforma_id: Mapped[int | None] = mapped_column(
        ForeignKey("plataformas.id", ondelete="SET NULL"), nullable=True
    )
    estado: Mapped[str] = mapped_column(String(30), default="bueno")
    fecha_compra: Mapped[date | None] = mapped_column(Date)
    precio_compra: Mapped[float | None] = mapped_column(Float)
    valoracion: Mapped[int | None] = mapped_column(Integer)  # 1-10
    favorito: Mapped[bool] = mapped_column(Boolean, default=False)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_adicion: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    videojuego: Mapped[Videojuego] = relationship(back_populates="colecciones")
    plataforma: Mapped[Plataforma | None] = relationship()
    usuario: Mapped[Usuario] = relationship(back_populates="items")
