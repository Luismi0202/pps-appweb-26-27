"""Endpoints de plataformas (CRUD completo)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ItemColeccion, Plataforma, videojuego_plataforma
from app.schemas import PlataformaCrear, PlataformaSalida, PlataformaActualizar
from app.seguridad import requiere_gestor, usuario_actual

router = APIRouter(
    prefix="/api/plataformas",
    tags=["2. Plataformas"],
    dependencies=[Depends(usuario_actual)],
)


def _buscar(db: Session, plataforma_id: int) -> Plataforma:
    plataforma = db.get(Plataforma, plataforma_id)
    if plataforma is None:
        raise HTTPException(
            status_code=404,
            detail=f"La plataforma con id {plataforma_id} no existe",
        )
    return plataforma


@router.get("", response_model=list[PlataformaSalida], summary="Listar plataformas")
def listar_plataformas(db: Session = Depends(get_db)):
    return db.scalars(
        select(Plataforma).order_by(Plataforma.nombre)
    ).all()


@router.get("/{plataforma_id}", response_model=PlataformaSalida,
            summary="Obtener una plataforma")
def obtener_plataforma(plataforma_id: int, db: Session = Depends(get_db)):
    return _buscar(db, plataforma_id)


@router.post("", response_model=PlataformaSalida,
             status_code=status.HTTP_201_CREATED, summary="Crear una plataforma",
             dependencies=[Depends(requiere_gestor)])
def crear_plataforma(datos: PlataformaCrear, db: Session = Depends(get_db)):
    repetida = db.scalar(
        select(Plataforma).where(
            func.lower(Plataforma.nombre) == datos.nombre.strip().lower()
        )
    )
    if repetida:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una plataforma llamada '{datos.nombre}'",
        )
    nueva = Plataforma(
        nombre=datos.nombre.strip(),
        fabricante=datos.fabricante,
        anio_lanzamiento=datos.anio_lanzamiento,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.put("/{plataforma_id}", response_model=PlataformaSalida,
            summary="Actualizar una plataforma",
            dependencies=[Depends(requiere_gestor)])
def actualizar_plataforma(
    plataforma_id: int,
    datos: PlataformaActualizar,
    db: Session = Depends(get_db),
):
    plataforma = _buscar(db, plataforma_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plataforma, campo, valor)
    db.commit()
    db.refresh(plataforma)
    return plataforma


@router.delete("/{plataforma_id}", summary="Eliminar una plataforma",
               dependencies=[Depends(requiere_gestor)])
def eliminar_plataforma(plataforma_id: int, db: Session = Depends(get_db)):
    plataforma = _buscar(db, plataforma_id)

    en_juegos = db.scalar(
        select(func.count())
        .select_from(videojuego_plataforma)
        .where(videojuego_plataforma.c.plataforma_id == plataforma_id)
    )
    en_coleccion = db.scalar(
        select(func.count())
        .select_from(ItemColeccion)
        .where(ItemColeccion.plataforma_id == plataforma_id)
    )
    if en_juegos or en_coleccion:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede eliminar: la plataforma está en uso por "
                f"{en_juegos} videojuego(s) y {en_coleccion} ejemplar(es) "
                "de la colección"
            ),
        )

    db.delete(plataforma)
    db.commit()
    return {"mensaje": "Plataforma eliminada correctamente", "id": plataforma_id}
