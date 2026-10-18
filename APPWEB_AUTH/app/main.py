"""Punto de entrada de la API Colección de Videojuegos."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (registra los modelos en el metadata)
from app.database import Base, SessionLocal, engine, migrar_colecciones, migrar_usuarios
from app.routers import (
    auth,
    colecciones,
    desarrolladoras,
    estadisticas,
    generos,
    plataformas,
    videojuegos,
)
from app.seed import asegurar_admin, asignar_huerfanos, seed_si_vacio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crea/actualiza las tablas y carga datos de ejemplo al arrancar."""
    Base.metadata.create_all(bind=engine)
    # Adapta bases de datos anteriores (booleano es_admin -> columna rol).
    migrar_usuarios()
    db = SessionLocal()
    try:
        admin = asegurar_admin(db)
        # Migra bases de datos antiguas (colección global -> por usuario).
        migrar_colecciones(admin.id)
        seed_si_vacio(db, admin)
        asignar_huerfanos(db, admin)
    finally:
        db.close()
    yield


app = FastAPI(
    title="API Colección de Videojuegos",
    description=(
        "Backend REST para gestionar una colección de videojuegos.\n\n"
        "**Autenticación (JWT):**\n"
        "0. **Auth** — regístrate en `/api/auth/registro`, inicia sesión en "
        "`/api/auth/login` y usa el token con el botón **Authorize** "
        "(esquema `Bearer`).\n"
        "   Esa respuesta trae dos tokens: un **access token** corto y un "
        "**refresh token** largo. Cuando el access caduca, renueva la sesión "
        "sin contraseña en `POST /api/auth/refresh`.\n\n"
        "**Roles:** cada cuenta tiene un rol. `usuario` (por defecto) solo "
        "gestiona su propia colección; `gestor` además edita el catálogo "
        "(videojuegos, plataformas, géneros y desarrolladoras) y consulta las "
        "cuentas; `admin` además asigna los roles.\n\n"
        "**Apartados:**\n"
        "1. **Videojuegos** — CRUD con carátula, descripción, filtros y paginación\n"
        "2. **Plataformas** — CRUD\n"
        "3. **Géneros** — CRUD\n"
        "4. **Desarrolladoras** — CRUD\n"
        "5. **Colección** — tus ejemplares: estado, precio, valoración y favoritos\n"
        "6. **Estadísticas** — resúmenes y conteos de tu colección\n"
        "7. **Usuarios** — consultar cuentas (admin y gestor) y cambiar roles (solo admin)\n\n"
        "Todos los endpoints (salvo auth y `/`) requieren el token JWT.\n"
        "CORS abierto: puedes llamarla desde cualquier página web (fetch/axios)."
    ),
    version="2.1.0",
    lifespan=lifespan,
    contact={"name": "API Colección de Videojuegos"},
)

# CORS: permite peticiones desde cualquier frontend (páginas web, Postman...)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auth.router_usuarios)
app.include_router(videojuegos.router)
app.include_router(plataformas.router)
app.include_router(generos.router)
app.include_router(desarrolladoras.router)
app.include_router(colecciones.router)
app.include_router(estadisticas.router)

# Panel web "Ludoteca" servido por la propia API: http://localhost:8000/panel
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount(
    "/panel",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="panel",
)


@app.get("/", tags=["General"], summary="Información de la API")
def raiz():
    return {
        "mensaje": "API Colección de Videojuegos",
        "version": "2.1.0",
        "documentacion_interactiva": "/docs",
        "openapi": "/openapi.json",
        "panel_web": "/panel",
        "autenticacion": {
            "registro": "POST /api/auth/registro",
            "login": "POST /api/auth/login",
            "refrescar_token": "POST /api/auth/refresh",
            "usuario_actual": "GET /api/auth/yo",
        },
        "apartados": {
            "videojuegos": "/api/videojuegos",
            "plataformas": "/api/plataformas",
            "generos": "/api/generos",
            "desarrolladoras": "/api/desarrolladoras",
            "colecciones": "/api/colecciones",
            "estadisticas": "/api/estadisticas/resumen",
            "usuarios": "/api/usuarios",
        },
    }


@app.get("/api/salud", tags=["General"], summary="Comprobar que la API vive")
def salud():
    return {"estado": "ok"}
