# Comparativa de presupuestos – Aplicación web desplegada

**Autor:** Luis Miguel Gomila Domínguez
**Aplicación:** API Colección de Videojuegos / Panel web "Ludoteca" ([`APPWEB_AUTH`](./APPWEB_AUTH))
**Fecha de la consulta de precios:** noviembre de 2026

---

## 1. Enlace al despliegue

La aplicación está desplegada en **Render**:

🔗 **<https://pps-appweb-26-27-sju7.onrender.com>**

| Ruta | Qué hay |
|------|---------|
| [`/`](https://pps-appweb-26-27-sju7.onrender.com/) | Índice de la API (JSON con las rutas disponibles) |
| [`/panel`](https://pps-appweb-26-27-sju7.onrender.com/panel) | **Frontend** (panel web "Ludoteca") |
| [`/panel/login.html`](https://pps-appweb-26-27-sju7.onrender.com/panel/login.html) | Pantalla de inicio de sesión y registro |
| [`/docs`](https://pps-appweb-26-27-sju7.onrender.com/docs) | Documentación interactiva Swagger |
| [`/redoc`](https://pps-appweb-26-27-sju7.onrender.com/redoc) | Documentación ReDoc |
| [`/api/salud`](https://pps-appweb-26-27-sju7.onrender.com/api/salud) | Comprobación de que la API está viva |

> ⏳ **Aviso:** el servicio está en el plan gratuito de Render, que **duerme el servicio tras 15 minutos sin tráfico**. La primera visita después de ese tiempo puede tardar alrededor de un minuto en cargar; las siguientes van rápidas.

## 2. Acceso al frontend (`/panel`)

El backend (FastAPI) sirve el frontend como archivos estáticos en la ruta **`/panel`**, así que no hace falta desplegar el frontend por separado:

1. Entra en <https://pps-appweb-26-27-sju7.onrender.com/panel>.
2. Si no hay sesión iniciada, el panel redirige a la pantalla de **login**.
3. Introduce el email y la contraseña de una de las cuentas de la tabla siguiente (o crea una cuenta nueva con **Registrarse**; empezará con rol `usuario` y la colección vacía).
4. Al iniciar sesión, el panel guarda el **JWT (JSON Web Token)** y lo renueva solo con el *refresh token* mientras se usa.

## 3. Credenciales de base

La base de datos SQLite que se despliega (`APPWEB_AUTH/coleccion_videojuegos.db`) incluye estas cuentas de ejemplo:

| Perfil | Email | Contraseña | Rol | Qué puede hacer |
|--------|-------|-----------|-----|-----------------|
| **Administrador** | `admin@ludoteca.local` | `admin123` | `admin` | Gestionar su colección, crear/editar/borrar el catálogo (juegos, plataformas, géneros, desarrolladoras) y administrar cuentas: cambiar roles, restablecer contraseñas y borrar usuarios |
| **Usuario normal** | `tester@ludoteca.local` | `secreto123` | `usuario` | Gestionar **solo su propia colección**; el catálogo es de solo lectura (cualquier POST/PUT/DELETE sobre él devuelve `403 Forbidden`) |

**Cómo probar cada rol**

- **Admin:** en `/panel/login.html` entra con `admin@ludoteca.local` / `admin123`. Aparecen las opciones de edición del catálogo y la gestión de usuarios.
- **Usuario normal:** cierra sesión y entra con `tester@ludoteca.local` / `secreto123`. Solo se ve y edita la colección propia; las acciones de catálogo y de usuarios no están disponibles.
- **Desde Swagger (`/docs`):** haz `POST /api/auth/login` con el JSON `{"email": "...", "password": "..."}`, copia el `access_token` y pégalo en **Authorize**.

> 🔐 **Nota de seguridad:** son credenciales de demostración publicadas en el repositorio. En un despliegue real habría que cambiarlas nada más arrancar y definir la variable de entorno `LUDOTECA_SECRET_KEY` con una clave propia (si no, se usa la clave de desarrollo que viene en el código).

---

## 4. Comparativa de presupuestos

### 4.1 Qué necesita la aplicación

Para comparar en igualdad de condiciones, se presupuesta lo que la app necesita **tal como está**:

- **1 proceso Python** (FastAPI + Uvicorn) con poca carga: 0,5 vCPU y 512 MB de RAM bastan para una práctica o un uso pequeño.
- **Base de datos SQLite en un archivo**: no hace falta un servidor de base de datos aparte, pero sí **disco persistente** para que los datos no se pierdan al reiniciar o redesplegar.
- **HTTPS** y una URL pública.
- **Tráfico bajo** (unos pocos GB al mes).

Se comparan dos escenarios por proveedor:

- **A – Gratis / demo:** lo que se puede tener sin pagar, con sus limitaciones.
- **B – Mínimo de producción:** siempre encendido y con los datos persistentes.

### 4.2 Render (despliegue actual)

| Concepto | Escenario A | Escenario B |
|----------|-------------|-------------|
| Servicio web | Free – 0 $ (512 MB, 0,1 CPU) | Starter – **7 $/mes** (512 MB, 0,5 CPU) |
| Disco persistente para SQLite | No disponible en Free | 1 GB × 0,25 $/GB = **0,25 $/mes** |
| Plan de espacio de trabajo | Hobby – 0 $ | Hobby – 0 $ |
| **Total** | **0 $/mes** | **≈ 7,25 $/mes (≈ 87 $/año)** |

- El plan Free **se duerme tras 15 minutos sin tráfico** y tarda un minuto en volver. Cada espacio de trabajo tiene **750 horas gratis al mes**.
- En Free **no se pueden añadir discos**, así que el sistema de archivos es efímero: los cambios en la SQLite (usuarios nuevos, colecciones…) **se pierden al redesplegar o reiniciar** y se vuelve al `.db` del repositorio.
- Starter **siempre está encendido**. Para la persistencia hay que añadir un disco (0,25 $/GB) o pasar a Render Postgres (desde unos 6 $/mes, cambiando el código de SQLite a PostgreSQL).
- Ventaja principal: es el que menos trabajo da (despliegue automático desde GitHub y HTTPS incluido).

### 4.3 Amazon Web Services (AWS)

La opción más sencilla y barata en AWS es **Amazon Lightsail** (un VPS (Virtual Private Server, servidor privado virtual) con precio fijo):

| Concepto | Escenario A | Escenario B |
|----------|-------------|-------------|
| Instancia | Lightsail 5 $ **gratis los 3 primeros meses** (cuentas nuevas) | Lightsail Linux – **5 $/mes** (512 MB RAM, 2 vCPU, 20 GB SSD, 1 TB de transferencia) |
| Disco persistente | Incluido (20 GB SSD) | Incluido |
| HTTPS | Certbot / Let's Encrypt (gratis, se configura a mano) | Igual |
| **Total** | **0 $ durante 3 meses** | **≈ 5 $/mes (≈ 60 $/año)** |

- Es un servidor Linux completo: hay que instalar Python, Uvicorn, un proxy inverso (Nginx o Caddy) y el certificado, y además mantener actualizado el sistema.
- El plan de 5 $ tiene **CPU con créditos de ráfaga** (base garantizada baja): va bien para una app con poco tráfico, pero no para carga sostenida.
- Después del periodo gratuito **cobra automáticamente**; si solo es para la práctica, hay que borrar la instancia.
- Alternativas en AWS: EC2 (más flexible, factura más compleja) o App Runner (gestionado, pero sin disco persistente para SQLite y más caro siempre encendido).

### 4.4 Microsoft Azure

La opción equivalente a Render es **Azure App Service para Linux**:

| Concepto | Escenario A | Escenario B |
|----------|-------------|-------------|
| Plan de App Service | F1 Free – 0 $ (recursos compartidos, **60 min de CPU al día**, 1 GB de almacenamiento) | B1 Basic Linux – **≈ 13,14 $/mes** (1 núcleo, 1,75 GB RAM, 10 GB de almacenamiento) |
| Persistencia | Almacenamiento `/home` del plan | Incluido en el plan |
| HTTPS | Dominio `*.azurewebsites.net` | Certificado gestionado gratis |
| **Total** | **0 $/mes** | **≈ 13,14 $/mes (≈ 158 $/año)** |

- El plan **F1 para la app cuando se agota la cuota diaria de CPU** y no tiene SLA (Service Level Agreement, acuerdo de nivel de servicio): solo vale para pruebas.
- B1 da **más RAM que el resto** por el precio, pero es la opción más cara de las cuatro para esta app.
- Se paga **por plan, no por aplicación**: varias apps pequeñas pueden compartir el mismo B1.
- Las cuentas nuevas reciben **200 $ de crédito durante 30 días**.

### 4.5 Google Cloud

| Concepto | Escenario A | Escenario B |
|----------|-------------|-------------|
| Cómputo | Compute Engine **e2-micro** – *Always Free* (2 vCPU compartidas, 1 GB RAM) en `us-west1`, `us-central1` o `us-east1` | e2-micro en una región europea (p. ej. Madrid, `europe-southwest1`) – **≈ 7–9 $/mes** (estimación) |
| Disco persistente | 30 GB de disco estándar gratis | ≈ 0,4–1 $/mes por 10 GB |
| Tráfico de salida | 1 GB/mes gratis | Pago por GB a partir de ahí |
| **Total** | **0 $/mes** (si no se sale de los límites) | **≈ 8–10 $/mes (≈ 96–120 $/año)** |

- La capa *Always Free* **no caduca**, pero solo es gratis en esas tres regiones de EE. UU. y con disco estándar; con SSD, otra región o una máquina mayor ya se cobra.
- Igual que Lightsail, es un servidor que hay que instalar y mantener uno mismo.
- **Cloud Run** también tiene capa gratuita (2 millones de peticiones al mes), pero su sistema de archivos es efímero: con SQLite se perderían los datos, así que habría que migrar a una base de datos gestionada (Cloud SQL), lo que sube mucho el precio.
- Las cuentas nuevas reciben **300 $ de crédito durante 90 días**.
- ⚠️ El precio del escenario B es una **estimación**: depende de la región y conviene confirmarlo en la [calculadora de Google Cloud](https://cloud.google.com/products/calculator).

### 4.6 Resumen

| Proveedor | Servicio | Gratis / demo | Mínimo de producción | Coste anual (B) | Gestión | SQLite persistente |
|-----------|----------|---------------|----------------------|-----------------|---------|--------------------|
| **Render** | Web Service | Sí (se duerme a los 15 min) | **≈ 7,25 $/mes** | ≈ 87 $ | Muy fácil (PaaS (Platform as a Service)) | Solo en planes de pago, con disco |
| **AWS** | Lightsail | 3 meses gratis | **≈ 5 $/mes** | ≈ 60 $ | Media (VPS que se mantiene a mano) | Sí (20 GB SSD) |
| **Azure** | App Service Linux | Sí (F1, 60 min CPU/día) | **≈ 13,14 $/mes** | ≈ 158 $ | Fácil (PaaS) | Sí (10 GB) |
| **Google Cloud** | Compute Engine | Sí, permanente (e2-micro en EE. UU.) | **≈ 8–10 $/mes** (est.) | ≈ 96–120 $ | Media (VM (Virtual Machine) que se mantiene a mano) | Sí (disco persistente) |

> Precios en dólares estadounidenses (USD), **sin IVA** (en España se añadiría un 21 %). Las tarifas cambian con frecuencia y dependen de la región: hay que confirmarlas en la web de cada proveedor antes de contratar.

### 4.7 Conclusión

- **Para la práctica**, el plan **Free de Render** (el despliegue actual) es suficiente: cuesta 0 €, se despliega solo desde GitHub e incluye HTTPS. A cambio, se duerme y los cambios en la base de datos no sobreviven a un redespliegue.
- **Para mantenerla siempre encendida al menor precio**, **AWS Lightsail (≈ 5 $/mes)** es lo más barato e incluye disco para la SQLite, pero toca administrar el servidor.
- **Para mantenerla encendida sin administrar servidores**, **Render Starter + disco (≈ 7,25 $/mes)** es la mejor relación entre precio y comodidad, y no obliga a cambiar nada del código.
- **Azure B1** solo compensa si se van a alojar varias apps en el mismo plan o si ya se trabaja con Microsoft; **Google Cloud** es interesante por su e2-micro gratis para siempre, aceptando la latencia de un servidor en EE. UU. y el mantenimiento manual.

---

## Fuentes

- [Render – Pricing](https://render.com/pricing) · [Render – Deploy for Free](https://render.com/docs/free)
- [Render – How much does cloud application hosting cost](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses)
- [Amazon Lightsail – Pricing](https://aws.amazon.com/lightsail/pricing/)
- [Azure App Service on Linux – Pricing](https://azure.microsoft.com/en-gb/pricing/details/app-service/linux/)
- [Microsoft Q&A – Precio de B1 en Linux](https://learn.microsoft.com/en-us/answers/a/12322935)
- [Google Cloud – Free Tier](https://cloud.google.com/free) · [Google Cloud – Calculadora de precios](https://cloud.google.com/products/calculator)
