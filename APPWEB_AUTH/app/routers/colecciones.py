"""Endpoints de la colección personal (ejemplares poseídos por cada usuario)."""
import math
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import ItemColeccion, Plataforma, Usuario, Videojuego
from app.schemas import (
    ColeccionActualizar,
    ColeccionCrear,
    ColeccionFavorito,
    ColeccionSalida,
    PaginaColeccion,
)
from app.seguridad import usuario_actual

router = APIRouter(
    prefix="/api/colecciones",
    tags=["5. Colección (por usuario)"],
)

_CARGA = (
    selectinload(ItemColeccion.videojuego).selectinload(Videojuego.plataformas),
    selectinload(ItemColeccion.videojuego).selectinload(Videojuego.generos),
    selectinload(ItemColeccion.videojuego).selectinload(Videojuego.desarrolladora),
    selectinload(ItemColeccion.plataforma),
)

_ORDEN = {
    "fecha-desc": ItemColeccion.fecha_adicion.desc(),
    "fecha-asc": ItemColeccion.fecha_adicion.asc(),
    "valoracion-desc": ItemColeccion.valoracion.desc().nulls_last(),
    "precio-desc": ItemColeccion.precio_compra.desc().nulls_last(),
    "titulo-asc": Videojuego.titulo.asc(),
}


def _buscar(db: Session, item_id: int, usuario: Usuario) -> ItemColeccion:
    """Busca un ejemplar del usuario actual (404 si no existe o es de otro)."""
    item = db.scalar(
        select(ItemColeccion)
        .where(
            ItemColeccion.id == item_id,
            ItemColeccion.usuario_id == usuario.id,
        )
        .options(*_CARGA)
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"El ejemplar de colección con id {item_id} no existe",
        )
    return item


@router.get("", response_model=PaginaColeccion, summary="Listar mi colección")
def listar_coleccion(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
    q: Optional[str] = Query(
        None, min_length=1, max_length=100,
        description="Busca por título o descripción del videojuego",
    ),
    estado: Optional[str] = Query(
        None,
        description="nuevo | como nuevo | bueno | aceptable | malo | digital",
    ),
    favorito: Optional[bool] = Query(
        None, description="Filtra solo favoritos (true) o no favoritos (false)"
    ),
    plataforma: Optional[str] = Query(
        None, description="ID o nombre de plataforma del ejemplar"
    ),
    valoracion_min: Optional[int] = Query(None, ge=1, le=10),
    orden: Literal[
        "fecha-desc", "fecha-asc", "valoracion-desc", "precio-desc", "titulo-asc"
    ] = "fecha-desc",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
):
    condiciones = [ItemColeccion.usuario_id == usuario.id]
    if q:
        busqueda = f"%{q.strip()}%"
        condiciones.append(
            or_(
                Videojuego.titulo.ilike(busqueda),
                Videojuego.descripcion.ilike(busqueda),
            )
        )
    if estado:
        condiciones.append(
            func.lower(ItemColeccion.estado) == estado.strip().lower()
        )
    if favorito is not None:
        condiciones.append(ItemColeccion.favorito == favorito)
    if valoracion_min is not None:
        condiciones.append(ItemColeccion.valoracion >= valoracion_min)
    if plataforma:
        if plataforma.isdigit():
            condiciones.append(ItemColeccion.plataforma_id == int(plataforma))
        else:
            condiciones.append(
                Plataforma.nombre.ilike(plataforma.strip())
                & (ItemColeccion.plataforma_id == Plataforma.id)
            )

    total = db.scalar(
        select(func.count())
        .select_from(ItemColeccion)
        .join(Videojuego, Videojuego.id == ItemColeccion.videojuego_id)
        .outerjoin(Plataforma, Plataforma.id == ItemColeccion.plataforma_id)
        .where(*condiciones)
    ) or 0

    items = db.scalars(
        select(ItemColeccion)
        .join(Videojuego, Videojuego.id == ItemColeccion.videojuego_id)
        .outerjoin(Plataforma, Plataforma.id == ItemColeccion.plataforma_id)
        .where(*condiciones)
        .options(*_CARGA)
        .order_by(_ORDEN[orden])
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()

    paginas = max(1, math.ceil(total / por_pagina))
    return PaginaColeccion(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        paginas=paginas,
        items=items,
    )


@router.get("/{item_id}", response_model=ColeccionSalida,
            summary="Obtener un ejemplar")
def obtener_item(
    item_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    return _buscar(db, item_id, usuario)


@router.post("", response_model=ColeccionSalida,
             status_code=status.HTTP_201_CREATED,
             summary="Añadir un videojuego a mi colección")
def crear_item(
    datos: ColeccionCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    vj = db.get(Videojuego, datos.videojuego_id)
    if vj is None:
        raise HTTPException(
            status_code=404,
            detail=f"El videojuego con id {datos.videojuego_id} no existe",
        )

    plataforma = None
    if datos.plataforma_id is not None:
        plataforma = db.get(Plataforma, datos.plataforma_id)
        if plataforma is None:
            raise HTTPException(
                status_code=404,
                detail=f"La plataforma con id {datos.plataforma_id} no existe",
            )

    # Evita duplicados en MI colección: mismo juego + misma plataforma
    consulta = select(ItemColeccion).where(
        ItemColeccion.usuario_id == usuario.id,
        ItemColeccion.videojuego_id == datos.videojuego_id,
    )
    if datos.plataforma_id is None:
        consulta = consulta.where(ItemColeccion.plataforma_id.is_(None))
    else:
        consulta = consulta.where(
            ItemColeccion.plataforma_id == datos.plataforma_id
        )
    if db.scalar(consulta):
        raise HTTPException(
            status_code=409,
            detail="Ese videojuego ya está en tu colección en esa plataforma",
        )

    nuevo = ItemColeccion(
        usuario_id=usuario.id,
        videojuego=vj,
        plataforma=plataforma,
        estado=datos.estado,
        fecha_compra=datos.fecha_compra,
        precio_compra=datos.precio_compra,
        valoracion=datos.valoracion,
        favorito=datos.favorito,
        notas=datos.notas,
    )
    db.add(nuevo)
    db.commit()
    return _buscar(db, nuevo.id, usuario)


@router.put("/{item_id}", response_model=ColeccionSalida,
            summary="Actualizar un ejemplar (parcial)")
def actualizar_item(
    item_id: int,
    datos: ColeccionActualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    item = _buscar(db, item_id, usuario)

    cambios = datos.model_dump(exclude_unset=True)
    plataforma_id = cambios.pop("plataforma_id", "sin_cambios")

    if plataforma_id != "sin_cambios":
        if plataforma_id is not None:
            if db.get(Plataforma, plataforma_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"La plataforma con id {plataforma_id} no existe",
                )
            item.plataforma_id = plataforma_id
        else:
            item.plataforma_id = None

    for campo, valor in cambios.items():
        setattr(item, campo, valor)

    db.commit()
    return _buscar(db, item_id, usuario)


@router.patch("/{item_id}/favorito", response_model=ColeccionSalida,
              summary="Marcar o desmarcar como favorito")
def cambiar_favorito(
    item_id: int,
    datos: ColeccionFavorito,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    item = _buscar(db, item_id, usuario)
    item.favorito = datos.favorito
    db.commit()
    return _buscar(db, item_id, usuario)


@router.delete("/{item_id}", summary="Eliminar un ejemplar de mi colección")
def eliminar_item(
    item_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    item = _buscar(db, item_id, usuario)
    db.delete(item)
    db.commit()
    return {"mensaje": "Ejemplar eliminado de la colección", "id": item_id}
