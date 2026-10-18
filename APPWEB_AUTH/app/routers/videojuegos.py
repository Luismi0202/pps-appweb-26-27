"""Endpoints de videojuegos: el núcleo de la API (CRUD completo)."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Desarrolladora,
    Genero,
    Plataforma,
    Videojuego,
)
from app.schemas import (
    PaginaVideojuegos,
    VideojuegoActualizar,
    VideojuegoCrear,
    VideojuegoSalida,
)
from app.seguridad import requiere_gestor, usuario_actual

router = APIRouter(
    prefix="/api/videojuegos",
    tags=["1. Videojuegos"],
    dependencies=[Depends(usuario_actual)],
)

_CARGA = (
    selectinload(Videojuego.plataformas),
    selectinload(Videojuego.generos),
    selectinload(Videojuego.desarrolladora),
)

_ORDEN = {
    "titulo-asc": Videojuego.titulo.asc(),
    "titulo-desc": Videojuego.titulo.desc(),
    "anio-asc": Videojuego.anio_lanzamiento.asc(),
    "anio-desc": Videojuego.anio_lanzamiento.desc(),
    "recientes": Videojuego.id.desc(),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _buscar(db: Session, videojuego_id: int) -> Videojuego:
    vj = db.scalar(
        select(Videojuego)
        .where(Videojuego.id == videojuego_id)
        .options(*_CARGA)
    )
    if vj is None:
        raise HTTPException(
            status_code=404,
            detail=f"El videojuego con id {videojuego_id} no existe",
        )
    return vj


def _resolver_ids(
    db: Session, modelo, ids: list[int], nombre: str
) -> list:
    """Devuelve los objetos ORM de una lista de IDs o lanza un 404."""
    if not ids:
        return []
    objetos = db.scalars(
        select(modelo).where(modelo.id.in_(set(ids)))
    ).all()
    encontrados = {obj.id for obj in objetos}
    faltantes = sorted({i for i in ids if i not in encontrados})
    if faltantes:
        raise HTTPException(
            status_code=404,
            detail=f"IDs de {nombre} no encontrados: {faltantes}",
        )
    return list(objetos)


def _validar_desarrolladora(db: Session, desarrolladora_id: Optional[int]):
    if desarrolladora_id is not None and db.get(
        Desarrolladora, desarrolladora_id
    ) is None:
        raise HTTPException(
            status_code=404,
            detail=f"La desarrolladora con id {desarrolladora_id} no existe",
        )


def _condicion_genero(valor: str):
    if valor.isdigit():
        return Videojuego.generos.any(Genero.id == int(valor))
    return Videojuego.generos.any(
        func.lower(Genero.nombre) == valor.strip().lower()
    )


def _condicion_plataforma(valor: str):
    if valor.isdigit():
        return Videojuego.plataformas.any(Plataforma.id == int(valor))
    return Videojuego.plataformas.any(
        func.lower(Plataforma.nombre) == valor.strip().lower()
    )


def _condicion_desarrolladora(valor: str):
    if valor.isdigit():
        return Videojuego.desarrolladora.has(
            Desarrolladora.id == int(valor)
        )
    return Videojuego.desarrolladora.has(
        func.lower(Desarrolladora.nombre) == valor.strip().lower()
    )


# ---------------------------------------------------------------------------
# GET /api/videojuegos — listado con filtros, búsqueda y paginación
# ---------------------------------------------------------------------------
@router.get("", response_model=PaginaVideojuegos, summary="Listar videojuegos")
def listar_videojuegos(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(
        None, min_length=1, max_length=100,
        description="Busca por título o descripción",
    ),
    genero: Optional[str] = Query(
        None, description="Filtra por ID o nombre de género (ej. '3' o 'RPG')"
    ),
    plataforma: Optional[str] = Query(
        None, description="Filtra por ID o nombre de plataforma"
    ),
    desarrolladora: Optional[str] = Query(
        None, description="Filtra por ID o nombre de desarrolladora"
    ),
    anio_desde: Optional[int] = Query(None, ge=1970, le=2035),
    anio_hasta: Optional[int] = Query(None, ge=1970, le=2035),
    orden: Literal[
        "titulo-asc", "titulo-desc", "anio-asc", "anio-desc", "recientes"
    ] = Query("titulo-asc", description="Campo de ordenación"),
    pagina: int = Query(1, ge=1, description="Página (empieza en 1)"),
    por_pagina: int = Query(20, ge=1, le=100, description="Resultados por página"),
):
    condiciones = []
    if q:
        busqueda = f"%{q.strip()}%"
        condiciones.append(
            or_(
                Videojuego.titulo.ilike(busqueda),
                Videojuego.descripcion.ilike(busqueda),
            )
        )
    if genero:
        condiciones.append(_condicion_genero(genero))
    if plataforma:
        condiciones.append(_condicion_plataforma(plataforma))
    if desarrolladora:
        condiciones.append(_condicion_desarrolladora(desarrolladora))
    if anio_desde:
        condiciones.append(Videojuego.anio_lanzamiento >= anio_desde)
    if anio_hasta:
        condiciones.append(Videojuego.anio_lanzamiento <= anio_hasta)

    total = db.scalar(
        select(func.count()).select_from(Videojuego).where(*condiciones)
    ) or 0

    items = db.scalars(
        select(Videojuego)
        .where(*condiciones)
        .options(*_CARGA)
        .order_by(_ORDEN[orden])
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()

    return PaginaVideojuegos.crear(total, pagina, por_pagina, items)


# ---------------------------------------------------------------------------
# GET /api/videojuegos/{id} — detalle (carátula, descripción, relaciones)
# ---------------------------------------------------------------------------
@router.get(
    "/{videojuego_id}",
    response_model=VideojuegoSalida,
    summary="Obtener un videojuego",
)
def obtener_videojuego(videojuego_id: int, db: Session = Depends(get_db)):
    return _buscar(db, videojuego_id)


# ---------------------------------------------------------------------------
# POST /api/videojuegos — crear
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=VideojuegoSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un videojuego",
    dependencies=[Depends(requiere_gestor)],
)
def crear_videojuego(
    datos: VideojuegoCrear, db: Session = Depends(get_db)
):
    _validar_desarrolladora(db, datos.desarrolladora_id)
    plataformas = _resolver_ids(db, Plataforma, datos.plataformas_ids, "plataforma")
    generos = _resolver_ids(db, Genero, datos.generos_ids, "género")

    nuevo = Videojuego(
        titulo=datos.titulo.strip(),
        descripcion=datos.descripcion.strip(),
        caratula_url=datos.caratula_url,
        anio_lanzamiento=datos.anio_lanzamiento,
        clasificacion=datos.clasificacion,
        puntuacion=datos.puntuacion,
        desarrolladora_id=datos.desarrolladora_id,
        plataformas=plataformas,
        generos=generos,
    )
    db.add(nuevo)
    db.commit()
    return _buscar(db, nuevo.id)


# ---------------------------------------------------------------------------
# PUT /api/videojuegos/{id} — actualización parcial
# ---------------------------------------------------------------------------
@router.put(
    "/{videojuego_id}",
    response_model=VideojuegoSalida,
    summary="Actualizar un videojuego",
    dependencies=[Depends(requiere_gestor)],
)
def actualizar_videojuego(
    videojuego_id: int,
    datos: VideojuegoActualizar,
    db: Session = Depends(get_db),
):
    vj = _buscar(db, videojuego_id)

    if "desarrolladora_id" in datos.model_fields_set:
        _validar_desarrolladora(db, datos.desarrolladora_id)

    cambios = datos.model_dump(exclude_unset=True)
    plataformas_ids = cambios.pop("plataformas_ids", None)
    generos_ids = cambios.pop("generos_ids", None)
    cambios.pop("desarrolladora_id", None)

    for campo, valor in cambios.items():
        setattr(vj, campo, valor)

    if "desarrolladora_id" in datos.model_fields_set:
        vj.desarrolladora_id = datos.desarrolladora_id
    if plataformas_ids is not None:
        vj.plataformas = _resolver_ids(
            db, Plataforma, plataformas_ids, "plataforma"
        )
    if generos_ids is not None:
        vj.generos = _resolver_ids(db, Genero, generos_ids, "género")

    db.commit()
    return _buscar(db, videojuego_id)


# ---------------------------------------------------------------------------
# DELETE /api/videojuegos/{id} — eliminar (borra también su colección)
# ---------------------------------------------------------------------------
@router.delete(
    "/{videojuego_id}",
    summary="Eliminar un videojuego",
    dependencies=[Depends(requiere_gestor)],
)
def eliminar_videojuego(videojuego_id: int, db: Session = Depends(get_db)):
    vj = _buscar(db, videojuego_id)
    db.delete(vj)
    db.commit()
    return {
        "mensaje": "Videojuego eliminado correctamente",
        "id": videojuego_id,
    }
