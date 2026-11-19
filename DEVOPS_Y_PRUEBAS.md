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
| Variables de entorno | Ver la tabla siguiente |
| Auto-deploy | Activado sobre `main` |

Variables de entorno (*Environment*) para la versión actual:

| Variable | Valor | Obligatoria |
|----------|-------|:-----------:|
| `LUDOTECA_SECRET_KEY` | Clave larga y aleatoria propia (**no** la de desarrollo) | Sí |
| `LUDOTECA_PROXIES_CONFIABLES` | `1` (Render pone un proxy delante: sin esto la protección anti-DDoS vería a todos los visitantes como una sola IP; §7.2) | **Sí** |
| `LUDOTECA_PUBLIC_URL` | `https://pps-appweb-26-27-sju7.onrender.com` (URL de vuelta del login social y cookie `Secure`) | Con login social |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Los que da Google Cloud Console al crear el ID de cliente OAuth | Para el botón de Google |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | Los que da GitHub al crear la OAuth App | Para el botón de GitHub |

Las URL de vuelta que hay que registrar en Google y GitHub, y cómo conseguir
los ID y secretos, están en el [README de la app](./APPWEB_AUTH/README.md#login-y-registro-con-google-o-github).
Los secretos solo van en Render, nunca en el repositorio.

> ⚠️ Render despliega desde el repositorio `PERSONAL`. Subir a `origin` (el del
> IES) lanza el CI pero **no** actualiza la web publicada: hay que hacer también
> `git push PERSONAL main` (§3.1).

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

- [`tests/oauth/test_oauth.py`](./APPWEB_AUTH/tests/oauth/test_oauth.py) (18 pruebas, ~7 s): la app real con
  `TestClient` y BD temporal, **simulando** Google y GitHub (se sustituye la
  función que les hace las peticiones). Cubre la redirección al proveedor,
  alta de usuario nuevo, reutilización y vinculación por email, que los JWT
  emitidos funcionan en `/api/auth/yo`, colecciones y refresh, email sin
  verificar, `state` manipulado / de otro proveedor / sin cookie (CSRF),
  cancelación, cookie `Secure` en https, proveedor desconocido o sin configurar y borrado en cascada.
- [`tests/funcionales/test_oauth_navegador.py`](./APPWEB_AUTH/tests/funcionales/test_oauth_navegador.py) (5 pruebas Selenium): botones
  ocultos sin configuración y visibles (con su enlace) con ella, que el botón
  lleva a `github.com/login/oauth/authorize`, y que la vuelta
  `#oauth=<tokens>` entra al panel (y limpia la URL) y `#oauth_error=` muestra
  el aviso.

Resultado: **41 de 41 pruebas pasan** (18 OAuth + 23 Selenium) y
`probar_api.py` sigue pasando entero, también arrancando sobre una copia de la
BD real del repositorio (la tabla `cuentas_oauth` se crea sola y no se pierde
ningún usuario). El viaje real a Google/GitHub no se automatiza porque exige
cuentas y credenciales reales: se prueba a mano una vez configuradas.

#### Total de la suite automática

Con las 12 pruebas anti-DDoS de la §7, `python -m pytest` ejecuta **53
pruebas** (12 anti-DDoS + 18 OAuth + 23 Selenium), además de las 110
comprobaciones de `probar_api.py`. Todas pasan en local y en GitHub Actions
(§8).

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
| 7. Estrés con `--limit-concurrency 30` | 300 | 20/s | 120 s | 1 | ¿Evita el bloqueo limitar las conexiones en Uvicorn? |

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
| [1. Normal (20 u.)](./APPWEB_AUTH/tests/estres/resultados/1_carga_normal.html) | 710 | **0 (0 %)** | 10 ms | 220 ms | 240 ms | 268 ms | 12,2 req/s |
| [2. Alta (100 u.)](./APPWEB_AUTH/tests/estres/resultados/2_carga_alta.html) | 5 058 | **0 (0 %)** | 15 ms | 210 ms | 270 ms | 375 ms | 57,1 req/s |
| [3b. Estrés (200 u.)](./APPWEB_AUTH/tests/estres/resultados/3b_estres_200.html) | 13 490 | **0 (0 %)** | 32 ms | 240 ms | 370 ms | 869 ms | 113,6 req/s |
| [3. Estrés (300 u., 1 proceso)](./APPWEB_AUTH/tests/estres/resultados/3_estres.html) | 890 | **115 (12,9 %)** | 220 ms | 60 000 ms | 89 000 ms | 90 617 ms | 8,8 req/s |
| [3c. Repetición (300 u., 1 proceso)](./APPWEB_AUTH/tests/estres/resultados/3c_estres_300_repeticion.html) | 1 274 | **114 (8,9 %)** | 240 ms | 60 000 ms | 90 000 ms | ≈ 90 000 ms | 12,4 req/s |
| [4. Estrés (300 u., 4 procesos)](./APPWEB_AUTH/tests/estres/resultados/4_estres_4workers.html) | 19 482 | **1 (0,005 %)** | 20 ms | 260 ms | 1 300 ms | 3 733 ms | 164,1 req/s |
| [7. Estrés (300 u., `--limit-concurrency 30`)](./APPWEB_AUTH/tests/estres/resultados/7_estres_300_limit_concurrency.html) | 18 325 | **17 720 (96,7 %)** | 10 ms | 39 ms | 90 ms | 1 281 ms | 154,2 req/s |

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

**6. Limitar conexiones en Uvicorn no es la solución (escenario 7).** Se
probó a arrancar con `--limit-concurrency 30`, para que nunca hubiera más
trabajo a la vez del que caben hilos y conexiones. El servidor **ya no se
bloquea**: ningún `QueuePool` en el log y respuestas en milisegundos. Pero
**rechaza el 96,7 % de las peticiones con 503**, y de rebote muchas con 401,
porque los logins rechazados dejan a los usuarios sin token. El motivo es
que Uvicorn cuenta las **conexiones abiertas**, no las peticiones en curso, y
cada usuario de Locust (como un navegador) mantiene su conexión abierta
(*keep-alive*): con 300 usuarios conectados casi todos quedan por encima del
límite. Conclusión: evita la caída, pero a costa de dejar fuera a casi todos.
El arreglo de verdad es el del pool de conexiones (§9.2) o escalar procesos
(escenario 4).

**7. Qué significa para el despliegue en Render.** Las pruebas se hicieron en
un PC con varios núcleos. El plan Free de Render tiene **0,1 CPU**, así que los
límites reales allí serán bastante más bajos (sobre todo en login, que es
CPU pura). Para una clase o una demo (decenas de usuarios) va bien; para
cientos de usuarios simultáneos habría que aplicar las mejoras de §9.

---

## 6. Pruebas de carga en producción (Render)

### 6.1 Enfoque y precauciones

El enunciado pide repartir el estrés entre **local** (§5) y **producción**.
Contra producción no se puede lanzar lo mismo que en local: es el servicio
público, en el plan Free (0,1 CPU, se duerme a los 15 minutos), con la base de
datos de demostración. Por eso el perfil de producción,
[`tests/estres/locustfile_produccion.py`](./APPWEB_AUTH/tests/estres/locustfile_produccion.py),
está hecho para **no hacer daño ni ensuciar datos**:

- **No inicia sesión ni escribe nada**: hace lo que un visitante anónimo
  (pantalla de login con su CSS y JS, panel, portada de la API,
  `/openapi.json`, `/api/salud`).
- Pide el catálogo **sin token** y espera un **401**, que se cuenta como
  correcto: es la respuesta esperada y ejercita la capa de autenticación.
- Pausas de 2–5 s entre acciones (visitantes realistas, no una inundación).
- Si se definen `LUDOTECA_PROD_EMAIL` y `LUDOTECA_PROD_PASSWORD`, cada usuario
  entra con esa cuenta y navega por el catálogo (solo lecturas). Está pensado
  para lanzarlo con una cuenta de pruebas propia; **no se ha usado** para
  este documento, para no meter credenciales en el despliegue real.

Además, [`tests/ddos/rafaga.py`](./APPWEB_AUTH/tests/ddos/rafaga.py) lanza una
ráfaga corta desde una sola máquina para ver **si el hosting frena** un pico de
peticiones (ver también §7).

### 6.2 Cómo ejecutarlas

Primero hay que **despertar** el servicio (la primera petición tras dormir
tarda ~30–60 s):

```powershell
curl.exe https://pps-appweb-26-27-sju7.onrender.com/api/salud
```

Carga con 10 y 30 visitantes (desde la carpeta `APPWEB_AUTH`):

```powershell
locust -f tests/estres/locustfile_produccion.py --host https://pps-appweb-26-27-sju7.onrender.com --headless -u 10 -r 1 -t 60s --csv tests/estres/resultados/8_produccion_10_usuarios --html tests/estres/resultados/8_produccion_10_usuarios.html
```

```powershell
locust -f tests/estres/locustfile_produccion.py --host https://pps-appweb-26-27-sju7.onrender.com --headless -u 30 -r 2 -t 120s --csv tests/estres/resultados/9_produccion_30_usuarios --html tests/estres/resultados/9_produccion_30_usuarios.html
```

Ráfaga de 300 peticiones, 20 a la vez:

```powershell
python tests/ddos/rafaga.py https://pps-appweb-26-27-sju7.onrender.com/api/salud -n 300 -c 20
```

### 6.3 Resultados obtenidos

Ejecutadas el 19/11/2026 desde un PC doméstico en España contra la versión
desplegada en ese momento: la de octubre, **sin** el login social ni la
protección anti-DDoS, porque el repositorio `PERSONAL` aún no se había
actualizado (ver §3.1).

| Escenario | Usuarios | Duración | Peticiones | Fallos | Mediana | p95 | p99 | Máx | Rendimiento |
|-----------|:-------:|:--------:|-----------:|-------:|--------:|----:|----:|----:|------------:|
| [8. Producción ligera](./APPWEB_AUTH/tests/estres/resultados/8_produccion_10_usuarios.html) | 10 | 60 s | 231 | **0** | 200 ms | 350 ms | 610 ms | 769 ms | 4,0 req/s |
| [9. Producción media](./APPWEB_AUTH/tests/estres/resultados/9_produccion_30_usuarios.html) | 30 | 120 s | 1 488 | **0** | 200 ms | 280 ms | 460 ms | 967 ms | 12,5 req/s |

Por petición (escenario 9):

| Petición | Nº | Mediana | p95 |
|----------|---:|--------:|----:|
| `GET /panel/login.html` | 248 | 200 ms | 280 ms |
| `GET /panel/styles.css` | 246 | 200 ms | 290 ms |
| `GET /panel/auth.js` | 246 | 200 ms | 250 ms |
| `GET /panel/` y `app.js` | 238 | 200 ms | 270–380 ms |
| `GET /api/salud` | 182 | 190 ms | 240 ms |
| `GET /api/videojuegos` sin token → 401 | 189 | 200 ms | 280 ms |
| `GET /` | 73 | 200 ms | 280 ms |
| `GET /openapi.json` | 66 | 200 ms | 270 ms |

**Ráfaga de 300 peticiones a `/api/salud` (20 a la vez):**

```
300 peticiones, 20 a la vez -> https://pps-appweb-26-27-sju7.onrender.com/api/salud
  duración 5.0 s · 60.6 req/s · mediana 282 ms · p95 431 ms · máx 781 ms
  200: 300
```

**Análisis:**

1. **Producción aguanta sin errores** con 10 y 30 visitantes simultáneos.
2. Los **~200 ms de mediana son casi todo red** (ida y vuelta España ↔
   servidores de Render, más TLS): en local las mismas rutas tardan 3–10 ms.
   Al pasar de 10 a 30 usuarios la mediana no sube, así que el servidor no
   está cerca de su límite con este tráfico.
3. Las peticiones de la prueba son ligeras (estáticos, salud, 401). Lo que
   saturaría antes los 0,1 CPU del plan Free es el **login** (bcrypt, ~0,25 s
   de CPU en un PC y bastante más con 0,1 CPU). No se ha forzado en
   producción a propósito.
4. La **ráfaga** de 300 peticiones en 5 s desde una sola IP pasó entera (300 ×
   200, ningún 429): **ni la app desplegada ni Render limitaron** ese pico.
   Render tiene protección de red frente a ataques volumétricos, pero no
   limita el ritmo de un cliente a este nivel. Es justo lo que cubre la
   protección de la §7 una vez desplegada.

> 🔁 **Para repetir tras desplegar la versión nueva:** con la protección
> activa y `LUDOTECA_PROXIES_CONFIABLES=1`, la misma ráfaga de 300 debería dar
> **300 × 200** (el límite es 300 por minuto e IP), y una de **400** debería
> devolver **429** en las últimas ~100.

---

## 7. Protección y pruebas anti-DDoS

### 7.1 El problema

Las pruebas anteriores dejaron claro que, **tal como estaba**, la aplicación
era fácil de tumbar o de atacar:

- Nada limitaba cuántas peticiones podía hacer un mismo cliente: con 300
  usuarios la API se bloqueaba (§5.4) y la ráfaga de producción pasó entera
  (§6.3).
- El **login** no tenía límite de intentos: se podían probar contraseñas sin
  freno (**fuerza bruta**). Además, cada intento cuesta un bcrypt (~0,25–0,5 s
  de CPU), así que unos pocos atacantes bastan para acaparar la CPU (**DoS de
  capa de aplicación**).
- No había límite de tamaño de las peticiones.

### 7.2 La protección añadida

[`app/anti_ddos.py`](./APPWEB_AUTH/app/anti_ddos.py) es un *middleware* ASGI
que se ejecuta **antes** que cualquier endpoint. Se registra en `main.py` justo
antes de CORS. Rechazar una petición le cuesta ~7 ms, sin tocar la base de
datos ni el *threadpool*.

| Defensa | Límite por defecto | Respuesta | Contra qué |
|---------|-------------------|-----------|------------|
| Peticiones por IP | 300 por minuto | **429** + `Retry-After` | Inundación desde un mismo origen |
| Intentos de login, registro y OAuth por IP | 20 por minuto | **429** + `Retry-After` | Fuerza bruta y abuso del bcrypt |
| Tamaño del cuerpo | 1 MB | **413** | Peticiones enormes que consumen memoria |

- Es una **ventana deslizante** de 60 s por IP, en memoria del proceso.
- `refresh` y la lista de proveedores **no** cuentan como intento de login:
  el panel renueva la sesión sin ser castigado.
- **IP real detrás de un proxy:** con `LUDOTECA_PROXIES_CONFIABLES=0` (por
  defecto) se usa la IP de la conexión y **se ignora `X-Forwarded-For`**, que
  cualquiera puede inventarse. Detrás de Render hay que poner `1`: entonces se
  toma la IP que **añade el propio proxy** (la última de la cabecera), no la
  que pueda poner el atacante delante.
- Todo es configurable por variables de entorno (§2.4), y
  `LUDOTECA_ANTI_DDOS=0` lo desactiva.
- **Límites conocidos:** los contadores son de cada proceso (con
  `--workers 4` el límite efectivo es ×4), y esto no para un **DDoS
  volumétrico** de miles de IPs: eso corresponde a la red del hosting
  (Render/Cloudflare) o a un WAF. Esta capa protege la aplicación del abuso
  desde pocos orígenes, que es lo que se puede probar y controlar desde el
  código.

> ⚠️ **En Render es obligatorio** definir `LUDOTECA_PROXIES_CONFIABLES=1` antes
> de desplegar esta versión. Si no, la app ve a **todos** los visitantes con la
> IP del proxy y aplica los límites a todo el mundo junto (20 logins por
> minuto en total).

### 7.3 Pruebas

Hay tres tipos de prueba, de la más rápida a la más realista.

**a) Pruebas automáticas**, en [`tests/ddos/test_anti_ddos.py`](./APPWEB_AUTH/tests/ddos/test_anti_ddos.py)
(12 pruebas, ~10 s). Se ejecutan con `python -m pytest` y en el CI. Montan el
*middleware* real sobre una mini-app para poder lanzar cientos de peticiones
en milisegundos:

| Prueba | Comprueba |
|--------|-----------|
| `test_inundacion_desde_una_ip_recibe_429` | Pasan 300 peticiones y de la 301 en adelante, 429 |
| `test_el_429_lleva_retry_after_y_mensaje` | El 429 dice cuánto esperar y por qué |
| `test_limite_configurable` | `LUDOTECA_LIMITE_GENERAL` cambia el límite |
| `test_se_recupera_al_pasar_la_ventana` | Pasado un minuto se vuelve a atender (reloj simulado) |
| `test_fuerza_bruta_de_login_se_corta_a_los_20_intentos` | 20 intentos de login y luego 429 |
| `test_bloqueo_de_login_no_afecta_al_resto_de_la_api` | Con el login bloqueado, el resto de la API y el refresh siguen |
| `test_sin_proxy_no_se_puede_falsear_la_ip` | Cambiar `X-Forwarded-For` no salta el límite |
| `test_detras_de_proxy_cada_cliente_tiene_su_limite` | Un atacante bloqueado no afecta a otro cliente |
| `test_detras_de_proxy_se_usa_la_ip_que_anade_el_proxy` | Una IP inventada al principio de la cabecera no sirve |
| `test_cuerpo_demasiado_grande_413` y `test_cuerpo_normal_pasa` | Límite de 1 MB |
| `test_se_puede_desactivar` | `LUDOTECA_ANTI_DDOS=0` |

**b) Ataque simulado con Locust**, en [`tests/estres/locustfile_ddos.py`](./APPWEB_AUTH/tests/estres/locustfile_ddos.py)
(solo en local). Mezcla **50 usuarios legítimos**, cada uno con su IP (simulada
con `X-Forwarded-For`) y navegando con pausas, y **5 atacantes** desde una
misma IP (`203.0.113.66`) que, sin pausas, prueban contraseñas en el login e
inundan el catálogo. Sus peticiones salen como `[ATAQUE]` en las
estadísticas. Se ejecuta dos veces, con y sin protección:

```powershell
python tests/servidor_aislado.py --port 8765 --proxies 1 --anti-ddos
```

```powershell
locust -f tests/estres/locustfile_ddos.py --host http://127.0.0.1:8765 --headless -u 55 -r 10 -t 60s --csv tests/estres/resultados/6_ddos_con_proteccion --html tests/estres/resultados/6_ddos_con_proteccion.html
```

Para el caso sin protección, el servidor se arranca sin `--anti-ddos`.

**c) Ráfagas** con [`tests/ddos/rafaga.py`](./APPWEB_AUTH/tests/ddos/rafaga.py)
contra el servidor local protegido (y contra producción, §6.3):

```powershell
python tests/ddos/rafaga.py http://127.0.0.1:8765/api/salud -n 400 -c 20
```

```powershell
python tests/ddos/rafaga.py http://127.0.0.1:8765/api/auth/login -n 40 -c 5 --post-json '{\"email\":\"admin@ludoteca.local\",\"password\":\"mal\"}'
```

### 7.4 Resultados obtenidos

**a) Pruebas automáticas:** 12 de 12 pasan, en local y en GitHub Actions.

**b) Ataque simulado** (60 s, 50 legítimos + 5 atacantes):

| | [5. Sin protección](./APPWEB_AUTH/tests/estres/resultados/5_ddos_sin_proteccion.html) | [6. Con protección](./APPWEB_AUTH/tests/estres/resultados/6_ddos_con_proteccion.html) |
|---|---:|---:|
| Intentos de contraseña del atacante | 556 | 22 919 |
| …que **llegaron a comprobarse** (bcrypt) | **556** (todos) | **20** |
| …cortados con 429 | 0 | **22 899** (~7 ms cada uno) |
| Tiempo de cada intento del atacante | ~510 ms | ~7 ms |
| Inundación del catálogo `[ATAQUE] GET` | 193 (401) | 7 500 (7 220 con 429) |
| **Errores de los usuarios legítimos** | **0** | **0** |
| Catálogo legítimo (mediana / p95) | 21 / 83 ms | 40 / 100 ms |
| Login legítimo (mediana) | 590 ms | 650 ms |

**c) Ráfagas en local con la protección activa:**

```
400 peticiones, 20 a la vez -> /api/salud      ->  200: 298 · 429: 102
40 peticiones, 5 a la vez   -> /api/auth/login ->  401: 20  · 429: 20
```

Los 20 primeros intentos llegan al login y dan 401 por contraseña errónea; a
partir del 21, 429 sin llegar a comprobar la contraseña.

**Comprobación de no regresión:** `probar_api.py` (114 peticiones, 15 de ellas
de login o registro) pasa entero con la protección **activada**, en 12 s y
**sin ningún 429**. El uso normal no se ve afectado.

**Análisis:**

1. **La fuerza bruta queda neutralizada:** sin protección el atacante probó
   556 contraseñas en un minuto (≈ 33 000 por hora); con protección, **20 por
   minuto**. Además, cada intento rechazado ya no cuesta un bcrypt.
2. **Los usuarios legítimos no notan el bloqueo**, porque los límites son por
   IP: 0 errores en los dos casos.
3. Con la protección, el atacante recibe la respuesta tan rápido (7 ms) que
   **reintenta mucho más** (22 919 frente a 556 intentos). Esas respuestas son
   baratas, pero no gratis: la mediana del catálogo legítimo sube de 21 a
   40 ms. Por eso esta capa es la **última línea**. En un despliegue serio el
   bloqueo debería hacerse antes, en el proxy, CDN o WAF, y la aplicación
   quedarse como red de seguridad.
4. Las ráfagas muestran el límite exacto: ~300 por minuto e IP aceptadas y el
   resto con 429 + `Retry-After`.

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
              ├ pytest: anti-DDoS + OAuth + Selenium     └ artefacto: informe HTML + CSV
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

- En el servidor aislado del CI la protección anti-DDoS va **desactivada**,
  porque Locust lanza a todos sus usuarios desde la misma IP. La protección se
  prueba aparte con sus 12 pruebas, que sí corren en el CI.

#### Resultado en GitHub

Tras el commit `5ed3194` ("Hecho ejercicio 3") subido a `origin`, el workflow
corrió en GitHub **en verde**:

| Job | Duración | Resultado |
|-----|---------:|-----------|
| `api-y-funcionales` | 1 min 42 s | ✅ `probar_api.py` + suite pytest completa |
| `carga-humo` | 1 min 13 s | ✅ Locust sin errores; artefacto `informe-carga` (310 KB) |

Dejó **2 avisos** (no son fallos): *"Node.js 20 is deprecated"* en
`actions/checkout@v4`, `actions/setup-python@v5` y `actions/upload-artifact@v4`.
GitHub está retirando Node 20 y de momento las ejecuta con Node 24. Se quitan
subiendo esas acciones a sus versiones nuevas (§9.2).

**Cómo verlo:** pestaña **Actions** del repositorio (no *Settings → Secrets and
variables*, que es para guardar secretos, y este workflow no necesita
ninguno) → ejecución "Pruebas APPWEB_AUTH" → cada job muestra la salida de
cada paso, y abajo están los **Artifacts** descargables. Para relanzarlo a
mano: **Actions** → "Pruebas APPWEB_AUTH" → **Run workflow**.

---

## 9. Conclusiones y mejoras propuestas

### 9.1 Conclusiones

- El soporte DevOps cubre todo lo que pide el enunciado:
  **funcionales** (23 casos Selenium + 110 comprobaciones de API + 18 de
  OAuth), **estrés en local** (Locust, 3 perfiles y 7 escenarios), **estrés en
  producción** (Render, 2 escenarios y una ráfaga) y **anti-DDoS**
  (protección + 12 pruebas + ataque simulado). Todo es reproducible gracias al
  **servidor aislado** con BD temporal y corre en **GitHub Actions**, que ya ha
  pasado en verde.
- **Funcionalmente** la aplicación pasa todas las pruebas.
- **En rendimiento** aguanta sin errores hasta **200 usuarios simultáneos**
  (≈ 114 req/s) con un proceso, pero **con 300 se bloquea** por el
  agotamiento del pool de conexiones de SQLAlchemy frente al *threadpool* de
  FastAPI. Con 4 procesos aguanta 300 usuarios (164 req/s).
- Las pruebas de estrés han servido para lo que son: **encontrar dos fallos
  que las pruebas funcionales no podían ver** (el bloqueo del pool y la
  carrera del *seed* con varios procesos). Limitar conexiones en Uvicorn
  (`--limit-concurrency`) evita el bloqueo, pero rechaza el 97 % del tráfico,
  así que no es el arreglo.
- **En producción** (Render Free) la app atiende 30 visitantes simultáneos
  sin errores; los ~200 ms de respuesta son casi todo red. La versión
  desplegada no limitaba nada: una ráfaga de 300 peticiones pasó entera.
- **Frente a DDoS** la nueva protección corta la fuerza bruta del login de
  556 a **20 intentos por minuto** y responde 429 en ~7 ms, sin errores para
  los usuarios legítimos y sin afectar al uso normal (`probar_api.py` pasa
  sin ningún 429). No sustituye a la protección de red del hosting frente a
  ataques volumétricos desde miles de IPs.

### 9.2 Mejoras propuestas

| Prioridad | Mejora | Por qué |
|:---------:|--------|---------|
| Alta | Ajustar el pool en `database.py` (p. ej. `pool_size=20, max_overflow=30, pool_timeout=10`) o, al ser SQLite, usar `NullPool` | Que haya al menos tantas conexiones como hilos (40) y desaparezca el bloqueo; un timeout más corto hace que, si satura, falle rápido en vez de colgarse 30 s. |
| Alta | Hacer el *seed* seguro con varios procesos (capturar `IntegrityError` en `asegurar_admin`, o ejecutarlo antes de arrancar Uvicorn) | Permite usar `--workers N` sin preparar la BD a mano. |
| Media | Activar `PRAGMA journal_mode=WAL` en SQLite | Lecturas y una escritura a la vez; baja el p99 con varios procesos. |
| ✅ Hecha | Limitar intentos de login y peticiones por IP (*rate limiting*) | Aplicada en `app/anti_ddos.py` (§7). |
| Alta | Desplegar la versión nueva en Render con `LUDOTECA_PROXIES_CONFIABLES=1` y repetir la ráfaga de la §6 | Comprobar en producción que la protección responde 429 y que no bloquea a usuarios distintos. |
| Media | Guardar los contadores anti-DDoS en Redis (o similar) en vez de en memoria | Que el límite sea común a todos los procesos (`--workers N`) y sobreviva a reinicios. |
| Baja | Subir las acciones del workflow (`checkout`, `setup-python`, `upload-artifact`) a sus versiones para Node 24 | Quitar los avisos de Node 20 del CI. |
| Media | Desplegar con `--workers` acorde a la CPU y disco persistente / PostgreSQL | Lo que se ve en el escenario 4 y en la [comparativa](./COMPARATIVA_PRESUPUESTOS_APLICACION_WEB_DESPLEGADA.md). |
| Baja | `render.yaml` en el repo y *Deploy Hook* al final del workflow | Infraestructura como código y despliegue solo si pasan las pruebas. |
| Baja | Dejar de versionar `__pycache__/` (ya se ignora en `APPWEB_AUTH/.gitignore`, pero hay `.pyc` subidos de antes) | Limpieza del repositorio. |

Tras aplicar las mejoras de prioridad alta habría que **repetir el escenario 3**
(300 usuarios, 1 proceso) con el mismo comando para comprobar que el bloqueo
desaparece.
