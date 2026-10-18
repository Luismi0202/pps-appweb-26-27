"""Endpoints de géneros (CRUD completo)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Genero, videojuego_genero
from app.schemas import GeneroActualizar, GeneroCrear, GeneroSalida
from app.seguridad import requiere_gestor, usuario_actual

router = APIRouter(
    prefix="/api/generos",
    tags=["3. Géneros"],
    dependencies=[Depends(usuario_actual)],
)


def _buscar(db: Session, genero_id: int) -> Genero:
    genero = db.get(Genero, genero_id)
    if genero is None:
        raise HTTPException(
            status_code=404,
            detail=f"El género con id {genero_id} no existe",
        )
    return genero


@router.get("", response_model=list[GeneroSalida], summary="Listar géneros")
def listar_generos(db: Session = Depends(get_db)):
    return db.scalars(select(Genero).order_by(Genero.nombre)).all()


@router.get("/{genero_id}", response_model=GeneroSalida,
            summary="Obtener un género")
def obtener_genero(genero_id: int, db: Session = Depends(get_db)):
    return _buscar(db, genero_id)


@router.post("", response_model=GeneroSalida,
             status_code=status.HTTP_201_CREATED, summary="Crear un género",
             dependencies=[Depends(requiere_gestor)])
def crear_genero(datos: GeneroCrear, db: Session = Depends(get_db)):
    repetido = db.scalar(
        select(Genero).where(
            func.lower(Genero.nombre) == datos.nombre.strip().lower()
        )
    )
    if repetido:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un género llamado '{datos.nombre}'",
        )
    nuevo = Genero(
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.put("/{genero_id}", response_model=GeneroSalida,
            summary="Actualizar un género",
            dependencies=[Depends(requiere_gestor)])
def actualizar_genero(
    genero_id: int,
    datos: GeneroActualizar,
    db: Session = Depends(get_db),
):
    genero = _buscar(db, genero_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(genero, campo, valor)
    db.commit()
    db.refresh(genero)
    return genero


@router.delete("/{genero_id}", summary="Eliminar un género",
               dependencies=[Depends(requiere_gestor)])
def eliminar_genero(genero_id: int, db: Session = Depends(get_db)):
    genero = _buscar(db, genero_id)

    en_uso = db.scalar(
        select(func.count())
        .select_from(videojuego_genero)
        .where(videojuego_genero.c.genero_id == genero_id)
    )
    if en_uso:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede eliminar: el género está asignado a "
                f"{en_uso} videojuego(s)"
            ),
        )

    db.delete(genero)
    db.commit()
    return {"mensaje": "Género eliminado correctamente", "id": genero_id}
