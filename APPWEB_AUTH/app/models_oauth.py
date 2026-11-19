"""Cuentas externas (Google / GitHub) vinculadas a un usuario de la Ludoteca.

Es una tabla nueva y aparte: el modelo ``Usuario`` no cambia. Cada fila dice
"la cuenta ``sub`` del proveedor ``proveedor`` inicia sesión como el usuario
``usuario_id``". La crea ``Base.metadata.create_all`` al arrancar, igual que
el resto de tablas, así que las bases de datos existentes no necesitan
migración.

Si se borra el usuario, la clave foránea ``ON DELETE CASCADE`` (con el
``PRAGMA foreign_keys=ON`` que activa ``database.py``) borra sus vínculos.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

PROVEEDOR_GOOGLE = "google"
PROVEEDOR_GITHUB = "github"


class CuentaOAuth(Base):
    __tablename__ = "cuentas_oauth"
    __table_args__ = (
        UniqueConstraint("proveedor", "sub", name="uq_cuenta_oauth_proveedor_sub"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    proveedor: Mapped[str] = mapped_column(String(20))
    # Identificador estable de la cuenta en el proveedor ("sub" de Google,
    # "id" numérico de GitHub). El email puede cambiar; esto no.
    sub: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    fecha_vinculacion: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
