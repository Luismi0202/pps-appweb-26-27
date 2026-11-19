# Ejercicio 3 – Soporte DevOps: pruebas funcionales, de estrés y anti-DDoS (APPWEB_AUTH)

**Autor:** Luis Miguel Gomila Domínguez
**Aplicación:** API Colección de Videojuegos + panel web "Ludoteca" ([`APPWEB_AUTH`](./APPWEB_AUTH))
**Fecha de las pruebas:** 19 de noviembre de 2026

Este documento explica **cómo se ha ido montando el soporte DevOps** de la
aplicación (código, control de versiones, pruebas, integración continua y
despliegue), y en concreto **la parte de pruebas funcionales (Selenium) y de
estrés (Locust)**: cómo están hechas, cómo se ejecutan y qué resultados han
dado al probarlas.

> **Enunciado del ejercicio 3**
> - Crear test funcionales de la aplicación web (Selenium, Playwright, etc.).
> - Crear test de estrés de la aplicación, repartidos entre el despliegue
>   local y el de producción. Se pueden introducir pruebas para evitar
>   ataques DDoS.

### Dónde está cada cosa

| Requisito | Sección | Código de las pruebas | Resultados |
|-----------|---------|-----------------------|------------|
| Test funcionales (Selenium) | [§4](#4-pruebas-funcionales-con-selenium) | [`tests/funcionales/`](./APPWEB_AUTH/tests/funcionales/) · [`paginas.py`](./APPWEB_AUTH/tests/funcionales/paginas.py) · [`test_autenticacion.py`](./APPWEB_AUTH/tests/funcionales/test_autenticacion.py) · [`test_panel.py`](./APPWEB_AUTH/tests/funcionales/test_panel.py) · [`test_oauth_navegador.py`](./APPWEB_AUTH/tests/funcionales/test_oauth_navegador.py) | [§4.4](#44-resultados-obtenidos) |
| Test de la API (contrato HTTP) | [§4](#4-pruebas-funcionales-con-selenium) | [`tests/probar_api.py`](./APPWEB_AUTH/tests/probar_api.py) · [`tests/oauth/test_oauth.py`](./APPWEB_AUTH/tests/oauth/test_oauth.py) | [§4.4](#44-resultados-obtenidos) |
| Estrés en **local** | [§5](#5-pruebas-de-carga-y-estrés-con-locust) | [`tests/estres/locustfile.py`](./APPWEB_AUTH/tests/estres/locustfile.py) · [`tests/servidor_aislado.py`](./APPWEB_AUTH/tests/servidor_aislado.py) | [§5.4](#54-resultados-obtenidos) · [`resultados/`](./APPWEB_AUTH/tests/estres/resultados/) |
| Estrés en **producción** (Render) | [§6](#6-pruebas-de-carga-en-producción-render) | [`tests/estres/locustfile_produccion.py`](./APPWEB_AUTH/tests/estres/locustfile_produccion.py) · [`tests/ddos/rafaga.py`](./APPWEB_AUTH/tests/ddos/rafaga.py) | [§6.3](#63-resultados-obtenidos) |
| Protección y pruebas **anti-DDoS** | [§7](#7-protección-y-pruebas-anti-ddos) | [`app/anti_ddos.py`](./APPWEB_AUTH/app/anti_ddos.py) · [`tests/ddos/test_anti_ddos.py`](./APPWEB_AUTH/tests/ddos/test_anti_ddos.py) · [`tests/estres/locustfile_ddos.py`](./APPWEB_AUTH/tests/estres/locustfile_ddos.py) · [`tests/ddos/rafaga.py`](./APPWEB_AUTH/tests/ddos/rafaga.py) | [§7.4](#74-resultados-obtenidos) |
| Automatización (CI) | [§8](#8-integración-continua-github-actions) | [`.github/workflows/pruebas-appweb.yml`](./.github/workflows/pruebas-appweb.yml) · [`pytest.ini`](./APPWEB_AUTH/pytest.ini) · [`requirements-test.txt`](./APPWEB_AUTH/requirements-test.txt) | Pestaña *Actions* de GitHub |

---

## Índice

1. [Qué es la aplicación](#1-qué-es-la-aplicación)
2. [Estructura DevOps del proyecto](#2-estructura-devops-del-proyecto)
3. [Cómo se ha ido construyendo (fases)](#3-cómo-se-ha-ido-construyendo-fases)
4. [Pruebas funcionales con Selenium](#4-pruebas-funcionales-con-selenium)
5. [Pruebas de carga y estrés con Locust (local)](#5-pruebas-de-carga-y-estrés-con-locust)
6. [Pruebas de carga en producción (Render)](#6-pruebas-de-carga-en-producción-render)
7. [Protección y pruebas anti-DDoS](#7-protección-y-pruebas-anti-ddos)
8. [Integración continua (GitHub Actions)](#8-integración-continua-github-actions)
9. [Conclusiones y mejoras propuestas](#9-conclusiones-y-mejoras-propuestas)

---

## 1. Qué es la aplicación

| Capa | Tecnología | Dónde está |
|------|------------|------------|
| Backend / API REST | Python 3 + **FastAPI** servido con **Uvicorn** | `APPWEB_AUTH/app/` |
| Base de datos | **SQLite** (archivo `coleccion_videojuegos.db`) con **SQLAlchemy 2** | `APPWEB_AUTH/app/database.py` |
| Seguridad | **JWT** (access + refresh, HS256) y contraseñas con **bcrypt**; roles `usuario` / `gestor` / `admin` | `APPWEB_AUTH/app/seguridad.py`, `routers/auth.py` |
| Frontend | HTML + CSS + JavaScript sin framework, servido por la propia API en `/panel` | `APPWEB_AUTH/frontend/` |
| Despliegue | **Render** (plan gratuito) → <https://pps-appweb-26-27-sju7.onrender.com> | ver [comparativa](./COMPARATIVA_PRESUPUESTOS_APLICACION_WEB_DESPLEGADA.md) |

Un único proceso sirve la API **y** el panel, así que para probar la aplicación
de extremo a extremo basta con levantar Uvicorn.

---

## 2. Estructura DevOps del proyecto

### 2.1 Mapa del repositorio

```
pps-ciberseguridad-trabajos-pps-26-27-luismi0202/
├── .github/workflows/
│   └── pruebas-appweb.yml          # CI: API + Selenium + carga corta (GitHub Actions)
├── APPWEB_AUTH/
│   ├── app/                        # Código de la API (FastAPI)
│   │   ├── anti_ddos.py            #   Middleware anti-DDoS (límites por IP, 429/413)
│   │   └── routers/oauth.py        #   Login con Google/GitHub
│   ├── frontend/                   # Panel web "Ludoteca"
│   ├── tests/
│   │   ├── probar_api.py           # Batería de ~110 comprobaciones de la API (HTTP)
│   │   ├── servidor_aislado.py     # Levanta la API con una BD temporal (no toca la del repo)
│   │   ├── funcionales/            # Pruebas end-to-end con Selenium + pytest
│   │   │   ├── conftest.py         #   fixtures: servidor, navegador, sesiones
│   │   │   ├── paginas.py          #   Page Objects (selectores del panel)
│   │   │   ├── test_autenticacion.py
│   │   │   ├── test_panel.py
│   │   │   └── test_oauth_navegador.py
│   │   ├── oauth/test_oauth.py     # Login con Google/GitHub (proveedores simulados)
│   │   ├── ddos/
│   │   │   ├── test_anti_ddos.py   # Pruebas de la protección anti-DDoS (pytest)
│   │   │   └── rafaga.py           # Ráfaga de peticiones (local o producción)
│   │   └── estres/
│   │       ├── locustfile.py             # Carga/estrés en local (3 perfiles)
│   │       ├── locustfile_produccion.py  # Carga en producción (Render), solo lecturas
│   │       ├── locustfile_ddos.py        # Ataque simulado vs. usuarios legítimos (local)
│   │       └── resultados/               # CSV + informes HTML de las ejecuciones documentadas
│   ├── pytest.ini                  # Configuración de pytest
│   ├── requirements.txt            # Dependencias de producción
│   ├── requirements-test.txt       # Dependencias solo de pruebas
│   ├── postman_collection.json     # Pruebas manuales/exploratorias de la API
│   └── coleccion_videojuegos.db    # BD de demostración que se despliega
├── COMPARATIVA_PRESUPUESTOS_APLICACION_WEB_DESPLEGADA.md
├── DEVOPS_Y_PRUEBAS.md             # (este documento)
└── README.md
```

### 2.2 El ciclo DevOps aplicado

```
  PLAN ──► CODE ──► BUILD ──► TEST ──► RELEASE ──► DEPLOY ──► OPERATE ──► MONITOR
   │        │        │         │         │           │          │            │
 README   FastAPI  pip install pytest+   push a     Render     Render     /api/salud
 (roles,  + panel  requirements Selenium  main       (auto-     free      + Locust
 endpoints)        .txt       + Locust  (GitHub)   deploy)    plan       (rendimiento)
                              + probar_api
                              en GitHub Actions
```

| Fase | Qué se usa | Cómo se ha hecho |
|------|-----------|------------------|
| **Plan** | README + tabla de roles y endpoints | Se definieron primero los apartados (CRUD de 7 recursos, auth, roles) y se documentaron en el README antes de cerrarlos. |
| **Code** | Git + GitHub | Commits pequeños por funcionalidad (ver §3). Dos remotos: `origin` (repositorio de entrega del IES) y `PERSONAL` (`Luismi0202/pps-appweb-26-27`, el que se conecta al hosting). |
| **Build** | `requirements.txt` | No hay compilación: el "build" es instalar dependencias con `pip`. Las de pruebas están separadas en `requirements-test.txt` para que producción no cargue Selenium ni Locust. |
| **Test** | `probar_api.py`, **Selenium**, **Locust** | Cuatro niveles: API (contrato HTTP), funcional (navegador real), rendimiento (carga/estrés en local y en producción) y seguridad frente a DoS/DDoS. Detalle en §4–§7. |
| **Release** | rama `main` | `main` es la rama desplegable; todo lo que llega ahí debe pasar las pruebas (§8). |
| **Deploy** | **Render** | Servicio web de Python conectado al repositorio `PERSONAL`; con el *auto-deploy* de Render cada push a `main` redespliega (§3.2). |
| **Operate** | Render (plan Free) | Duerme a los 15 min sin tráfico; disco efímero (la SQLite vuelve a la versión del repo al redesplegar). |
| **Monitor** | `GET /api/salud`, logs de Render, Locust | El panel muestra "API conectada" consultando `/api/salud` (la misma ruta sirve como *health check* de Render); Locust mide tiempos de respuesta. |

### 2.3 Entornos

| Entorno | Cómo se levanta | Base de datos | Para qué |
|---------|-----------------|---------------|----------|
| **Desarrollo** | `python -m uvicorn app.main:app --reload --port 8000` | `APPWEB_AUTH/coleccion_videojuegos.db` | Programar y probar a mano |
| **Pruebas (aislado)** | `python tests/servidor_aislado.py --port 8765` (o automáticamente desde pytest) | BD **temporal** creada desde cero con el *seed* y borrada al acabar | Pruebas automáticas reproducibles; nunca se ensucia la BD versionada |
| **CI** | GitHub Actions (`ubuntu-latest`, Python 3.12, Chrome) | BD temporal | Puerta de calidad en cada push/PR |
| **Producción (demo)** | Render | Copia del `.db` del repo (efímera en plan Free) | Uso público |

> 💡 **Decisión de diseño:** la app abre `sqlite:///./coleccion_videojuegos.db`
> (ruta relativa al directorio de trabajo). `servidor_aislado.py` aprovecha eso
> arrancando Uvicorn dentro de una carpeta temporal con `--app-dir` apuntando al
> código: así las pruebas **no necesitan modificar el código de la aplicación**
> y siempre empiezan con los mismos datos (10 juegos, 6 plataformas, 8 géneros,
> cuenta `admin@ludoteca.local`).

### 2.4 Configuración por variables de entorno

| Variable | Uso | Valor en pruebas |
|----------|-----|------------------|
| `LUDOTECA_SECRET_KEY` | Clave de firma de los JWT | `clave-solo-para-pruebas-automaticas` (la pone `servidor_aislado.py`) |
| `LUDOTECA_TOKEN_MINUTOS` / `LUDOTECA_REFRESH_MINUTOS` | Caducidad de tokens | Por defecto (480 / 10080) |
| `LUDOTECA_BASE_URL` | Si se define, las pruebas Selenium van contra ese servidor en vez de levantar uno | Sin definir (servidor aislado) |
| `LUDOTECA_HEADLESS` | `0` para ver el navegador mientras se prueba | `1` (sin ventana) |
| `LUDOTECA_ADMIN_EMAIL` / `LUDOTECA_ADMIN_PASSWORD` | Cuenta que usa Locust | Cuenta de ejemplo del seed |
| `LUDOTECA_ANTI_DDOS` | `0` desactiva la protección anti-DDoS (§7) | `0` en el servidor aislado salvo con `--anti-ddos` |
| `LUDOTECA_LIMITE_GENERAL` / `LUDOTECA_LIMITE_AUTH` | Peticiones por minuto e IP (general / login-registro) | Por defecto 300 / 20 |
| `LUDOTECA_MAX_CUERPO_KB` | Tamaño máximo del cuerpo (413 si se supera) | Por defecto 1024 |
| `LUDOTECA_PROXIES_CONFIABLES` | Nº de proxies delante (para leer la IP real de `X-Forwarded-For`) | `0` (`1` con `--proxies 1`) |
| `LUDOTECA_PROD_EMAIL` / `LUDOTECA_PROD_PASSWORD` | Cuenta opcional para la carga autenticada en producción | Sin definir (carga anónima) |

---

## 3. Cómo se ha ido construyendo (fases)

El soporte DevOps no se montó de golpe, sino por capas, cada una apoyándose en
la anterior. El historial de Git lo refleja:

| Fase | Fecha | Commit(s) | Qué se añadió al soporte DevOps |
|------|-------|-----------|----------------------------------|
| **0. Repositorio y código base** | 18/10/2026 | `939ec89`, `a6d986d` | API FastAPI + panel, `requirements.txt`, README con arranque rápido, colección de **Postman** y la batería `tests/probar_api.py`. Primer nivel de pruebas: **contrato de la API** por HTTP. |
| **1. Iteración de funcionalidades** | 18/10/2026 | `49a8151`, `500d386` | Cambio de contraseña y borrado de usuarios, con sus pruebas añadidas a `probar_api.py` (versión de token, 403 por rol…). Primer *merge* entre la copia local y el remoto: se trabaja con ramas remotas. |
| **2. Documentación integrada** | 19/10/2026 | `e880b92` | Páginas `documentacion.html` y `api.html` dentro del propio panel. Es el commit que se sube también al remoto `PERSONAL`, desde el que se publica en Render. |
| **3. Despliegue y costes** | 04/11/2026 | `ede4f52`, `13582a0` | Despliegue en **Render**, enlace público y [comparativa de presupuestos](./COMPARATIVA_PRESUPUESTOS_APLICACION_WEB_DESPLEGADA.md) de hosting (Render, VPS, PaaS…). |
| **4. Pruebas funcionales y de estrés + CI** | 19/11/2026 | *(este trabajo)* | Entorno de pruebas aislado, **Selenium** (18 casos E2E), **Locust** (3 perfiles, 6 escenarios locales), pipeline de **GitHub Actions** y este documento. |
| **5. Login con Google y GitHub** | 19/11/2026 | *(este trabajo)* | Nueva forma de entrar con los mismos JWT, con sus pruebas (18 de API con proveedores simulados + 5 Selenium) metidas en la misma suite y en el CI. |
| **6. Producción y anti-DDoS** | 19/11/2026 | *(este trabajo)* | Carga contra **Render**, middleware **anti-DDoS** (límites por IP, 429/413) con 12 pruebas pytest, escenario de **ataque simulado** con Locust y mitigación del bloqueo con `--limit-concurrency`. |

### 3.1 Flujo de trabajo con Git y los dos remotos

```
         (desarrollo local)
   main ──●──●──●──●──●──●──●──►
              │           │
   git push origin main   git push PERSONAL main
              ▼           ▼
  IES-Rafael-Alberti/…   Luismi0202/pps-appweb-26-27
  (entrega + CI)          (repositorio vigilado por Render)
                              │ auto-deploy
                              ▼
                   pps-appweb-26-27-sju7.onrender.com
```

- `origin` → repositorio del IES donde se entregan los trabajos. Aquí vive el
  workflow de GitHub Actions (§8).
- `PERSONAL` → repositorio propio, con el mismo nombre que el servicio de
  Render. Al hacer `git push PERSONAL main`, Render vuelve a construir y
  publicar la app.

### 3.2 Configuración del servicio en Render

Render no necesita Dockerfile para Python: se configura en su panel con
(valores de referencia para esta app; revisa que coinciden con los de tu
servicio):

| Ajuste | Valor |
|--------|-------|
| Runtime | Python 3 |
| Root directory | `APPWEB_AUTH` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/salud` (recomendado) |
| Variables de entorno | `LUDOTECA_SECRET_KEY` (clave propia, **no** la de desarrollo) |
| Auto-deploy | Activado sobre `main` |

> Si se quisiera tener esta configuración como código (*Infrastructure as
> Code*), se podría añadir un `render.yaml` (Blueprint) al repositorio; ahora
> mismo está definida en el panel de Render.

---

## 4. Pruebas funcionales con Selenium

### 4.1 Enfoque

Las pruebas funcionales (*end-to-end*) manejan **un Chrome real** con
**Selenium WebDriver**, como lo haría una persona: escriben en los formularios,
pulsan botones, aceptan los `confirm()` y comprueban lo que se ve en pantalla.
Se organizan con **pytest** y el patrón **Page Object**:

| Archivo | Papel |
|---------|-------|
| `tests/funcionales/conftest.py` | *Fixtures*: arranca el servidor aislado (una vez por sesión), abre Chrome (uno por prueba, para que no se compartan `localStorage` ni sesiones), y deja sesiones listas: `panel_admin` (entra con la cuenta admin) y `panel_usuario` (registra una cuenta nueva con email aleatorio). Guarda captura si una prueba falla. |
| `tests/funcionales/paginas.py` | Page Objects `PantallaLogin` y `Panel`: todos los selectores CSS (`#form-login`, `#grid-catalogo`, `#usuario-rol`…) están aquí. Si cambia el HTML, solo se toca este archivo. |
| `tests/funcionales/test_autenticacion.py` | Login, registro, roles visibles, cierre de sesión y cambio de contraseña. |
| `tests/funcionales/test_panel.py` | Catálogo, búsqueda, filtros, ficha, colección, estadísticas, usuarios y CRUD de juegos. |

Las esperas son **explícitas** (`WebDriverWait`) en vez de `sleep`: el panel
carga todo con `fetch` y la búsqueda tiene *debounce* de 350 ms, así que se
espera a que desaparezcan los *skeletons* de carga, a que salga un *toast* o a
que cambie la URL.

### 4.2 Casos de prueba

| # | Prueba | Qué comprueba |
|---|--------|---------------|
| 1 | `test_panel_sin_sesion_redirige_al_login` | Entrar a `/panel/` sin token redirige a `login.html`. |
| 2 | `test_login_con_password_incorrecta_muestra_error` | Credenciales malas → aviso visible, sigue en login y **no** se guarda token. |
| 3 | `test_login_admin_entra_al_panel_con_permisos` | Admin entra, ve su nombre y rol "Administrador", el botón **＋ Nuevo juego** y la pestaña **Usuarios**; en `localStorage` hay access y refresh JWT. |
| 4 | `test_registro_crea_cuenta_con_rol_usuario` | Registro desde el formulario → entra con rol "Usuario" y **sin** opciones de gestión. |
| 5 | `test_registro_con_email_duplicado_muestra_error` | Registrar un email existente muestra el error de la API (409). |
| 6 | `test_cerrar_sesion_borra_tokens` | "Salir" + confirmar → vuelve al login y borra los tokens. |
| 7 | `test_cambiar_password_y_volver_a_entrar` | Cambia la contraseña desde 🔑, cierra sesión, la **antigua ya no vale** y la nueva sí. |
| 8 | `test_cambiar_password_sin_coincidir_no_envia` | Si la confirmación no coincide, avisa y no cierra el modal. |
| 9 | `test_catalogo_muestra_los_juegos` | El catálogo pinta los 10 juegos del seed y el contador coincide. |
| 10 | `test_busqueda_por_titulo` | Buscar "mario" deja solo *Super Mario Odyssey*. |
| 11 | `test_busqueda_sin_resultados` | Búsqueda sin coincidencias → contador 0 y mensaje "No hay juegos…". |
| 12 | `test_filtro_por_genero` | Filtro *Metroidvania* incluye *Hollow Knight* y excluye *Minecraft*. |
| 13 | `test_abrir_ficha_de_un_juego` | La ficha de *Hades* muestra su desarrolladora y, al admin, el botón Editar. |
| 14 | `test_usuario_no_ve_acciones_de_gestion_en_la_ficha` | Un usuario normal no ve Editar ni Eliminar en la ficha. |
| 15 | `test_usuario_anade_un_juego_a_su_coleccion` | Colección vacía → añade *Celeste* desde la ficha → aparece en "Mi colección" y el KPI de inversión marca 19.99 €. |
| 16 | `test_estadisticas_se_pintan` | La pestaña Estadísticas pinta los 6 KPIs, gráficos y el top. |
| 17 | `test_admin_ve_la_lista_de_usuarios` | La pestaña Usuarios lista cuentas (incluida la del admin). |
| 18 | `test_admin_crea_y_elimina_un_juego` | El admin crea un juego con el formulario, lo encuentra buscando, lo borra desde la ficha (aceptando el `confirm`) y desaparece. |

#### Login con Google y GitHub (añadido después)

Al incorporar el login social se añadieron dos grupos de pruebas, que corren
con el mismo `python -m pytest`:

- `tests/oauth/test_oauth.py` (18 pruebas, ~7 s): la app real con
  `TestClient` y BD temporal, **simulando** Google y GitHub (se sustituye la
  función que les hace las peticiones). Cubre la redirección al proveedor,
  alta de usuario nuevo, reutilización y vinculación por email, que los JWT
  emitidos funcionan en `/api/auth/yo`, colecciones y refresh, email sin
  verificar, `state` manipulado / de otro proveedor / sin cookie (CSRF),
  cancelación, cookie `Secure` en https, proveedor desconocido o sin configurar y borrado en cascada.
- `tests/funcionales/test_oauth_navegador.py` (5 pruebas Selenium): botones
  ocultos sin configuración y visibles (con su enlace) con ella, que el botón
  lleva a `github.com/login/oauth/authorize`, y que la vuelta
  `#oauth=<tokens>` entra al panel (y limpia la URL) y `#oauth_error=` muestra
  el aviso.

Resultado: **41 de 41 pruebas pasan** (18 OAuth + 23 Selenium) y
`probar_api.py` sigue pasando entero, también arrancando sobre una copia de la
BD real del repositorio (la tabla `cuentas_oauth` se crea sola y no se pierde
ningún usuario). El viaje real a Google/GitHub no se automatiza porque exige
cuentas y credenciales reales: se prueba a mano una vez configuradas.

### 4.3 Cómo ejecutarlas

Requisitos: Python 3.10+ y Google Chrome instalado (el driver lo descarga
Selenium Manager solo).

```powershell
cd APPWEB_AUTH
pip install -r requirements-test.txt
```

```powershell
python -m pytest
```

Variantes útiles:

```powershell
$env:LUDOTECA_HEADLESS = "0"; python -m pytest -k coleccion   # ver el navegador
```

```powershell
$env:LUDOTECA_BASE_URL = "https://pps-appweb-26-27-sju7.onrender.com"; python -m pytest   # contra Render
```

> Contra Render conviene "despertar" antes el servicio (plan Free) visitando
> `/api/salud`, y hay que tener en cuenta que las pruebas **crean cuentas y un
> juego temporal** en esa base de datos (el juego lo borran ellas mismas).

### 4.4 Resultados obtenidos

**Ejecución final (19/11/2026, Chrome 156 headless, servidor aislado local):**

```
tests/funcionales/test_autenticacion.py ........  (8 passed)
tests/funcionales/test_panel.py ..........        (10 passed)
======================= 18 passed in 110.05s (0:01:50) ========================
```

| Prueba | Tiempo | Prueba | Tiempo |
|--------|-------:|--------|-------:|
| panel_sin_sesion_redirige_al_login | 6,7 s | catalogo_muestra_los_juegos | 5,2 s |
| login_con_password_incorrecta | 4,7 s | busqueda_por_titulo | 5,9 s |
| login_admin_entra_al_panel | 5,2 s | busqueda_sin_resultados | 5,9 s |
| registro_crea_cuenta_con_rol_usuario | 5,4 s | filtro_por_genero | 5,9 s |
| registro_con_email_duplicado | 4,2 s | abrir_ficha_de_un_juego | 5,9 s |
| cerrar_sesion_borra_tokens | 5,4 s | usuario_no_ve_acciones_de_gestion | 6,6 s |
| cambiar_password_y_volver_a_entrar | 9,0 s | usuario_anade_juego_a_coleccion | 7,4 s |
| cambiar_password_sin_coincidir | 6,2 s | estadisticas_se_pintan | 6,5 s |
| | | admin_ve_la_lista_de_usuarios | 5,5 s |
| | | admin_crea_y_elimina_un_juego | 8,4 s |

Antes, en el mismo servidor, la batería de la API dio
`RESULTADO: todas las pruebas pasaron [OK]` (**110 de 110 comprobaciones**).

**Incidencias encontradas durante la puesta a punto** (todas eran de la propia
prueba, no de la aplicación, y se corrigieron en los Page Objects):

| Fallo en la 1.ª ejecución | Causa | Solución |
|---------------------------|-------|----------|
| `assert 'ADMINISTRADOR' == 'Administrador'` | El chip de rol tiene `text-transform: uppercase`; Selenium devuelve el texto **tal como se ve**. | Leer `textContent` en lugar de `.text`. |
| `ElementNotInteractableException` al crear juego | Los checkbox de plataformas/géneros están ocultos con `display:none` y se pulsa su "chip". | Hacer click en el `<span>` de la etiqueta `label.chip-opt`. |

Conclusión: **todas las funcionalidades del panel probadas se comportan como
se espera** en un navegador real, incluidos los permisos por rol en la
interfaz, la renovación/invalidación de sesión al cambiar la contraseña y el
CRUD de juegos.

---

## 5. Pruebas de carga y estrés con Locust

### 5.1 Enfoque

Se usa **[Locust](https://locust.io)**, una herramienta en Python en la que los
usuarios virtuales se describen como clases. Cada usuario espera entre 1 y 3 s
entre acciones ("tiempo de pensar"), así que el número de usuarios se parece al
de personas reales usando el panel a la vez.

El archivo [`tests/estres/locustfile.py`](./APPWEB_AUTH/tests/estres/locustfile.py)
define **tres perfiles** que reproducen las llamadas que hace el panel:

| Perfil | Peso | Qué hace |
|--------|:----:|----------|
| `Visitante` | 6 | Inicia sesión una vez y navega: listar catálogo (paginado y ordenado), buscar, filtrar por género+plataforma, abrir fichas, cargar los selects de filtros, estadísticas y `/api/salud`. Casi todo lecturas. |
| `Coleccionista` | 3 | Se **registra** con una cuenta nueva y gestiona su colección: añadir ejemplares, listar, editar estado/valoración, marcar favorito, borrar y ver el resumen. Lecturas + escrituras en SQLite. |
| `InicioSesion` | 1 | Repite **login** (bcrypt), **refresh** del token y `/api/auth/yo`. Mide el coste de la autenticación. |

Antes de empezar, un *listener* `test_start` pide el catálogo para conocer los
ids reales de los juegos. Un `409` al añadir un juego repetido se cuenta como
éxito (es una respuesta de negocio correcta, no un fallo del servidor).

### 5.2 Escenarios ejecutados

Cada escenario se lanzó contra un **servidor recién levantado** con BD
temporal (`servidor_aislado.py`), en el mismo PC que Locust:

| Escenario | Usuarios | Ritmo de entrada | Duración | Procesos Uvicorn | Objetivo |
|-----------|:-------:|:----------------:|:--------:|:----------------:|----------|
| 1. Carga normal | 20 | 5/s | 60 s | 1 | Uso típico de una clase |
| 2. Carga alta | 100 | 10/s | 90 s | 1 | Pico de uso esperado |
| 3. Estrés | 300 | 20/s | 120 s | 1 | Buscar el punto de saturación |
| 3b. Estrés intermedio | 200 | 20/s | 120 s | 1 | Acotar dónde empieza a fallar (añadido tras ver el 3) |
| 3c. Repetición del 3 | 300 | 20/s | 120 s | 1 | Confirmar que el fallo es reproducible |
| 4. Estrés escalado | 300 | 20/s | 120 s | 4 (`--workers 4`) | ¿Mejora escalando procesos? |

**Equipo de pruebas:** Windows 11, Python 3.13, Uvicorn 0.54, Locust 2.47; Locust y la API en la misma máquina (red local `127.0.0.1`).

### 5.3 Cómo ejecutarlas

1. Levantar la API aislada (en una terminal):

```powershell
cd APPWEB_AUTH
python tests/servidor_aislado.py --port 8765
```

2. Lanzar Locust (en otra terminal). **Con interfaz web** — se abre
   <http://localhost:8089>, se eligen usuarios y ritmo y se ven las gráficas en
   directo:

```powershell
locust -f tests/estres/locustfile.py --host http://127.0.0.1:8765
```

   **Sin interfaz**, guardando CSV e informe HTML (así se han hecho las del documento):

```powershell
locust -f tests/estres/locustfile.py --host http://127.0.0.1:8765 --headless -u 100 -r 10 -t 90s --csv tests/estres/resultados/2_carga_alta --html tests/estres/resultados/2_carga_alta.html
```

   Para el escenario 4, arrancar el servidor con `--workers 4`.

> ⚠️ **No lanzar el estrés contra Render** sin pensarlo: el plan Free tiene
> 0,1 CPU, se saturaría enseguida y las cuentas creadas por el perfil
> `Coleccionista` se quedarían en su base de datos. Para eso está el servidor
> aislado.

### 5.4 Resultados obtenidos

Los CSV y los informes HTML de Locust (con gráficas de usuarios, req/s y
tiempos) de cada ejecución están en
[`APPWEB_AUTH/tests/estres/resultados/`](./APPWEB_AUTH/tests/estres/resultados/)
(`<escenario>.html` se abre en el navegador).

#### Resumen por escenario (todas las peticiones agregadas)

| Escenario | Peticiones | Fallos | Mediana | p95 | p99 | Máximo | Rendimiento |
|-----------|-----------:|-------:|--------:|----:|----:|-------:|------------:|
| 1. Normal (20 u.) | 710 | **0 (0 %)** | 10 ms | 220 ms | 240 ms | 268 ms | 12,2 req/s |
| 2. Alta (100 u.) | 5 058 | **0 (0 %)** | 15 ms | 210 ms | 270 ms | 375 ms | 57,1 req/s |
| 3b. Estrés (200 u.) | 13 490 | **0 (0 %)** | 32 ms | 240 ms | 370 ms | 869 ms | 113,6 req/s |
| 3. Estrés (300 u., 1 proceso) | 890 | **115 (12,9 %)** | 220 ms | 60 000 ms | 89 000 ms | 90 617 ms | 8,8 req/s |
| 3c. Repetición (300 u., 1 proceso) | 1 274 | **114 (8,9 %)** | 240 ms | 60 000 ms | 90 000 ms | ≈ 90 000 ms | 12,4 req/s |
| 4. Estrés (300 u., 4 procesos) | 19 482 | **1 (0,005 %)** | 20 ms | 260 ms | 1 300 ms | 3 733 ms | 164,1 req/s |

> El p95 de los escenarios 1–3b ronda los 220–240 ms solo por el **login y el
> registro** (bcrypt, ver abajo); quitándolos, las lecturas del catálogo
> tienen p95 de 14–75 ms con 100 usuarios.

#### Tiempos por tipo de petición (escenario 2, 100 usuarios)

| Petición | Nº | Mediana | p95 | Máx |
|----------|---:|--------:|----:|----:|
| `POST /api/auth/login` | 295 | 220 ms | 280 ms | 314 ms |
| `POST /api/auth/registro` | 30 | 290 ms | 360 ms | 375 ms |
| `POST /api/auth/refresh` | 69 | 8 ms | 38 ms | 70 ms |
| `GET /api/videojuegos` (listado) | 767 | 15 ms | 75 ms | 272 ms |
| `GET /api/videojuegos?q=` (búsqueda) | 439 | 15 ms | 77 ms | 197 ms |
| `GET /api/videojuegos/{id}` (ficha) | 604 | 13 ms | 75 ms | 238 ms |
| `GET /api/estadisticas/*` | 849 | 10 ms | 54 ms | 309 ms |
| `GET /api/colecciones` | 422 | 17 ms | 83 ms | 259 ms |
| `POST /api/colecciones` | 354 | 20 ms | 100 ms | 253 ms |
| `PUT /api/colecciones/{id}` | 182 | 32 ms | 98 ms | 208 ms |
| `GET /api/salud` | 138 | 3 ms | 9 ms | 13 ms |

#### Análisis

**1. Hasta 200 usuarios simultáneos la API va sobrada.** Cero errores y el
rendimiento crece casi lineal con los usuarios (12 → 57 → 114 req/s). Las
lecturas responden en decenas de milisegundos.

**2. El login es la operación más cara, y es a propósito.** `login` y
`registro` tardan ~220–300 ms incluso sin carga porque **bcrypt** (12 rondas)
está diseñado para ser lento y frenar ataques de fuerza bruta. `refresh` no
usa bcrypt y tarda ~8 ms: por eso el panel renueva la sesión con el *refresh
token* en vez de volver a pedir la contraseña. Con mucha carga el login es lo
primero que se nota (p99 de 580 ms con 200 usuarios).

**3. Con 300 usuarios y un solo proceso, la API se bloquea (fallo encontrado).**
Pasó en las dos ejecuciones (3 y 3c). El historial de Locust muestra el
patrón:

| Segundo | Usuarios | req/s | p95 |
|--------:|---------:|------:|----:|
| 16 | 300 | 64–75 | ~500 ms |
| ~40–48 | 300 | **0** | se dispara |
| 72+ | 300 | 0 | 30 000 ms |
| 105+ | 300 | 0 | 60 000 ms |

El servidor deja de responder **del todo** (incluso `GET /api/salud`, que no
toca la BD, tardó 29 s) y en su log aparece 106 veces:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached,
connection timed out, timeout 30.00
```

Que los tiempos se queden en 30 s, 60 s y 90 s exactos (múltiplos del
`timeout` de 30 s del pool) confirma la causa:

- Todos los endpoints son funciones `def` síncronas, así que FastAPI los
  ejecuta en un ***threadpool* de 40 hilos**.
- Cada petición pide una sesión con `get_db()`, pero el *pool* de conexiones de
  SQLAlchemy por defecto solo tiene **15** (5 + 10 de desbordamiento).
- Con más de ~40 peticiones a la vez, los 40 hilos se quedan esperando una
  conexión, y las conexiones ocupadas no se devuelven porque el cierre de la
  sesión (`db.close()` tras el `yield` de `get_db`) **también necesita un hilo
  libre** del mismo *threadpool*. Es un bloqueo mutuo que solo se rompe cuando
  salta el timeout de 30 s y la petición devuelve `500`. (Es un problema
  conocido de FastAPI con dependencias síncronas con `yield` + SQLAlchemy; el
  mecanismo exacto no se ha depurado paso a paso, pero los síntomas —0 req/s,
  esperas de 30 s exactos y el error del pool— encajan con él.)
- Con 200 usuarios no llega a pasar porque casi nunca hay más de 40 peticiones
  en vuelo; con 300 se cruza ese umbral y el sistema cae de golpe (no se
  degrada poco a poco).

**4. Escalar a 4 procesos lo resuelve para esta carga.** Con
`--workers 4` cada proceso tiene su propio *threadpool* y su propio pool de
conexiones: 300 usuarios dan **164 req/s con un único fallo** (una conexión
cortada en 19 482 peticiones). El p99 sube a ~1,3 s porque los 4 procesos
compiten por escribir en el **mismo archivo SQLite**, que solo admite un
escritor a la vez.

**5. Segundo fallo encontrado: arranque con varios procesos y BD vacía.** Al
lanzar `uvicorn --workers 4` sobre una base de datos que no existe, los cuatro
procesos ejecutan el *seed* a la vez y tres revientan con
`UNIQUE constraint failed: usuarios.email` (todos intentan crear
`admin@ludoteca.local`), con lo que Uvicorn aborta el arranque. En las pruebas
se ha sorteado creando antes la BD con un solo proceso
(`servidor_aislado.py --workers N` lo hace solo); en la app real habría que
hacer el *seed* tolerante a esa carrera o ejecutarlo como paso previo al
arranque.

**6. Qué significa para el despliegue en Render.** Las pruebas se hicieron en
un PC con varios núcleos. El plan Free de Render tiene **0,1 CPU**, así que los
límites reales allí serán bastante más bajos (sobre todo en login, que es
CPU pura). Para una clase o una demo (decenas de usuarios) va bien; para
cientos de usuarios simultáneos habría que aplicar las mejoras de §9.

---

## 8. Integración continua (GitHub Actions)

El archivo [`.github/workflows/pruebas-appweb.yml`](./.github/workflows/pruebas-appweb.yml)
automatiza las pruebas en cada `push` a `main` o *pull request* que toque
`APPWEB_AUTH/` (y a mano con **Run workflow**):

```
 push / PR ─► Job 1: api-y-funcionales ───────────────► Job 2: carga-humo
              ├ checkout + Python 3.12 + caché pip       ├ servidor aislado :8765
              ├ pip install -r requirements-test.txt     ├ Locust 20 usuarios, 45 s
              ├ servidor aislado :8000 + probar_api.py   ├ --exit-code-on-error 1
              ├ pytest (Selenium, Chrome headless)       └ artefacto: informe HTML + CSV
              └ artefacto: JUnit XML + capturas de fallos
```

- Los *runners* `ubuntu-latest` ya traen Google Chrome; Selenium Manager baja
  el chromedriver que corresponda, así que no hay que instalar nada más.
- Si una prueba Selenium falla, `conftest.py` guarda una **captura de pantalla**
  en `tests/funcionales/capturas/`, que el job publica como artefacto.
- El job de carga solo corre si los funcionales pasan, y **falla si alguna
  petición falla** (`--exit-code-on-error 1`): es una prueba de humo de
  rendimiento, no un estrés completo (eso se hace a mano, §5, porque tarda y
  depende de la máquina).
- Relación con el despliegue: Render despliega desde el repositorio `PERSONAL`
  por su cuenta; el workflow actúa como **puerta de calidad** para saber si lo
  que hay en `main` está sano. Para que el despliegue esperara a las pruebas,
  se desactivaría el *auto-deploy* y se lanzaría el *Deploy Hook* de Render como
  último paso del workflow.

> ⚠️ El workflow se ha escrito y sus pasos se han ejecutado en local (mismos
> comandos), pero **no se ha visto todavía correr en GitHub**: depende de que
> GitHub Actions esté habilitado en el repositorio de la organización. Tras el
> primer push, revisar la pestaña **Actions**.

---

## 9. Conclusiones y mejoras propuestas

### 9.1 Conclusiones

- El soporte DevOps tiene ya los tres niveles de prueba automática:
  **API** (110 comprobaciones), **funcional E2E** (18 casos Selenium) y
  **rendimiento** (Locust, 3 perfiles), todos reproducibles gracias al
  **servidor aislado** con BD temporal, y enganchados a un pipeline de
  **GitHub Actions**.
- **Funcionalmente** la aplicación pasa todas las pruebas.
- **En rendimiento** aguanta sin errores hasta **200 usuarios simultáneos**
  (≈ 114 req/s) con un proceso, pero **con 300 se bloquea** por el
  agotamiento del pool de conexiones de SQLAlchemy frente al *threadpool* de
  FastAPI. Con 4 procesos aguanta 300 usuarios (164 req/s).
- Las pruebas de estrés han servido para lo que son: **encontrar dos fallos
  que las pruebas funcionales no podían ver** (el bloqueo del pool y la
  carrera del *seed* con varios procesos).

### 9.2 Mejoras propuestas

| Prioridad | Mejora | Por qué |
|:---------:|--------|---------|
| Alta | Ajustar el pool en `database.py` (p. ej. `pool_size=20, max_overflow=30, pool_timeout=10`) o, al ser SQLite, usar `NullPool` | Que haya al menos tantas conexiones como hilos (40) y desaparezca el bloqueo; un timeout más corto hace que, si satura, falle rápido en vez de colgarse 30 s. |
| Alta | Hacer el *seed* seguro con varios procesos (capturar `IntegrityError` en `asegurar_admin`, o ejecutarlo antes de arrancar Uvicorn) | Permite usar `--workers N` sin preparar la BD a mano. |
| Media | Activar `PRAGMA journal_mode=WAL` en SQLite | Lecturas y una escritura a la vez; baja el p99 con varios procesos. |
| Media | Limitar intentos de login por IP (*rate limiting*) | El login con bcrypt es el endpoint más caro: además de seguridad, protege la CPU. |
| Media | Desplegar con `--workers` acorde a la CPU y disco persistente / PostgreSQL | Lo que se ve en el escenario 4 y en la [comparativa](./COMPARATIVA_PRESUPUESTOS_APLICACION_WEB_DESPLEGADA.md). |
| Baja | `render.yaml` en el repo y *Deploy Hook* al final del workflow | Infraestructura como código y despliegue solo si pasan las pruebas. |
| Baja | Dejar de versionar `__pycache__/` (ya se ignora en `APPWEB_AUTH/.gitignore`, pero hay `.pyc` subidos de antes) | Limpieza del repositorio. |

Tras aplicar las mejoras de prioridad alta habría que **repetir el escenario 3**
(300 usuarios, 1 proceso) con el mismo comando para comprobar que el bloqueo
desaparece.
