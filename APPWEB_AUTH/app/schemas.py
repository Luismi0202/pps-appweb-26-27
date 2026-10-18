"""Esquemas Pydantic: validación de entrada y documentación de salida."""
import math
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
class UsuarioCrear(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=50, examples=["Maic"])
    email: str = Field(..., max_length=150, examples=["maic@ejemplo.com"])
    password: str = Field(..., min_length=6, max_length=72, examples=["secreto123"])

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1] or v.startswith("@"):
            raise ValueError("email no válido")
        return v

    @field_validator("nombre")
    @classmethod
    def _nombre_limpio(cls, v: str) -> str:
        return v.strip()


class UsuarioLogin(BaseModel):
    email: str = Field(..., examples=["maic@ejemplo.com"])
    password: str = Field(..., examples=["secreto123"])


class UsuarioSalida(BaseModel):
    id: int
    nombre: str
    email: str
    rol: Literal["usuario", "gestor", "admin"] = "usuario"
    es_admin: bool = False
    activo: bool
    fecha_registro: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RolActualizar(BaseModel):
    """Cambio de rol desde la pestaña de administración (solo admin)."""

    rol: Literal["usuario", "gestor", "admin"] = Field(
        ..., description="Nuevo rol de la cuenta"
    )


class PasswordCambio(BaseModel):
    """Cambio de la contraseña propia (cualquier rol, con la actual).

    POST /api/auth/cambiar-password: exige la contraseña actual para que un
    token robado no baste con «cambiarte» la clave. Al confirmar se anulan
    todos los tokens emitidos hasta ese momento.
    """

    password_actual: str = Field(
        ..., max_length=72, examples=["secreto123"],
        description="Contraseña vigente de la cuenta",
    )
    password_nueva: str = Field(
        ..., min_length=6, max_length=72, examples=["clave-nueva-123"],
        description="Nueva contraseña (mínimo 6 caracteres, como en el registro)",
    )
    confirmar: str = Field(
        ..., min_length=6, max_length=72, examples=["clave-nueva-123"],
        description="Repetición de la contraseña nueva",
    )

    @model_validator(mode="after")
    def _coinciden_y_cambia(self) -> "PasswordCambio":
        if self.confirmar != self.password_nueva:
            raise ValueError("La confirmación no coincide con la contraseña nueva")
        if self.password_nueva == self.password_actual:
            raise ValueError("La contraseña nueva debe ser distinta de la actual")
        return self


class PasswordRestablecer(BaseModel):
    """Contraseña nueva que un admin asigna a otra cuenta (solo admin).

    PATCH /api/usuarios/{id}/password: el administrador no necesita conocer
    la contraseña anterior (es un proceso de recuperación), pero al guardarla
    se anulan los tokens de esa cuenta: sus sesiones abiertas mueren.
    """

    password_nueva: str = Field(
        ..., min_length=6, max_length=72, examples=["recuperada-123"],
        description="Nueva contraseña para la cuenta (mínimo 6 caracteres)",
    )
    confirmar: str = Field(
        ..., min_length=6, max_length=72, examples=["recuperada-123"],
        description="Repetición de la contraseña nueva",
    )

    @model_validator(mode="after")
    def _coinciden(self) -> "PasswordRestablecer":
        if self.confirmar != self.password_nueva:
            raise ValueError("La confirmación no coincide con la contraseña nueva")
        return self


class PaginaUsuarios(BaseModel):
    """Respuesta paginada del listado de usuarios (solo admin)."""

    total: int
    pagina: int
    por_pagina: int
    paginas: int
    items: list[UsuarioSalida]

    @classmethod
    def crear(cls, total: int, pagina: int, por_pagina: int, items: list):
        paginas = max(1, math.ceil(total / por_pagina))
        return cls(
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
            paginas=paginas,
            items=items,
        )


class TokenSalida(BaseModel):
    access_token: str
    refresh_token: str = Field(
        ..., description="Token largo para renovar la sesión (POST /api/auth/refresh)"
    )
    token_type: str = "bearer"
    expira_en_segundos: int = Field(..., description="Validez del token")
    refresh_expira_en_segundos: Optional[int] = Field(
        None, description="Validez del refresh token"
    )
    usuario: UsuarioSalida


class TokenRefresco(BaseModel):
    """Cuerpo de POST /api/auth/refresh: renueva la sesión con el refresh token."""

    refresh_token: str = Field(..., examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6..."])


# ---------------------------------------------------------------------------
# Estados posibles de un ejemplar de la colección
# ---------------------------------------------------------------------------
EstadoColeccion = Literal[
    "nuevo", "como nuevo", "bueno", "aceptable", "malo", "digital"
]

# ---------------------------------------------------------------------------
# Plataformas
# ---------------------------------------------------------------------------
class PlataformaBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100,
                        examples=["Nintendo Switch"])
    fabricante: Optional[str] = Field(None, max_length=100,
                                      examples=["Nintendo"])
    anio_lanzamiento: Optional[int] = Field(None, ge=1970, le=2035,
                                            examples=[2017])


class PlataformaCrear(PlataformaBase):
    pass


class PlataformaActualizar(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    fabricante: Optional[str] = Field(None, max_length=100)
    anio_lanzamiento: Optional[int] = Field(None, ge=1970, le=2035)


class PlataformaSalida(PlataformaBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Géneros
# ---------------------------------------------------------------------------
class GeneroBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80,
                        examples=["RPG"])
    descripcion: Optional[str] = Field(None, max_length=1000)


class GeneroCrear(GeneroBase):
    pass


class GeneroActualizar(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=1000)


class GeneroSalida(GeneroBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Desarrolladoras
# ---------------------------------------------------------------------------
class DesarrolladoraBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120,
                        examples=["FromSoftware"])
    pais: Optional[str] = Field(None, max_length=80, examples=["Japón"])
    web: Optional[str] = Field(None, max_length=255)


class DesarrolladoraCrear(DesarrolladoraBase):
    pass


class DesarrolladoraActualizar(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=120)
    pais: Optional[str] = Field(None, max_length=80)
    web: Optional[str] = Field(None, max_length=255)


class DesarrolladoraSalida(DesarrolladoraBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Videojuegos
# ---------------------------------------------------------------------------
class VideojuegoBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200,
                        examples=["Elden Ring"])
    descripcion: str = Field(..., min_length=1, max_length=4000,
                             examples=["Un vasto mundo de fantasía..."])
    caratula_url: str = Field(
        ...,
        max_length=500,
        examples=["https://placehold.co/600x800?text=Elden+Ring"],
        description="URL de la carátula (imagen) del videojuego",
    )
    anio_lanzamiento: int = Field(..., ge=1970, le=2035, examples=[2022])
    clasificacion: Optional[str] = Field(
        None, max_length=20, examples=["PEGI 16"],
        description="Clasificación por edad (PEGI)",
    )
    puntuacion: Optional[float] = Field(
        None, ge=0, le=10, examples=[9.5],
        description="Puntuación media de 0 a 10",
    )
    desarrolladora_id: Optional[int] = Field(
        None, description="ID de la desarrolladora (null = sin asignar)"
    )
    plataformas_ids: list[int] = Field(
        default_factory=list, examples=[[1, 2]],
        description="Lista de IDs de plataformas donde está disponible",
    )
    generos_ids: list[int] = Field(
        default_factory=list, examples=[[1, 3]],
        description="Lista de IDs de géneros",
    )

    @field_validator("caratula_url")
    @classmethod
    def _url_valida(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("caratula_url debe ser una URL http(s) válida")
        return v


class VideojuegoCrear(VideojuegoBase):
    pass


class VideojuegoActualizar(BaseModel):
    """Actualización parcial: solo se modifican los campos enviados."""

    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = Field(None, min_length=1, max_length=4000)
    caratula_url: Optional[str] = Field(None, max_length=500)
    anio_lanzamiento: Optional[int] = Field(None, ge=1970, le=2035)
    clasificacion: Optional[str] = Field(None, max_length=20)
    puntuacion: Optional[float] = Field(None, ge=0, le=10)
    desarrolladora_id: Optional[int] = None
    plataformas_ids: Optional[list[int]] = None
    generos_ids: Optional[list[int]] = None

    @field_validator("caratula_url")
    @classmethod
    def _url_valida(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("caratula_url debe ser una URL http(s) válida")
        return v


class VideojuegoSalida(BaseModel):
    id: int
    titulo: str
    descripcion: str
    caratula_url: str
    anio_lanzamiento: int
    clasificacion: Optional[str]
    puntuacion: Optional[float]
    fecha_registro: Optional[datetime] = None
    desarrolladora: Optional[DesarrolladoraSalida]
    plataformas: list[PlataformaSalida]
    generos: list[GeneroSalida]

    model_config = ConfigDict(from_attributes=True)


class PaginaVideojuegos(BaseModel):
    """Respuesta paginada del listado de videojuegos."""

    total: int
    pagina: int
    por_pagina: int
    paginas: int
    items: list[VideojuegoSalida]

    @classmethod
    def crear(cls, total: int, pagina: int, por_pagina: int, items: list):
        paginas = max(1, math.ceil(total / por_pagina))
        return cls(
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
            paginas=paginas,
            items=items,
        )


# ---------------------------------------------------------------------------
# Colección personal
# ---------------------------------------------------------------------------
class ColeccionBase(BaseModel):
    videojuego_id: int = Field(..., description="ID del videojuego poseído")
    plataforma_id: Optional[int] = Field(
        None, description="Plataforma del ejemplar (null = cualquiera/digital)"
    )
    estado: EstadoColeccion = Field(
        default="bueno",
        description="nuevo | como nuevo | bueno | aceptable | malo | digital",
    )
    fecha_compra: Optional[date] = Field(None, examples=["2024-05-17"])
    precio_compra: Optional[float] = Field(None, ge=0, examples=[59.99])
    valoracion: Optional[int] = Field(
        None, ge=1, le=10, description="Valoración personal de 1 a 10"
    )
    favorito: bool = False
    notas: Optional[str] = Field(None, max_length=2000)


class ColeccionCrear(ColeccionBase):
    pass


class ColeccionActualizar(BaseModel):
    """Actualización parcial de un ejemplar de la colección."""

    plataforma_id: Optional[int] = None
    estado: Optional[EstadoColeccion] = None
    fecha_compra: Optional[date] = None
    precio_compra: Optional[float] = Field(None, ge=0)
    valoracion: Optional[int] = Field(None, ge=1, le=10)
    favorito: Optional[bool] = None
    notas: Optional[str] = Field(None, max_length=2000)


class ColeccionFavorito(BaseModel):
    favorito: bool


class ColeccionSalida(BaseModel):
    id: int
    estado: str
    fecha_compra: Optional[date]
    precio_compra: Optional[float]
    valoracion: Optional[int]
    favorito: bool
    notas: Optional[str]
    fecha_adicion: Optional[datetime] = None
    videojuego: VideojuegoSalida
    plataforma: Optional[PlataformaSalida]

    model_config = ConfigDict(from_attributes=True)


class PaginaColeccion(BaseModel):
    """Respuesta paginada del listado de la colección."""

    total: int
    pagina: int
    por_pagina: int
    paginas: int
    items: list[ColeccionSalida]


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------
class ResumenEstadisticas(BaseModel):
    videojuegos: int
    plataformas: int
    generos: int
    desarrolladoras: int
    ejemplares_en_coleccion: int
    favoritos: int
    valoracion_media: Optional[float]
    inversion_total: Optional[float]


class ConteoPorNombre(BaseModel):
    nombre: str
    cantidad: int


class PlataformaEstadistica(BaseModel):
    plataforma: str
    fabricante: Optional[str]
    juegos: int
    en_coleccion: int


class GeneroEstadistica(BaseModel):
    genero: str
    juegos: int


class EstadoEstadistica(BaseModel):
    estado: str
    cantidad: int
