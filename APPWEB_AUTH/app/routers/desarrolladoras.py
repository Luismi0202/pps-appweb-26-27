"""Endpoints de desarrolladoras / editoras (CRUD completo)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Desarrolladora
from app.schemas import (
    DesarrolladoraActualizar,
    DesarrolladoraCrear,
    DesarrolladoraSalida,
)
from app.seguridad import requiere_gestor, usuario_actual

router = APIRouter(
    prefix="/api/desarrolladoras",
    tags=["4. Desarrolladoras"],
    dependencies=[Depends(usuario_actual)],
)


def _buscar(db: Session, desarrolladora_id: int) -> Desarrolladora:
    desarrolladora = db.get(Desarrolladora, desarrolladora_id)
    if desarrolladora is None:
        raise HTTPException(
            status_code=404,
            detail=f"La desarrolladora con id {desarrolladora_id} no existe",
        )
    return desarrolladora


@router.get("", response_model=list[DesarrolladoraSalida],
            summary="Listar desarrolladoras")
def listar_desarrolladoras(db: Session = Depends(get_db)):
    return db.scalars(
        select(Desarrolladora).order_by(Desarrolladora.nombre)
    ).all()


@router.get("/{desarrolladora_id}", response_model=DesarrolladoraSalida,
            summary="Obtener una desarrolladora")
def obtener_desarrolladora(
    desarrolladora_id: int, db: Session = Depends(get_db)
):
    return _buscar(db, desarrolladora_id)


@router.post("", response_model=DesarrolladoraSalida,
             status_code=status.HTTP_201_CREATED,
             summary="Crear una desarrolladora",
             dependencies=[Depends(requiere_gestor)])
def crear_desarrolladora(
    datos: DesarrolladoraCrear, db: Session = Depends(get_db)
):
    repetida = db.scalar(
        select(Desarrolladora).where(
            func.lower(Desarrolladora.nombre) == datos.nombre.strip().lower()
        )
    )
    if repetida:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una desarrolladora llamada '{datos.nombre}'",
        )
    nueva = Desarrolladora(
        nombre=datos.nombre.strip(),
        pais=datos.pais,
        web=datos.web,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.put("/{desarrolladora_id}", response_model=DesarrolladoraSalida,
            summary="Actualizar una desarrolladora",
            dependencies=[Depends(requiere_gestor)])
def actualizar_desarrolladora(
    desarrolladora_id: int,
    datos: DesarrolladoraActualizar,
    db: Session = Depends(get_db),
):
    desarrolladora = _buscar(db, desarrolladora_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(desarrolladora, campo, valor)
    db.commit()
    db.refresh(desarrolladora)
    return desarrolladora


@router.delete("/{desarrolladora_id}", summary="Eliminar una desarrolladora",
               dependencies=[Depends(requiere_gestor)])
def eliminar_desarrolladora(
    desarrolladora_id: int, db: Session = Depends(get_db)
):
    desarrolladora = _buscar(db, desarrolladora_id)

    total = len(desarrolladora.videojuegos)
    if total:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede eliminar: tiene {total} videojuego(s) asociados"
            ),
        )

    db.delete(desarrolladora)
    db.commit()
    return {
        "mensaje": "Desarrolladora eliminada correctamente",
        "id": desarrolladora_id,
    }
