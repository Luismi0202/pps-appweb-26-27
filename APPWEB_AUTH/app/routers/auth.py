"""Endpoints de autenticación: registro, login, contraseña y cuentas (JWT)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ROL_ADMIN, ItemColeccion, Usuario
from app.schemas import (
    PaginaUsuarios,
    PasswordCambio,
    PasswordRestablecer,
    RolActualizar,
    TokenRefresco,
    TokenSalida,
    UsuarioCrear,
    UsuarioLogin,
    UsuarioSalida,
)
from app.seguridad import (
    MINUTOS_REFRESH,
    MINUTOS_TOKEN,
    crear_refresh_token,
    crear_token,
    hash_password,
    requiere_admin,
    requiere_gestor,
    usuario_actual,
    usuario_del_refresh,
    verificar_password,
)

router = APIRouter(prefix="/api/auth", tags=["0. Autenticación"])

# ---------------------------------------------------------------------------
# Usuarios: listado y búsqueda para admin y gestor; los roles solo los
# cambia un admin, y solo un admin puede borrar cuentas o restablecer
# contraseñas ajenas. Se sirve bajo /api/usuarios, pero agrupado aquí porque
# es parte de las cuentas, igual que el registro y el login.
# ---------------------------------------------------------------------------
router_usuarios = APIRouter(prefix="/api/usuarios", tags=["7. Usuarios"])

_ORDEN_USUARIOS = (Usuario.nombre.asc(), Usuario.id.asc())


@router_usuarios.get(
    "",
    response_model=PaginaUsuarios,
    summary="Listar usuarios con búsqueda (admin y gestor)",
)
def listar_usuarios(
    q: str | None = Query(None, description="Busca por nombre, email o rol"),
    rol: str | None = Query(None, description="Filtra por rol exacto"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(requiere_gestor),
):
    filtros = []
    if q:
        like = f"%{q.strip()}%"
        filtros.append(
            or_(
                Usuario.nombre.ilike(like),
                Usuario.email.ilike(like),
                Usuario.rol.ilike(like),
            )
        )
    if rol:
        filtros.append(Usuario.rol == rol)

    total = db.scalar(select(func.count()).select_from(Usuario).where(*filtros)) or 0
    items = db.scalars(
        select(Usuario)
        .where(*filtros)
        .order_by(*_ORDEN_USUARIOS)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return PaginaUsuarios.crear(total, pagina, por_pagina, items)


@router_usuarios.get(
    "/{usuario_id}",
    response_model=UsuarioSalida,
    summary="Ver una cuenta (admin y gestor)",
)
def ver_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(requiere_gestor),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La cuenta con id {usuario_id} no existe",
        )
    return usuario


@router_usuarios.patch(
    "/{usuario_id}/rol",
    response_model=UsuarioSalida,
    summary="Cambiar el rol de una cuenta (solo admin)",
)
def cambiar_rol(
    usuario_id: int,
    datos: RolActualizar,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # Nadie debe poder perder sus propios permisos sin darse cuenta.
    if usuario_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol",
        )

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La cuenta con id {usuario_id} no existe",
        )

    # Si deja de ser admin, debe quedar al menos un administrador.
    if usuario.rol == ROL_ADMIN and datos.rol != ROL_ADMIN:
        admins = db.scalar(
            select(func.count()).select_from(Usuario).where(Usuario.rol == ROL_ADMIN)
        ) or 0
        if admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Debe quedar al menos un administrador en la plataforma",
            )

    usuario.rol = datos.rol
    db.commit()
    db.refresh(usuario)
    return usuario


@router_usuarios.patch(
    "/{usuario_id}/password",
    response_model=UsuarioSalida,
    summary="Restablecer la contraseña de una cuenta (solo admin)",
)
def restablecer_password(
    usuario_id: int,
    datos: PasswordRestablecer,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    """Proceso de recuperación de cuenta: el admin pone una contraseña nueva.

    No hace falta conocer la anterior (por eso solo lo puede hacer un
    administrador y no un gestor). Al guardarla se incrementa la versión de
    token de la cuenta, de modo que los JWT emitidos hasta ese momento —
    incluidos los de quien suplantaba o secuestró la sesión— dejan de servir.

    El admin se cambia su propia contraseña por el flujo dedicado
    ``POST /api/auth/cambiar-password``, que exige la actual.
    """
    if usuario_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Para tu propia contraseña usa POST /api/auth/cambiar-password "
                "(necesitas conocer la actual)"
            ),
        )

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La cuenta con id {usuario_id} no existe",
        )

    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.token_version += 1
    db.commit()
    db.refresh(usuario)
    return usuario


@router_usuarios.delete(
    "/{usuario_id}",
    summary="Eliminar una cuenta y su colección (solo admin)",
)
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    """Borra la cuenta y, en cascada, los ejemplares de su colección.

    Dos reglas que hacen que siempre tenga sentido:
    un admin no puede eliminarse a sí mismo (evita bloquearse la salida y
    perder el último administrador —como quien ejecuta la acción es admin y
    sobrevive, siempre queda al menos uno—), y la operación es exclusiva de
    administradores: los gestores solo consultan cuentas.
    """
    if usuario_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta",
        )

    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La cuenta con id {usuario_id} no existe",
        )

    ejemplares = (
        db.scalar(
            select(func.count())
            .select_from(ItemColeccion)
            .where(ItemColeccion.usuario_id == usuario_id)
        )
        or 0
    )

    db.delete(usuario)  # la relación y la FK CASCADE arrastran su colección
    db.commit()
    return {
        "mensaje": (
            f"Cuenta de {usuario.email} eliminada junto con "
            f"{ejemplares} ejemplar(es) de su colección"
        ),
        "id": usuario_id,
        "ejemplares_eliminados": ejemplares,
    }


def _respuesta_token(usuario: Usuario) -> TokenSalida:
    """Emite el par de tokens: access corto + refresh largo (rotación).

    Llevan la ``token_version`` vigente: si la cuenta cambia de contraseña,
    los pares anteriores quedan anulados.
    """
    version = usuario.token_version
    return TokenSalida(
        access_token=crear_token(usuario.id, version=version),
        refresh_token=crear_refresh_token(usuario.id, version=version),
        token_type="bearer",
        expira_en_segundos=MINUTOS_TOKEN * 60,
        refresh_expira_en_segundos=MINUTOS_REFRESH * 60,
        usuario=UsuarioSalida.model_validate(usuario),
    )


@router.post(
    "/registro",
    response_model=TokenSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una cuenta (devuelve token e inicia sesión)",
)
def registro(datos: UsuarioCrear, db: Session = Depends(get_db)):
    ya_existe = db.scalar(
        select(Usuario).where(func.lower(Usuario.email) == datos.email.lower())
    )
    if ya_existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay una cuenta registrada con el email '{datos.email}'",
        )

    usuario = Usuario(
        nombre=datos.nombre,
        email=datos.email.lower(),
        password_hash=hash_password(datos.password),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _respuesta_token(usuario)


@router.post(
    "/login",
    response_model=TokenSalida,
    summary="Iniciar sesión y obtener el token JWT",
)
def login(datos: UsuarioLogin, db: Session = Depends(get_db)):
    usuario = db.scalar(
        select(Usuario).where(func.lower(Usuario.email) == datos.email.strip().lower())
    )
    if usuario is None or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )
    return _respuesta_token(usuario)


@router.post(
    "/refresh",
    response_model=TokenSalida,
    summary="Renovar la sesión con el refresh token (rotación)",
)
def refrescar_token(datos: TokenRefresco, db: Session = Depends(get_db)):
    """Renueva los tokens sin volver a introducir la contraseña.

    Recibe el ``refresh_token`` devuelto en el registro o login y responde con
    un **nuevo par** de tokens (el refresh anterior se sustituye). El access
    caducado deja de servir: con este endpoint el frontend sigue la sesión
    viva sin interrumpir al usuario.
    """
    # Lanza 401 si el token es de otro tipo, está caducado o no es válido.
    usuario = usuario_del_refresh(datos.refresh_token, db)
    return _respuesta_token(usuario)


@router.post(
    "/cambiar-password",
    response_model=TokenSalida,
    summary="Cambiar mi propia contraseña (cualquier rol)",
)
def cambiar_password(
    datos: PasswordCambio,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
):
    """Cambia la contraseña de la cuenta autenticada.

    Exige la **contraseña actual**: tener un token (posiblemente robado) no
    basta para quedarte en una cuenta sin conocer su clave. Como medida de
    higiene, al guardar la nueva se incrementa la ``token_version``: todos
    los tokens emitidos hasta ese momento —otras sesiones abiertas, refresh
    caducados reutilizables— dejan de ser válidos. La respuesta devuelve un
    par de tokens nuevo, así que quien ha cambiado la contraseña sigue
    dentro sin volver a entrar y el resto de sesiones queda fuera.
    """
    if not verificar_password(datos.password_actual, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta",
        )

    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.token_version += 1
    db.commit()
    db.refresh(usuario)
    return _respuesta_token(usuario)


@router.get(
    "/yo",
    response_model=UsuarioSalida,
    summary="Datos del usuario autenticado",
)
def yo(usuario: Usuario = Depends(usuario_actual)):
    return usuario
