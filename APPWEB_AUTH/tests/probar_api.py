"""Pruebas rápidas de la API (se ejecutan contra el servidor en :8000).

Incluye pruebas de autenticación JWT: registro, login, renovación con
refresh token (incluidos tokens caducados), aislamiento de la colección por
usuario y rechazo de peticiones sin token.

También cubre los permisos por rol (usuario/gestor/admin), el cambio de
contraseña propio y el restablecimiento por admin —con la invalidación de
todos los tokens anteriores— y el borrado de cuentas por parte de un admin.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
fallos = []

# Clave de firma (la misma que usa el backend si no se define en el entorno).
CLAVE_SECRETA = os.getenv(
    "LUDOTECA_SECRET_KEY", "ludoteca-clave-de-desarrollo-cambiala-en-produccion"
)

# Token global que se rellena al iniciar sesión (admin) y usan las peticiones.
TOKEN = None


def req(metodo, ruta, cuerpo=None, token="auto"):
    """Hace una petición.

    ``token="auto"`` usa el token global; ``token=None`` va sin cabecera
    (para probar el 401); cualquier otro valor se usa como token literal.
    """
    token_efectivo = TOKEN if token == "auto" else token
    cabeceras = {"Content-Type": "application/json"}
    if token_efectivo:
        cabeceras["Authorization"] = "Bearer " + token_efectivo

    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    r = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                               headers=cabeceras)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo_error = e.read().decode("utf-8")
        try:
            return e.code, json.loads(cuerpo_error)
        except json.JSONDecodeError:
            return e.code, {"detail": cuerpo_error}


def comprobar(nombre, condicion, extra=""):
    estado = "OK " if condicion else "FALLO"
    print(f"[{estado}] {nombre} {extra}")
    if not condicion:
        fallos.append(nombre)


def firmar_jwt(payload):
    """Firma un JWT a mano (HS256) para fabricar tokens caducados de prueba."""

    def b64(datos: bytes) -> str:
        return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()

    cabecera = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    cuerpo = b64(json.dumps(payload).encode())
    firma = b64(
        hmac.new(CLAVE_SECRETA.encode(), f"{cabecera}.{cuerpo}".encode(),
                 hashlib.sha256).digest()
    )
    return f"{cabecera}.{cuerpo}.{firma}"


# ---- General --------------------------------------------------------------
codigo, datos = req("GET", "/")
comprobar("GET / responde 200", codigo == 200)

codigo, datos = req("GET", "/api/salud")
comprobar("GET /api/salud ok", codigo == 200 and datos["estado"] == "ok")

# ---- Autenticación (JWT) --------------------------------------------------
codigo, datos = req("GET", "/api/videojuegos", token=None)
comprobar("Sin token -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("GET", "/api/videojuegos", token="token.invalido.xxx")
comprobar("Token inválido -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": "admin@ludoteca.local", "password": "malo"},
                    token=None)
comprobar("Login con contraseña incorrecta -> 401", codigo == 401,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": "admin@ludoteca.local", "password": "admin123"},
                    token=None)
comprobar("Login admin -> 200 y token", codigo == 200 and "access_token" in datos,
          f"codigo={codigo}")
TOKEN = datos.get("access_token")
REFRESH = datos.get("refresh_token")

# ---- Refresco del JWT (renovar la sesión sin pasar la contraseña) ---------
comprobar("Login devuelve refresh_token", bool(REFRESH),
          f"refresh={'si' if REFRESH else 'no'}")

codigo, refrescado = req("POST", "/api/auth/refresh", {"refresh_token": REFRESH},
                         token=None)
comprobar("Refresh -> 200 con par de tokens nuevo", codigo == 200
          and "access_token" in refrescado and refrescado.get("refresh_token")
          and refrescado.get("refresh_expira_en_segundos"),
          f"codigo={codigo}")
TOKEN = refrescado.get("access_token") or TOKEN
REFRESH = refrescado.get("refresh_token") or REFRESH

codigo, datos = req("GET", "/api/auth/yo")
comprobar("El access renovado funciona", codigo == 200
          and datos.get("email") == "admin@ludoteca.local", f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/refresh", {"refresh_token": TOKEN},
                    token=None)
comprobar("Un access token no sirve como refresh -> 401", codigo == 401,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/refresh", {"refresh_token": "token.basura.xxx"},
                    token=None)
comprobar("Refresh con token basura -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/refresh", {}, token=None)
comprobar("Refresh sin refresh_token -> 422", codigo == 422, f"codigo={codigo}")

# Tokens caducados (firmados aquí a mano con la misma clave del backend).
ahora = int(time.time())
access_caducado = firmar_jwt({"sub": "1", "tipo": "access",
                              "iat": ahora - 7200, "exp": ahora - 60})
codigo, datos = req("GET", "/api/auth/yo", token=access_caducado)
comprobar("Access caducado -> 401", codigo == 401, f"codigo={codigo}")

refresh_caducado = firmar_jwt({"sub": "1", "tipo": "refresh",
                               "iat": ahora - 7200, "exp": ahora - 60})
codigo, datos = req("POST", "/api/auth/refresh", {"refresh_token": refresh_caducado},
                    token=None)
comprobar("Refresh caducado -> 401 (hay que volver a entrar)", codigo == 401,
          f"codigo={codigo}")

codigo, datos = req("GET", "/api/auth/yo")
comprobar("GET /api/auth/yo devuelve el usuario", codigo == 200
          and datos.get("email") == "admin@ludoteca.local")

codigo, datos = req("POST", "/api/auth/registro",
                    {"nombre": "Copion", "email": "admin@ludoteca.local",
                     "password": "secreto123"}, token=None)
comprobar("Registro con email ya usado -> 409", codigo == 409, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/registro",
                    {"nombre": "X", "email": "no-es-email", "password": "secreto123"},
                    token=None)
comprobar("Registro con email no válido -> 422", codigo == 422, f"codigo={codigo}")

# Usuario de pruebas fijo: se registra la primera vez y luego se inicia sesión.
EMAIL_PRUEBA = "tester@ludoteca.local"
CLAVE_PRUEBA = "secreto123"
codigo, datos = req("POST", "/api/auth/registro",
                    {"nombre": "Tester", "email": EMAIL_PRUEBA,
                     "password": CLAVE_PRUEBA}, token=None)
if codigo == 409:
    codigo, datos = req("POST", "/api/auth/login",
                        {"email": EMAIL_PRUEBA, "password": CLAVE_PRUEBA},
                        token=None)
    comprobar("Usuario de pruebas listo (login)", codigo == 200, f"codigo={codigo}")
else:
    comprobar("Usuario de pruebas creado (registro 201)", codigo == 201,
              f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token")

codigo, datos = req("GET", "/api/colecciones", token=TOKEN_PRUEBA)
comprobar("Colección del usuario nuevo está vacía (aislamiento)", codigo == 200
          and datos["total"] == 0, f"total={datos.get('total')}")

# ---- Listados -------------------------------------------------------------
codigo, datos = req("GET", "/api/videojuegos")
comprobar("Listar videojuegos (>= 10 seed)", codigo == 200 and datos["total"] >= 10,
          f"total={datos.get('total')}")

codigo, datos = req("GET", "/api/videojuegos?q=zelda")
comprobar("Búsqueda q=zelda", datos["total"] == 1 and "Zelda" in datos["items"][0]["titulo"])

codigo, datos = req("GET", "/api/videojuegos?genero=RPG")
comprobar("Filtro genero=RPG", datos["total"] >= 3, f"total={datos['total']}")

codigo, datos = req("GET", "/api/videojuegos?genero=3&plataforma=PC")
comprobar("Filtro genero id=3 + plataforma PC", datos["total"] >= 1)

codigo, datos = req("GET", "/api/videojuegos?anio_desde=2020&orden=anio-desc")
comprobar("Filtro rango de años", all(
    i["anio_lanzamiento"] >= 2020 for i in datos["items"]))

codigo, datos = req("GET", "/api/videojuegos?desarrolladora=Nintendo")
comprobar("Filtro por desarrolladora", datos["total"] == 2, f"total={datos['total']}")

codigo, datos = req("GET", "/api/videojuegos?pagina=2&por_pagina=5")
comprobar("Paginación (página 2 de 5)", datos["pagina"] == 2 and len(datos["items"]) == 5)

# ---- CRUD videojuegos -----------------------------------------------------
nuevo = {
    "titulo": "Hollow Knight: Silksong",
    "descripcion": "Hornet viaja a Pharatum como cazadora en esta secuela del metroidvania.",
    "caratula_url": "https://placehold.co/600x800?text=Silksong",
    "anio_lanzamiento": 2025,
    "clasificacion": "PEGI 7",
    "puntuacion": 9.0,
    "desarrolladora_id": 3,
    "plataformas_ids": [1, 5],
    "generos_ids": [5, 6],
}
codigo, datos = req("POST", "/api/videojuegos", nuevo)
comprobar("POST crear videojuego 201", codigo == 201, f"codigo={codigo}")
id_vj = datos.get("id")

codigo, datos = req("GET", f"/api/videojuegos/{id_vj}")
comprobar("GET detalle con relaciones", codigo == 200 and len(datos["plataformas"]) == 2
          and datos["desarrolladora"]["nombre"] == "Team Cherry")

codigo, datos = req("PUT", f"/api/videojuegos/{id_vj}", {"puntuacion": 9.9, "titulo": "Hollow Knight: Silksong"})
comprobar("PUT actualizar parcial", codigo == 200 and datos["puntuacion"] == 9.9)

codigo, datos = req("PUT", f"/api/videojuegos/{id_vj}", {"plataformas_ids": [1]})
comprobar("PUT cambia plataformas", codigo == 200 and len(datos["plataformas"]) == 1)

codigo, datos = req("POST", "/api/videojuegos", {**nuevo, "desarrolladora_id": 999})
comprobar("POST con desarrolladora inexistente 404", codigo == 404, f"codigo={codigo}")

codigo, datos = req("POST", "/api/videojuegos", {**nuevo, "caratula_url": "no-es-url"})
comprobar("POST con caratula no-URL 422", codigo == 422, f"codigo={codigo}")

codigo, datos = req("GET", "/api/videojuegos/99999")
comprobar("GET inexistente 404", codigo == 404)

# ---- CRUD plataformas -----------------------------------------------------
codigo, datos = req("POST", "/api/plataformas", {"nombre": "Dreamcast", "fabricante": "Sega", "anio_lanzamiento": 1998})
comprobar("POST crear plataforma 201", codigo == 201, f"codigo={codigo}")
id_plataforma = datos["id"]

codigo, datos = req("POST", "/api/plataformas", {"nombre": "Dreamcast"})
comprobar("POST duplicado 409", codigo == 409, f"codigo={codigo}")

codigo, datos = req("PUT", f"/api/plataformas/{id_plataforma}", {"fabricante": "Sega (Corporation)"})
comprobar("PUT actualizar plataforma", codigo == 200 and "Corporation" in datos["fabricante"])

codigo, datos = req("DELETE", f"/api/plataformas/{id_plataforma}")
comprobar("DELETE plataforma libre 200", codigo == 200)

codigo, datos = req("DELETE", "/api/plataformas/5")
comprobar("DELETE plataforma en uso 409", codigo == 409, f"codigo={codigo}")

# ---- CRUD géneros ---------------------------------------------------------
codigo, datos = req("POST", "/api/generos", {"nombre": "Terror", "descripcion": "Miedo y supervivencia."})
comprobar("POST crear género 201", codigo == 201)
id_genero = datos["id"]

codigo, datos = req("DELETE", f"/api/generos/{id_genero}")
comprobar("DELETE género libre 200", codigo == 200)

codigo, datos = req("DELETE", "/api/generos/1")
comprobar("DELETE género en uso 409", codigo == 409)

codigo, datos = req("PUT", f"/api/generos/{id_genero}", {"nombre": "Terror"})
comprobar("PUT género eliminado 404", codigo == 404)

# ---- CRUD desarrolladoras -------------------------------------------------
codigo, datos = req("POST", "/api/desarrolladoras", {"nombre": "Larian Studios", "pais": "Bélgica", "web": "https://larian.com"})
comprobar("POST crear desarrolladora 201", codigo == 201)
id_dev = datos["id"]

codigo, datos = req("PUT", f"/api/desarrolladoras/{id_dev}", {"pais": "Bélgica (Gante)"})
comprobar("PUT actualizar desarrolladora", codigo == 200)

codigo, datos = req("DELETE", "/api/desarrolladoras/3")
comprobar("DELETE desarrolladora con juegos 409", codigo == 409)

codigo, datos = req("DELETE", f"/api/desarrolladoras/{id_dev}")
comprobar("DELETE desarrolladora libre 200", codigo == 200)

# ---- CRUD colección -------------------------------------------------------
codigo, datos = req("GET", "/api/colecciones")
comprobar("Listar colección (>= 6 seed)", codigo == 200 and datos["total"] >= 6,
          f"total={datos.get('total')}")

codigo, datos = req("GET", "/api/colecciones?favorito=true")
comprobar("Filtro favoritos", datos["total"] >= 3, f"total={datos['total']}")
favoritos_antes = datos["total"]

codigo, datos = req("GET", "/api/colecciones?estado=digital&valoracion_min=9")
comprobar("Filtro estado+valoración", datos["total"] >= 2, f"total={datos['total']}")

nuevo_item = {
    "videojuego_id": id_vj,
    "plataforma_id": 1,
    "estado": "nuevo",
    "fecha_compra": "2025-09-30",
    "precio_compra": 19.99,
    "valoracion": 9,
    "favorito": False,
    "notas": "Edición física con mapa.",
}
codigo, datos = req("POST", "/api/colecciones", nuevo_item)
comprobar("POST añadir a colección 201", codigo == 201, f"codigo={codigo}")
id_item = datos["id"]

codigo, datos = req("POST", "/api/colecciones", nuevo_item)
comprobar("POST duplicado 409", codigo == 409, f"codigo={codigo}")

codigo, datos = req("POST", "/api/colecciones", {"videojuego_id": 99999})
comprobar("POST con videojuego inexistente 404", codigo == 404)

codigo, datos = req("PUT", f"/api/colecciones/{id_item}", {"valoracion": 10, "estado": "como nuevo"})
comprobar("PUT actualizar ejemplar", codigo == 200 and datos["valoracion"] == 10)

codigo, datos = req("PATCH", f"/api/colecciones/{id_item}/favorito", {"favorito": True})
comprobar("PATCH marcar favorito", codigo == 200 and datos["favorito"] is True)

codigo, datos = req("GET", "/api/colecciones?favorito=true")
comprobar("Filtro favoritos ahora (antes + 1)", datos["total"] == favoritos_antes + 1,
          f"total={datos['total']}")

codigo, datos = req("DELETE", f"/api/colecciones/{id_item}")
comprobar("DELETE ejemplar 200", codigo == 200)

# ---- Estadísticas ---------------------------------------------------------
codigo, datos = req("GET", "/api/estadisticas/resumen")
comprobar("Resumen general", codigo == 200 and datos["videojuegos"] >= 10
          and datos["ejemplares_en_coleccion"] >= 6,
          f"={json.dumps(datos, ensure_ascii=False)}")

codigo, datos = req("GET", "/api/estadisticas/por-plataforma")
comprobar("Por plataforma", codigo == 200 and len(datos) >= 6
          and all("juegos" in d for d in datos))

codigo, datos = req("GET", "/api/estadisticas/por-genero")
comprobar("Por género", codigo == 200 and len(datos) >= 8)

codigo, datos = req("GET", "/api/estadisticas/por-estado")
comprobar("Por estado", codigo == 200 and len(datos) >= 3)

codigo, datos = req("GET", "/api/estadisticas/top-valoraciones")
comprobar("Top valoraciones", codigo == 200 and datos[0]["valoracion"] == 10
          and "videojuego" in datos[0])

# ---- Limpieza: borrar el videojuego creado (prueba cascade) ---------------
codigo, datos = req("DELETE", f"/api/videojuegos/{id_vj}")
comprobar("DELETE videojuego 200", codigo == 200)

codigo, datos = req("GET", f"/api/videojuegos/{id_vj}")
comprobar("Detalle tras borrar 404", codigo == 404)

# ---- Roles y administración de usuarios ----------------------------------
codigo, datos = req("GET", "/api/auth/yo")
comprobar("El admin tiene rol 'admin'", codigo == 200 and datos.get("rol") == "admin",
          f"rol={datos.get('rol')}")
comprobar("La respuesta de usuario incluye rol y es_admin",
          "rol" in datos and "es_admin" in datos)
id_admin = datos.get("id")

# Un usuario normal no puede escribir en el catálogo ni listar cuentas.
codigo, datos = req("POST", "/api/plataformas",
                    {"nombre": "Pippin", "fabricante": "Apple"},
                    token=TOKEN_PRUEBA)
comprobar("Usuario normal no puede crear plataforma -> 403", codigo == 403,
          f"codigo={codigo}")

codigo, datos = req("GET", "/api/usuarios", token=TOKEN_PRUEBA)
comprobar("Usuario normal no puede listar usuarios -> 403", codigo == 403,
          f"codigo={codigo}")

# El admin sí administra usuarios.
codigo, datos = req("GET", "/api/usuarios")
comprobar("Admin lista usuarios", codigo == 200 and datos["total"] >= 2,
          f"total={datos.get('total')}")

codigo, datos = req("GET", f"/api/usuarios?q={EMAIL_PRUEBA}")
comprobar("Admin busca usuario por email", codigo == 200 and datos["total"] == 1
          and datos["items"][0]["email"] == EMAIL_PRUEBA,
          f"total={datos.get('total')}")
id_tester = datos["items"][0]["id"] if datos.get("items") else None

# El admin no puede cambiarse su propio rol.
codigo, datos = req("PATCH", f"/api/usuarios/{id_admin}/rol", {"rol": "usuario"})
comprobar("Admin no puede cambiarse su propio rol -> 400", codigo == 400,
          f"codigo={codigo}")

# Promover al tester a gestor: ahora puede crear en el catálogo y ver usuarios.
codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/rol", {"rol": "gestor"})
comprobar("Admin cambia rol a gestor", codigo == 200 and datos["rol"] == "gestor",
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/plataformas",
                    {"nombre": "Pippin", "fabricante": "Apple"},
                    token=TOKEN_PRUEBA)
comprobar("Gestor puede crear plataforma", codigo == 201, f"codigo={codigo}")
if codigo == 201:
    req("DELETE", f"/api/plataformas/{datos['id']}", token=TOKEN_PRUEBA)

# El gestor puede consultar cuentas, pero no cambiar roles.
codigo, datos = req("GET", "/api/usuarios", token=TOKEN_PRUEBA)
comprobar("Gestor puede listar usuarios", codigo == 200 and datos.get("total", 0) >= 2,
          f"codigo={codigo}")

codigo, datos = req("GET", f"/api/usuarios/{id_admin}", token=TOKEN_PRUEBA)
comprobar("Gestor puede ver una cuenta", codigo == 200, f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_admin}/rol", {"rol": "usuario"},
                    token=TOKEN_PRUEBA)
comprobar("Gestor no puede cambiar roles -> 403", codigo == 403, f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/rol", {"rol": "usuario"})
comprobar("Restaurar rol del tester a usuario", codigo == 200 and datos["rol"] == "usuario")

# ---- Cambio de contraseña propio y restablecimiento por admin -------------
# Un usuario normal no puede tocar cuentas ajenas por ninguna de las dos vías.
codigo, datos = req("DELETE", f"/api/usuarios/{id_admin}", token=TOKEN_PRUEBA)
comprobar("Usuario normal no puede eliminar cuentas -> 403", codigo == 403,
          f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_admin}/password",
                    {"password_nueva": "clave-segura-1", "confirmar": "clave-segura-1"},
                    token=TOKEN_PRUEBA)
comprobar("Usuario normal no puede restablecer contraseñas -> 403", codigo == 403,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/cambiar-password", {}, token=None)
comprobar("Cambiar contraseña sin token -> 401", codigo == 401, f"codigo={codigo}")

# Sesión de partida del tester: se guardan access y refresh para comprobar
# después que el cambio de contraseña los anula a los dos.
codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": CLAVE_PRUEBA}, token=None)
comprobar("Login del tester antes de cambiar la clave", codigo == 200,
          f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token")
REFRESH_PRUEBA = datos.get("refresh_token")

# El gestor consulta cuentas, pero tampoco borra ni toca contraseñas.
codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/rol", {"rol": "gestor"})
comprobar("Se promueve a gestor para los controles de permisos",
          codigo == 200 and datos["rol"] == "gestor", f"codigo={codigo}")

codigo, datos = req("DELETE", f"/api/usuarios/{id_admin}", token=TOKEN_PRUEBA)
comprobar("Gestor no puede eliminar cuentas -> 403", codigo == 403, f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_admin}/password",
                    {"password_nueva": "clave-segura-1", "confirmar": "clave-segura-1"},
                    token=TOKEN_PRUEBA)
comprobar("Gestor no puede restablecer contraseñas -> 403", codigo == 403,
          f"codigo={codigo}")

# Cambio propio: pide la actual y exige que la confirmación cuadre.
CLAVE_NUEVA = "clave-nueva-123"
codigo, datos = req("POST", "/api/auth/cambiar-password",
                    {"password_actual": "esta-no-es", "password_nueva": CLAVE_NUEVA,
                     "confirmar": CLAVE_NUEVA}, token=TOKEN_PRUEBA)
comprobar("Contraseña actual incorrecta -> 400", codigo == 400, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/cambiar-password",
                    {"password_actual": CLAVE_PRUEBA, "password_nueva": CLAVE_NUEVA,
                     "confirmar": "distinta-otra"}, token=TOKEN_PRUEBA)
comprobar("Confirmación que no coincide -> 422", codigo == 422, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/cambiar-password",
                    {"password_actual": CLAVE_PRUEBA, "password_nueva": CLAVE_PRUEBA,
                     "confirmar": CLAVE_PRUEBA}, token=TOKEN_PRUEBA)
comprobar("La contraseña nueva no puede ser la misma -> 422", codigo == 422,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/cambiar-password",
                    {"password_actual": CLAVE_PRUEBA, "password_nueva": CLAVE_NUEVA,
                     "confirmar": CLAVE_NUEVA}, token=TOKEN_PRUEBA)
comprobar("Cambio de contraseña -> 200 con tokens nuevos",
          codigo == 200 and "access_token" in datos and "refresh_token" in datos,
          f"codigo={codigo}")
TOKEN_CAMBIADO = datos.get("access_token")
REFRESH_CAMBIADO = datos.get("refresh_token")

# La medida de seguridad: los tokens emitidos hasta ese momento mueren.
codigo, datos = req("GET", "/api/auth/yo", token=TOKEN_PRUEBA)
comprobar("El access anterior muere al cambiar la clave -> 401", codigo == 401,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/refresh", {"refresh_token": REFRESH_PRUEBA},
                    token=None)
comprobar("El refresh anterior también muere -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("GET", "/api/auth/yo", token=TOKEN_CAMBIADO)
comprobar("Los tokens recién emitidos siguen vivos -> 200", codigo == 200,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": CLAVE_PRUEBA}, token=None)
comprobar("Login con la contraseña antigua -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": CLAVE_NUEVA}, token=None)
comprobar("Login con la contraseña nueva -> 200", codigo == 200, f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token") or TOKEN_CAMBIADO

# Se restaura la contraseña original para el resto de pruebas.
codigo, datos = req("POST", "/api/auth/cambiar-password",
                    {"password_actual": CLAVE_NUEVA, "password_nueva": CLAVE_PRUEBA,
                     "confirmar": CLAVE_PRUEBA}, token=TOKEN_PRUEBA)
comprobar("Se restaura la contraseña del tester", codigo == 200, f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token")

# Restablecimiento por admin: no pide la actual (proceso de recuperación).
codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/password",
                    {"password_nueva": "recuperada-123", "confirmar": "recuperada-123"})
comprobar("Admin restablece la contraseña del tester -> 200",
          codigo == 200 and datos.get("email") == EMAIL_PRUEBA, f"codigo={codigo}")

codigo, datos = req("GET", "/api/auth/yo", token=TOKEN_PRUEBA)
comprobar("El restablecimiento cierra las sesiones del tester -> 401",
          codigo == 401, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": CLAVE_PRUEBA}, token=None)
comprobar("El tester ya no entra con la clave vieja -> 401", codigo == 401,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": "recuperada-123"}, token=None)
comprobar("...pero sí con la restablecida -> 200", codigo == 200, f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token")

# El admin no se restablece la suya por esta vía: para eso está el flujo
# propio que exige conocer la contraseña actual.
codigo, datos = req("PATCH", f"/api/usuarios/{id_admin}/password",
                    {"password_nueva": "otra-clave-999", "confirmar": "otra-clave-999"})
comprobar("Admin no se restablece a sí mismo por este endpoint -> 400",
          codigo == 400, f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/password",
                    {"password_nueva": CLAVE_PRUEBA, "confirmar": CLAVE_PRUEBA})
comprobar("Se devuelve la contraseña original del tester", codigo == 200,
          f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_PRUEBA, "password": CLAVE_PRUEBA}, token=None)
comprobar("El tester vuelve a entrar con su clave", codigo == 200, f"codigo={codigo}")
TOKEN_PRUEBA = datos.get("access_token")

# ---- Borrado de cuentas (solo admin) -------------------------------------
codigo, datos = req("DELETE", f"/api/usuarios/{id_admin}")
comprobar("Un admin no puede eliminarse a sí mismo -> 400", codigo == 400,
          f"codigo={codigo}")

codigo, datos = req("DELETE", "/api/usuarios/99999")
comprobar("Eliminar cuenta inexistente -> 404", codigo == 404, f"codigo={codigo}")

# Cuenta desechable con un ejemplar: el borrado debe arrastrar su colección.
EMAIL_BORRABLE = "borrable@ludoteca.local"
CLAVE_BORRABLE = "borrame-123"
codigo, datos = req("POST", "/api/auth/registro",
                    {"nombre": "Borrable", "email": EMAIL_BORRABLE,
                     "password": CLAVE_BORRABLE}, token=None)
if codigo == 409:
    # Ya quedó de una ejecución anterior: el admin le recupera la clave.
    codigo, lista = req("GET", f"/api/usuarios?q={EMAIL_BORRABLE}")
    id_borrable = lista["items"][0]["id"] if lista.get("items") else None
    req("PATCH", f"/api/usuarios/{id_borrable}/password",
        {"password_nueva": CLAVE_BORRABLE, "confirmar": CLAVE_BORRABLE})
    codigo, datos = req("POST", "/api/auth/login",
                        {"email": EMAIL_BORRABLE, "password": CLAVE_BORRABLE},
                        token=None)
comprobar("Cuenta desechable lista (registro o recuperación)",
          codigo in (200, 201), f"codigo={codigo}")
TOKEN_BORRABLE = datos.get("access_token")
id_borrable = datos["usuario"]["id"]

codigo, datos = req("POST", "/api/colecciones",
                    {"videojuego_id": 1, "plataforma_id": 1}, token=TOKEN_BORRABLE)
comprobar("La cuenta desechable añade un ejemplar a su colección",
          codigo == 201, f"codigo={codigo}")

codigo, datos = req("DELETE", f"/api/usuarios/{id_borrable}")
comprobar("Admin elimina la cuenta -> 200 avisando del borrado en cascada",
          codigo == 200 and datos.get("ejemplares_eliminados", 0) >= 1,
          f"datos={datos}")

codigo, datos = req("GET", f"/api/usuarios/{id_borrable}")
comprobar("La cuenta eliminada ya no existe -> 404", codigo == 404, f"codigo={codigo}")

codigo, datos = req("POST", "/api/auth/login",
                    {"email": EMAIL_BORRABLE, "password": CLAVE_BORRABLE}, token=None)
comprobar("Login de la cuenta borrada -> 401", codigo == 401, f"codigo={codigo}")

codigo, datos = req("GET", "/api/auth/yo", token=TOKEN_BORRABLE)
comprobar("Sus tokens mueren con la cuenta -> 401", codigo == 401, f"codigo={codigo}")

# El permiso se exige antes que la existencia: el gestor no borra nada.
codigo, datos = req("DELETE", f"/api/usuarios/{id_borrable}", token=TOKEN_PRUEBA)
comprobar("Gestor que intenta borrar recibe 403 (no 404)", codigo == 403,
          f"codigo={codigo}")

codigo, datos = req("PATCH", f"/api/usuarios/{id_tester}/rol", {"rol": "usuario"})
comprobar("Restaurar rol del tester (cierre)", codigo == 200 and datos["rol"] == "usuario")

print()
if fallos:
    print(f"RESULTADO: {len(fallos)} fallo(s): {fallos}")
    sys.exit(1)
print("RESULTADO: todas las pruebas pasaron [OK]")
