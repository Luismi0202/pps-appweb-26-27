/* ============================================================
   Ludoteca · lógica conectada a la API de colección de videojuegos
   ============================================================ */

// Si se abre el HTML como archivo local, apuntamos al servidor; si se sirve
// desde FastAPI, usamos rutas relativas (mismo origen, sin problemas de CORS).
const API = location.protocol === "file:" ? "http://localhost:8000" : "";
const PAGINA_LOGIN = location.protocol === "file:" ? "login.html" : "/panel/login.html";

const CLAVE_TOKEN = "ludoteca_token";
const CLAVE_REFRESH = "ludoteca_refresh";
const CLAVE_USUARIO = "ludoteca_usuario";

/** Cabecera de autorización con el token JWT guardado (o {} si no hay). */
function cabeceraAuth() {
  const token = localStorage.getItem(CLAVE_TOKEN);
  return token ? { Authorization: "Bearer " + token } : {};
}

/** Cierra la sesión y manda al login. */
function cerrarSesion(mensaje) {
  localStorage.removeItem(CLAVE_TOKEN);
  localStorage.removeItem(CLAVE_REFRESH);
  localStorage.removeItem(CLAVE_USUARIO);
  if (mensaje) sessionStorage.setItem("ludoteca_aviso", mensaje);
  location.replace(PAGINA_LOGIN);
}

// Si no hay sesión, fuera: directo al login. Solo basta el refresh token,
// porque con él se renueva el access caducado sin volver a entrar la clave.
if (!localStorage.getItem(CLAVE_TOKEN) && !localStorage.getItem(CLAVE_REFRESH)) {
  location.replace(PAGINA_LOGIN);
}

const state = {
  plataformas: [],
  generos: [],
  desarrolladoras: [],
  catalogo: { pagina: 1, porPagina: 12, q: "", genero: "", plataforma: "",
              desarrolladora: "", orden: "recientes", total: 0, paginas: 1, cargado: false },
  coleccion: { pagina: 1, porPagina: 12, q: "", favorito: false, estado: "",
               orden: "fecha-desc", total: 0, paginas: 1, cargado: false },
  estadisticas: false,
  editando: null,
  usuarios: { pagina: 1, porPagina: 10, q: "", rol: "", total: 0, paginas: 1, cargado: false },
};

/* ---------- Permisos según el rol de la cuenta ---------- */
const ROLES = [
  { valor: "usuario", etq: "Usuario" },
  { valor: "gestor", etq: "Gestor" },
  { valor: "admin", etq: "Administrador" },
];

function etqRol(rol) {
  return (ROLES.find((r) => r.valor === rol) || { etq: rol || "usuario" }).etq;
}

function esAdmin() {
  const u = usuarioGuardado();
  return u.rol === "admin" || u.es_admin === true;
}

function puedeGestionar() {
  const u = usuarioGuardado();
  return u.rol === "gestor" || u.rol === "admin" || u.es_admin === true;
}

const ESTADOS = ["nuevo", "como nuevo", "bueno", "aceptable", "malo", "digital"];

/* ---------- Utilidades ---------- */
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function debounce(fn, ms = 350) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* ---------- Sesión JWT: renovación automática (refresh token) ---------- */
function datosToken(token) {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch (_) {
    return null;
  }
}

/** True si el access token no existe o caduca en menos de `segundos`. */
function accessPorCaducar(segundos = 90) {
  const datos = datosToken(localStorage.getItem(CLAVE_TOKEN) || "");
  if (!datos || !datos.exp) return true;
  return datos.exp - Date.now() / 1000 <= segundos;
}

let renovacionPendiente = null;

/**
 * Cambia el refresh token por un par nuevo de tokens (rotación) sin pedir la
 * contraseña. Solo hay una petición en vuelo aunque lleguen varias a la vez.
 */
function renovarSesion() {
  if (!renovacionPendiente) {
    renovacionPendiente = _renovarSesion().finally(() => {
      renovacionPendiente = null;
    });
  }
  return renovacionPendiente;
}

async function _renovarSesion() {
  const refresh = localStorage.getItem(CLAVE_REFRESH);
  if (!refresh) return false;
  try {
    const res = await fetch(API + "/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false; // refresh caducado o revocado
    const datos = await res.json();
    localStorage.setItem(CLAVE_TOKEN, datos.access_token);
    if (datos.refresh_token) localStorage.setItem(CLAVE_REFRESH, datos.refresh_token);
    if (datos.usuario) localStorage.setItem(CLAVE_USUARIO, JSON.stringify(datos.usuario));
    return true;
  } catch (_) {
    return false;
  }
}

/** Petición cruda: no interpreta los 401 (eso lo hace api()). */
function peticion(ruta, { method = "GET", body } = {}) {
  return fetch(API + ruta, {
    method,
    headers: { "Content-Type": "application/json", ...cabeceraAuth() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function api(ruta, opciones = {}) {
  // Renovación preventiva: si el access token está a punto de caducar, se
  // cambia antes de que la petición llegue a fallar.
  if (accessPorCaducar()) {
    try { await renovarSesion(); } catch (_) { /* lo decidirá el 401 */ }
  }

  let res = await peticion(ruta, opciones);

  if (res.status === 401) {
    // Puede haber caducado entre llamadas: se renueva y se reintenta una vez.
    let renovado = false;
    try { renovado = await renovarSesion(); } catch (_) { renovado = false; }
    if (renovado) res = await peticion(ruta, opciones);
    if (res.status === 401) {
      cerrarSesion("Tu sesión ha caducado. Vuelve a entrar.");
      throw new Error("Sesión caducada");
    }
  }

  if (!res.ok) {
    let mensaje = `Error ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") mensaje = data.detail;
      else if (Array.isArray(data.detail))
        mensaje = data.detail.map((d) => d.msg).join(" · ");
    } catch (_) { /* sin cuerpo */ }
    throw new Error(mensaje);
  }
  return res.status === 204 ? null : res.json();
}

function toast(mensaje, tipo = "ok") {
  const cont = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${tipo}`;
  el.textContent = mensaje;
  cont.appendChild(el);
  setTimeout(() => {
    el.classList.add("salir");
    setTimeout(() => el.remove(), 300);
  }, 3400);
}

function portada(url, titulo) {
  return `<div class="cover">
    <span class="cover-fallback">🎮</span>
    <img loading="lazy" src="${esc(url)}" alt="${esc(titulo)}"
         onerror="this.style.display='none'">
  </div>`;
}

function badgeNota(n) {
  return n == null ? "" : `<span class="badge nota">★ ${Number(n).toFixed(1)}</span>`;
}

function esqueletos(n = 8) {
  return Array.from({ length: n }, () => `<div class="skeleton"></div>`).join("");
}

/* ---------- Pestañas ---------- */
function activarTab(nombre) {
  $$(".tab").forEach((t) => t.classList.toggle("activo", t.dataset.tab === nombre));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${nombre}`));
  if (nombre === "coleccion" && !state.coleccion.cargado) cargarColeccion();
  if (nombre === "estadisticas" && !state.estadisticas) cargarEstadisticas();
  if (nombre === "usuarios" && !state.usuarios.cargado) cargarUsuarios();
}

/* ---------- Carga inicial de catálogos ---------- */
async function cargarFiltros() {
  try {
    const [plataformas, generos, desarrolladoras] = await Promise.all([
      api("/api/plataformas"),
      api("/api/generos"),
      api("/api/desarrolladoras"),
    ]);
    state.plataformas = plataformas;
    state.generos = generos;
    state.desarrolladoras = desarrolladoras;

    const rellenar = (sel, items, texto) => {
      const el = $(sel);
      el.innerHTML = `<option value="">${texto}</option>` +
        items.map((i) => `<option value="${esc(i.nombre)}">${esc(i.nombre)}</option>`).join("");
    };
    rellenar("#filtro-genero", generos, "Todos los géneros");
    rellenar("#filtro-plataforma", plataformas, "Todas las plataformas");
    rellenar("#filtro-desarrolladora", desarrolladoras, "Todas las desarrolladoras");
  } catch (e) {
    toast("No se pudieron cargar los filtros: " + e.message, "error");
  }
}

/* ============================================================
   CATÁLOGO
   ============================================================ */
function queryCatalogo() {
  const c = state.catalogo;
  const p = new URLSearchParams();
  if (c.q) p.set("q", c.q);
  if (c.genero) p.set("genero", c.genero);
  if (c.plataforma) p.set("plataforma", c.plataforma);
  if (c.desarrolladora) p.set("desarrolladora", c.desarrolladora);
  p.set("orden", c.orden);
  p.set("pagina", c.pagina);
  p.set("por_pagina", c.porPagina);
  return p.toString();
}

async function cargarCatalogo() {
  const grid = $("#grid-catalogo");
  grid.innerHTML = esqueletos(state.catalogo.porPagina);
  try {
    const data = await api(`/api/videojuegos?${queryCatalogo()}`);
    Object.assign(state.catalogo, { total: data.total, paginas: data.paginas, cargado: true });
    $("#contador-catalogo").textContent = data.total;
    grid.innerHTML = data.items.length
      ? data.items.map(tarjetaJuego).join("")
      : `<p class="vacio">No hay juegos que coincidan con la búsqueda 😢</p>`;
    renderPager("#pager-catalogo", state.catalogo, (pag) => {
      state.catalogo.pagina = pag; cargarCatalogo();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  } catch (e) {
    grid.innerHTML = `<p class="vacio">Error al cargar el catálogo: ${esc(e.message)}</p>`;
  }
}

function tarjetaJuego(j) {
  const generos = (j.generos || []).slice(0, 2)
    .map((g) => `<span class="chip">${esc(g.nombre)}</span>`).join("");
  return `<article class="card juego" data-id="${j.id}" role="button" tabindex="0">
    ${portada(j.caratula_url, j.titulo)}
    <div class="card-body">
      <div class="card-top">
        <span class="anio">${esc(j.anio_lanzamiento)}</span>
        ${badgeNota(j.puntuacion)}
      </div>
      <h3 class="titulo">${esc(j.titulo)}</h3>
      <div class="chips">${generos}</div>
      <p class="pegi">${j.clasificacion ? esc(j.clasificacion) : ""}</p>
    </div>
    <div class="card-hover">
      <button class="btn btn-primario btn-sm" data-accion="detalle">Ver ficha</button>
    </div>
  </article>`;
}

/* ============================================================
   FICHA DE VIDEOJUEGO (modal)
   ============================================================ */
async function abrirDetalle(id) {
  const cont = $("#modal-detalle .modal-contenido");
  cont.innerHTML = `<div class="cargando">Cargando ficha…</div>`;
  abrirModal("#modal-detalle");
  try {
    const j = await api(`/api/videojuegos/${id}`);
    const plataformas = (j.plataformas || [])
      .map((p) => `<span class="chip">${esc(p.nombre)}</span>`).join("") ||
      `<span class="chip">Sin especificar</span>`;
    const generos = (j.generos || [])
      .map((g) => `<span class="chip">${esc(g.nombre)}</span>`).join("") ||
      `<span class="chip">Sin género</span>`;
    const opcionesPlat = (j.plataformas || [])
      .map((p) => `<option value="${p.id}">${esc(p.nombre)}</option>`).join("");
    const accionesGestion = puedeGestionar()
      ? `<div class="ficha-acciones">
            <button class="btn btn-fantasma btn-sm" data-editar>✏️ Editar juego</button>
            <button class="btn btn-peligro btn-sm" data-borrar>🗑 Eliminar juego</button>
          </div>`
      : "";

    cont.innerHTML = `
      <div class="ficha">
        <div class="ficha-cover">${portada(j.caratula_url, j.titulo)}</div>
        <div>
          <h2>${esc(j.titulo)}</h2>
          <div class="chips">${generos}</div>
          <div class="ficha-meta">
            <div class="meta-caja"><div class="meta-lbl">Año</div><div class="meta-val">${esc(j.anio_lanzamiento)}</div></div>
            <div class="meta-caja"><div class="meta-lbl">Nota</div><div class="meta-val">${j.puntuacion != null ? "★ " + Number(j.puntuacion).toFixed(1) : "—"}</div></div>
            <div class="meta-caja"><div class="meta-lbl">Clasificación</div><div class="meta-val">${j.clasificacion ? esc(j.clasificacion) : "—"}</div></div>
            <div class="meta-caja"><div class="meta-lbl">Desarrolladora</div><div class="meta-val">${j.desarrolladora ? esc(j.desarrolladora.nombre) : "—"}</div></div>
          </div>
          <p class="ficha-desc">${esc(j.descripcion)}</p>
          <div class="seccion-titulo">Plataformas</div>
          <div class="chips">${plataformas}</div>

          <div class="seccion-titulo">Añadir a mi colección</div>
          <form class="form" id="form-anadir">
            <div class="form-fila">
              <label><span>Plataforma</span>
                <select name="plataforma_id">
                  <option value="">Sin plataforma</option>${opcionesPlat}
                </select>
              </label>
              <label><span>Estado</span>
                <select name="estado">${ESTADOS.map((e) => `<option value="${e}">${e}</option>`).join("")}</select>
              </label>
            </div>
            <div class="form-fila">
              <label><span>Valoración (1-10)</span>
                <input type="number" name="valoracion" min="1" max="10" placeholder="—">
              </label>
              <label><span>Precio (€)</span>
                <input type="number" name="precio_compra" min="0" step="0.01" placeholder="0.00">
              </label>
              <label><span>Fecha de compra</span>
                <input type="date" name="fecha_compra">
              </label>
            </div>
            <label style="flex-direction:row;align-items:center;gap:8px">
              <input type="checkbox" name="favorito" style="width:auto"> <span>Marcar como favorito ⭐</span>
            </label>
            <div class="form-acciones">
              <button type="submit" class="btn btn-primario">📚 Añadir a mi colección</button>
            </div>
          </form>

          ${accionesGestion}
        </div>
      </div>`;

    $("#form-anadir", cont).addEventListener("submit", (ev) => {
      ev.preventDefault();
      anadirAColeccion(j, new FormData(ev.target));
    });
    const btnEditar = $("[data-editar]", cont);
    const btnBorrar = $("[data-borrar]", cont);
    if (btnEditar) btnEditar.addEventListener("click", () => abrirFormulario(j));
    if (btnBorrar) btnBorrar.addEventListener("click", () => eliminarJuego(j));
  } catch (e) {
    cont.innerHTML = `<div class="cargando">No se pudo cargar la ficha: ${esc(e.message)}</div>`;
  }
}

async function anadirAColeccion(juego, fd) {
  const numero = (v) => (v === "" || v == null ? null : Number(v));
  try {
    await api("/api/colecciones", {
      method: "POST",
      body: {
        videojuego_id: juego.id,
        plataforma_id: numero(fd.get("plataforma_id")),
        estado: fd.get("estado") || "bueno",
        valoracion: numero(fd.get("valoracion")),
        precio_compra: numero(fd.get("precio_compra")),
        fecha_compra: fd.get("fecha_compra") || null,
        favorito: fd.get("favorito") === "on",
      },
    });
    toast(`«${juego.titulo}» añadido a tu colección 🎉`);
    invalidarColeccion();
    cerrarModal("#modal-detalle");
    activarTab("coleccion");
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ============================================================
   CREAR / EDITAR VIDEOJUEGO (modal formulario)
   ============================================================ */
function abrirFormulario(juego = null) {
  state.editando = juego;
  const cont = $("#modal-form .modal-contenido");
  const editando = Boolean(juego);
  const selPlat = new Set((juego?.plataformas || []).map((p) => p.id));
  const selGen = new Set((juego?.generos || []).map((g) => g.id));

  const chipsOpc = (items, nombre, seleccion) => items.length
    ? items.map((i) => `<label class="chip-opt">
        <input type="checkbox" name="${nombre}" value="${i.id}" ${seleccion.has(i.id) ? "checked" : ""}>
        <span>${esc(i.nombre)}</span>
      </label>`).join("")
    : `<span class="sub">No hay ninguno creado todavía.</span>`;

  cont.innerHTML = `
    <h2 style="margin:0 0 4px">${editando ? "✏️ Editar juego" : "＋ Nuevo juego"}</h2>
    <p class="sub" style="margin:0 0 18px">Los campos marcados son los que devuelve la API en cada ficha.</p>
    <form class="form" id="form-juego">
      <div class="form-fila">
        <label><span>Título *</span>
          <input type="text" name="titulo" required maxlength="200" value="${esc(juego?.titulo ?? "")}">
        </label>
        <label><span>Año *</span>
          <input type="number" name="anio_lanzamiento" required min="1970" max="2035" value="${esc(juego?.anio_lanzamiento ?? new Date().getFullYear())}">
        </label>
      </div>
      <label><span>URL de la carátula *</span>
        <input type="url" name="caratula_url" required
               value="${esc(juego?.caratula_url ?? "")}" placeholder="https://...">
      </label>
      <label><span>Descripción *</span>
        <textarea name="descripcion" required maxlength="4000">${esc(juego?.descripcion ?? "")}</textarea>
      </label>
      <div class="form-fila">
        <label><span>Clasificación</span>
          <input type="text" name="clasificacion" maxlength="20" placeholder="PEGI 12" value="${esc(juego?.clasificacion ?? "")}">
        </label>
        <label><span>Puntuación (0-10)</span>
          <input type="number" name="puntuacion" min="0" max="10" step="0.1" value="${juego?.puntuacion ?? ""}">
        </label>
        <label><span>Desarrolladora</span>
          <select name="desarrolladora_id">
            <option value="">Sin asignar</option>
            ${state.desarrolladoras.map((d) => `<option value="${d.id}" ${juego?.desarrolladora?.id === d.id ? "selected" : ""}>${esc(d.nombre)}</option>`).join("")}
          </select>
        </label>
      </div>
      <div>
        <div class="seccion-titulo" style="margin-top:4px">Plataformas</div>
        <div class="chip-options">${chipsOpc(state.plataformas, "plataformas_ids", selPlat)}</div>
      </div>
      <div>
        <div class="seccion-titulo" style="margin-top:4px">Géneros</div>
        <div class="chip-options">${chipsOpc(state.generos, "generos_ids", selGen)}</div>
      </div>
      <div class="form-acciones">
        <button type="button" class="btn btn-fantasma" data-cerrar>Cancelar</button>
        <button type="submit" class="btn btn-primario">${editando ? "Guardar cambios" : "Crear juego"}</button>
      </div>
    </form>`;

  cerrarModal("#modal-detalle");
  abrirModal("#modal-form");

  $("#form-juego", cont).addEventListener("submit", (ev) => {
    ev.preventDefault();
    guardarJuego(juego, new FormData(ev.target));
  });
}

async function guardarJuego(juego, fd) {
  const numero = (v) => (v === "" || v == null ? null : Number(v));
  const payload = {
    titulo: fd.get("titulo").trim(),
    descripcion: fd.get("descripcion").trim(),
    caratula_url: fd.get("caratula_url").trim(),
    anio_lanzamiento: Number(fd.get("anio_lanzamiento")),
    clasificacion: (fd.get("clasificacion") || "").trim() || null,
    puntuacion: numero(fd.get("puntuacion")),
    desarrolladora_id: numero(fd.get("desarrolladora_id")),
    plataformas_ids: $$('input[name="plataformas_ids"]:checked', $("#form-juego")).map((i) => Number(i.value)),
    generos_ids: $$('input[name="generos_ids"]:checked', $("#form-juego")).map((i) => Number(i.value)),
  };
  try {
    if (juego) {
      await api(`/api/videojuegos/${juego.id}`, { method: "PUT", body: payload });
      toast("Juego actualizado ✔");
    } else {
      await api("/api/videojuegos", { method: "POST", body: payload });
      toast("Juego creado ✔");
    }
    cerrarModal("#modal-form");
    cargarCatalogo();
    invalidarColeccion();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function eliminarJuego(juego) {
  if (!confirm(`¿Eliminar «${juego.titulo}» del catálogo?\nTambién se quitará de tu colección.`)) return;
  try {
    await api(`/api/videojuegos/${juego.id}`, { method: "DELETE" });
    toast("Juego eliminado");
    cerrarModal("#modal-detalle");
    cargarCatalogo();
    invalidarColeccion();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ============================================================
   MI COLECCIÓN
   ============================================================ */
function invalidarColeccion() {
  state.coleccion.cargado = false;
  state.estadisticas = false;
}

function queryColeccion() {
  const c = state.coleccion;
  const p = new URLSearchParams();
  if (c.q) p.set("q", c.q);
  if (c.favorito) p.set("favorito", "true");
  if (c.estado) p.set("estado", c.estado);
  p.set("orden", c.orden);
  p.set("pagina", c.pagina);
  p.set("por_pagina", c.porPagina);
  return p.toString();
}

async function cargarColeccion() {
  const grid = $("#grid-coleccion");
  grid.innerHTML = esqueletos(6);
  try {
    const [data, resumen] = await Promise.all([
      api(`/api/colecciones?${queryColeccion()}`),
      api("/api/estadisticas/resumen"),
    ]);
    Object.assign(state.coleccion, { total: data.total, paginas: data.paginas, cargado: true });
    renderKpis($("#coleccion-kpis"), resumen);
    grid.innerHTML = data.items.length
      ? data.items.map(tarjetaColeccion).join("")
      : `<p class="vacio">Tu colección está vacía con estos filtros 🫙</p>`;
    renderPager("#pager-coleccion", state.coleccion, (pag) => {
      state.coleccion.pagina = pag; cargarColeccion();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  } catch (e) {
    grid.innerHTML = `<p class="vacio">Error al cargar la colección: ${esc(e.message)}</p>`;
  }
}

function tarjetaColeccion(item) {
  const j = item.videojuego;
  return `<article class="card coleccion" data-item="${item.id}">
    ${portada(j.caratula_url, j.titulo)}
    <div class="card-acciones">
      <button class="btn-icon ${item.favorito ? "activo" : ""}" data-accion="favorito"
              title="${item.favorito ? "Quitar de favoritos" : "Marcar favorito"}">★</button>
      <button class="btn-icon peligro" data-accion="eliminar" title="Quitar de la colección">🗑</button>
    </div>
    <div class="card-body">
      <div class="card-top">
        <span class="anio">${esc(j.anio_lanzamiento)}</span>
        ${badgeNota(j.puntuacion)}
      </div>
      <h3 class="titulo" data-accion="detalle" style="cursor:pointer">${esc(j.titulo)}</h3>
      <p class="sub">${item.plataforma ? "🕹️ " + esc(item.plataforma.nombre) : "💾 Sin plataforma"}</p>
      <div class="controles-coleccion">
        <select data-accion="estado">
          ${ESTADOS.map((e) => `<option value="${e}" ${item.estado === e ? "selected" : ""}>${e}</option>`).join("")}
        </select>
        <div class="valoracion">
          <input type="number" class="input-mini" min="1" max="10"
                 value="${item.valoracion ?? ""}" placeholder="–" data-accion="valoracion" title="Valoración">
          <span>/10</span>
        </div>
      </div>
      <p class="precio">${item.precio_compra != null ? item.precio_compra.toFixed(2) + " €" : "—"} · ${item.fecha_compra ?? "sin fecha"}</p>
    </div>
  </article>`;
}

async function actualizarItem(id, cambios, mensaje) {
  try {
    await api(`/api/colecciones/${id}`, { method: "PUT", body: cambios });
    if (mensaje) toast(mensaje);
    invalidarColeccion();
    cargarColeccion();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ============================================================
   ESTADÍSTICAS
   ============================================================ */
async function cargarEstadisticas() {
  const contenedor = $("#stats-resumen");
  contenedor.innerHTML = esqueletos(6);
  try {
    const [resumen, porGenero, porPlataforma, porEstado, top] = await Promise.all([
      api("/api/estadisticas/resumen"),
      api("/api/estadisticas/por-genero"),
      api("/api/estadisticas/por-plataforma"),
      api("/api/estadisticas/por-estado"),
      api("/api/estadisticas/top-valoraciones"),
    ]);
    state.estadisticas = true;
    renderKpis(contenedor, resumen);
    renderBarras($("#chart-generos"), porGenero.map((g) => ({ etq: g.genero, valor: g.juegos })));
    renderBarras($("#chart-plataformas"), porPlataforma.map((p) => ({ etq: p.plataforma, valor: p.juegos })));
    renderBarras($("#chart-estados"), porEstado.map((e) => ({ etq: e.estado, valor: e.cantidad })));
    renderTop($("#top-valoraciones"), top);
  } catch (e) {
    contenedor.innerHTML = `<p class="vacio">Error al cargar estadísticas: ${esc(e.message)}</p>`;
  }
}

function renderKpis(contenedor, r) {
  const fichas = [
    { icono: "🎮", valor: r.videojuegos, etq: "Juegos en catálogo" },
    { icono: "📚", valor: r.ejemplares_en_coleccion, etq: "En mi colección" },
    { icono: "⭐", valor: r.favoritos, etq: "Favoritos" },
    { icono: "🏆", valor: r.valoracion_media != null ? Number(r.valoracion_media).toFixed(2) : "—", etq: "Nota media" },
    { icono: "💰", valor: r.inversion_total != null ? Number(r.inversion_total).toFixed(2) + " €" : "—", etq: "Inversión total" },
    { icono: "🕹️", valor: r.plataformas, etq: "Plataformas" },
  ];
  contenedor.innerHTML = fichas.map((f) => `
    <div class="kpi">
      <span class="kpi-icono">${f.icono}</span>
      <span class="kpi-valor">${esc(f.valor)}</span>
      <span class="kpi-etiqueta">${f.etq}</span>
    </div>`).join("");
}

function renderBarras(contenedor, filas) {
  if (!filas.length) { contenedor.innerHTML = `<p class="sub">Sin datos.</p>`; return; }
  const max = Math.max(...filas.map((f) => f.valor), 1);
  contenedor.innerHTML = filas.map((f) => `
    <div class="barra">
      <span class="barra-etq" title="${esc(f.etq)}">${esc(f.etq)}</span>
      <span class="barra-pista"><span class="barra-relleno" data-ancho="${Math.round((f.valor / max) * 100)}%"></span></span>
      <span class="barra-valor">${f.valor}</span>
    </div>`).join("");
  requestAnimationFrame(() => {
    $$(".barra-relleno", contenedor).forEach((el) => { el.style.width = el.dataset.ancho; });
  });
}

function renderTop(contenedor, items) {
  if (!items.length) { contenedor.innerHTML = `<p class="sub">Todavía no has valorado ningún juego.</p>`; return; }
  contenedor.innerHTML = items.map((item) => {
    const j = item.videojuego;
    return `<li class="top-item">
      <img class="top-mini" src="${esc(j.caratula_url)}" alt="" onerror="this.style.visibility='hidden'">
      <div class="top-txt">
        <span class="top-titulo">${esc(j.titulo)}</span>
        <span class="top-sub">${item.plataforma ? esc(item.plataforma.nombre) : "sin plataforma"} · ${esc(item.estado)}</span>
      </div>
      <span class="top-nota">★ ${item.valoracion}</span>
    </li>`;
  }).join("");
}

/* ============================================================
   USUARIOS (solo admin)
   ============================================================ */
function queryUsuarios() {
  const u = state.usuarios;
  const p = new URLSearchParams();
  if (u.q) p.set("q", u.q);
  if (u.rol) p.set("rol", u.rol);
  p.set("pagina", u.pagina);
  p.set("por_pagina", u.porPagina);
  return p.toString();
}

async function cargarUsuarios() {
  const cont = $("#lista-usuarios");
  cont.innerHTML = esqueletos(6);
  try {
    const data = await api(`/api/usuarios?${queryUsuarios()}`);
    Object.assign(state.usuarios, { total: data.total, paginas: data.paginas, cargado: true });
    $("#contador-usuarios").textContent = data.total;
    cont.innerHTML = data.items.length
      ? data.items.map(filaUsuario).join("")
      : `<p class="vacio">No hay cuentas que coincidan 😶</p>`;
    renderPager("#pager-usuarios", state.usuarios, (pag) => {
      state.usuarios.pagina = pag; cargarUsuarios();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  } catch (e) {
    cont.innerHTML = `<p class="vacio">Error al cargar usuarios: ${esc(e.message)}</p>`;
  }
}

function filaUsuario(u) {
  const yo = usuarioGuardado();
  const esYo = u.id === yo.id;
  const puedeCambiar = esAdmin() && !esYo;
  const motivo = !esAdmin()
    ? "Solo un administrador puede cambiar roles"
    : esYo ? "No puedes cambiar tu propio rol" : "";
  const opciones = ROLES.map((r) =>
    `<option value="${r.valor}" ${u.rol === r.valor ? "selected" : ""}>${r.etq}</option>`
  ).join("");
  return `<article class="fila-usuario" data-id="${u.id}">
    <span class="avatar-fila">${esc((u.nombre || "?").trim().charAt(0).toUpperCase())}</span>
    <div class="fila-datos">
      <span class="fila-nombre">${esc(u.nombre)}${esYo ? ' <span class="yo-tag">tú</span>' : ""}</span>
      <span class="fila-email">${esc(u.email)}</span>
    </div>
    <span class="badge-rol rol-${esc(u.rol)}">${esc(etqRol(u.rol))}</span>
    <select class="select-rol" data-accion="rol"${puedeCambiar ? "" : " disabled"}${motivo ? ` title="${motivo}"` : ""}>
      ${opciones}
    </select>
  </article>`;
}

/* ============================================================
   PAGINADOR
   ============================================================ */
function renderPager(sel, st, irA) {
  const cont = $(sel);
  if (!cont) return;
  cont.innerHTML = `
    <button class="btn btn-fantasma btn-sm" ${st.pagina <= 1 ? "disabled" : ""} data-pag="${st.pagina - 1}">← Anterior</button>
    <span class="pager-info">Página <b>${st.pagina}</b> de <b>${st.paginas}</b> · ${st.total} resultado${st.total === 1 ? "" : "s"}</span>
    <button class="btn btn-fantasma btn-sm" ${st.pagina >= st.paginas ? "disabled" : ""} data-pag="${st.pagina + 1}">Siguiente →</button>`;
  cont.onclick = (e) => {
    const boton = e.target.closest("[data-pag]");
    if (boton && !boton.disabled) irA(Number(boton.dataset.pag));
  };
}

/* ============================================================
   MODALES
   ============================================================ */
function abrirModal(sel) {
  $(sel).hidden = false;
  document.body.classList.add("sin-scroll");
}
function cerrarModal(sel) {
  $(sel).hidden = true;
  if (!$(".modal-fondo:not([hidden])")) document.body.classList.remove("sin-scroll");
}

/* ============================================================
   EVENTOS
   ============================================================ */
function conectarEventos() {
  $("#tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (tab) activarTab(tab.dataset.tab);
  });

  $("#btn-nuevo").addEventListener("click", () => abrirFormulario(null));

  // Catálogo: filtros
  $("#buscar-catalogo").addEventListener("input", debounce((e) => {
    state.catalogo.q = e.target.value.trim();
    state.catalogo.pagina = 1;
    cargarCatalogo();
  }));
  ["genero", "plataforma", "desarrolladora", "orden"].forEach((campo) => {
    $(`#filtro-${campo}`).addEventListener("change", (e) => {
      state.catalogo[campo] = e.target.value;
      state.catalogo.pagina = 1;
      cargarCatalogo();
    });
  });
  $("#btn-reset").addEventListener("click", () => {
    Object.assign(state.catalogo, { q: "", genero: "", plataforma: "", desarrolladora: "", orden: "recientes", pagina: 1 });
    $("#buscar-catalogo").value = "";
    ["genero", "plataforma", "desarrolladora"].forEach((c) => $(`#filtro-${c}`).value = "");
    $("#filtro-orden").value = "recientes";
    cargarCatalogo();
  });

  // Catálogo: clic en tarjeta
  $("#grid-catalogo").addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (card) abrirDetalle(Number(card.dataset.id));
  });
  $("#grid-catalogo").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const card = e.target.closest(".card");
      if (card) abrirDetalle(Number(card.dataset.id));
    }
  });

  // Colección: filtros
  $("#buscar-coleccion").addEventListener("input", debounce((e) => {
    state.coleccion.q = e.target.value.trim();
    state.coleccion.pagina = 1;
    cargarColeccion();
  }));
  $("#filtro-estado").addEventListener("change", (e) => {
    state.coleccion.estado = e.target.value;
    state.coleccion.pagina = 1;
    cargarColeccion();
  });
  $("#filtro-fav").addEventListener("change", (e) => {
    state.coleccion.favorito = e.target.checked;
    state.coleccion.pagina = 1;
    cargarColeccion();
  });
  $("#filtro-orden-coleccion").addEventListener("change", (e) => {
    state.coleccion.orden = e.target.value;
    state.coleccion.pagina = 1;
    cargarColeccion();
  });

  // Colección: acciones sobre cada tarjeta
  const gridColeccion = $("#grid-coleccion");
  gridColeccion.addEventListener("click", async (e) => {
    const card = e.target.closest("[data-item]");
    if (!card) return;
    const id = Number(card.dataset.item);

    const accion = e.target.closest("[data-accion]")?.dataset.accion;
    if (accion === "detalle") {
      // Necesitamos el id del videojuego: lo obtenemos de la lista actual
      const item = await api(`/api/colecciones/${id}`);
      abrirDetalle(item.videojuego.id);
      return;
    }
    if (accion === "favorito") {
      const boton = e.target.closest("[data-accion=favorito]");
      const esFav = boton.classList.contains("activo");
      try {
        await api(`/api/colecciones/${id}/favorito`, { method: "PATCH", body: { favorito: !esFav } });
        toast(!esFav ? "Marcado como favorito ⭐" : "Quitado de favoritos");
        invalidarColeccion();
        cargarColeccion();
      } catch (err) { toast(err.message, "error"); }
      return;
    }
    if (accion === "eliminar") {
      if (!confirm("¿Quitar este juego de tu colección?")) return;
      try {
        await api(`/api/colecciones/${id}`, { method: "DELETE" });
        toast("Quitado de la colección");
        invalidarColeccion();
        cargarColeccion();
      } catch (err) { toast(err.message, "error"); }
    }
  });

  gridColeccion.addEventListener("change", (e) => {
    const card = e.target.closest("[data-item]");
    if (!card) return;
    const id = Number(card.dataset.item);
    if (e.target.dataset.accion === "estado") {
      actualizarItem(id, { estado: e.target.value }, "Estado actualizado");
    } else if (e.target.dataset.accion === "valoracion") {
      const v = e.target.value === "" ? null : Number(e.target.value);
      actualizarItem(id, { valoracion: v }, "Valoración guardada");
    }
  });

  // Usuarios (admin): búsqueda, filtro por rol y asignación de rol.
  $("#buscar-usuarios").addEventListener("input", debounce((e) => {
    state.usuarios.q = e.target.value.trim();
    state.usuarios.pagina = 1;
    cargarUsuarios();
  }));
  $("#filtro-rol").addEventListener("change", (e) => {
    state.usuarios.rol = e.target.value;
    state.usuarios.pagina = 1;
    cargarUsuarios();
  });
  $("#lista-usuarios").addEventListener("change", async (e) => {
    const sel = e.target.closest('[data-accion="rol"]');
    if (!sel || sel.disabled || !esAdmin()) return;
    const id = Number(sel.closest("[data-id]").dataset.id);
    try {
      await api(`/api/usuarios/${id}/rol`, { method: "PATCH", body: { rol: sel.value } });
      toast("Rol actualizado ✔");
      cargarUsuarios();
    } catch (err) {
      toast(err.message, "error");
      cargarUsuarios();
    }
  });

  // Modales: cerrar con botón, fondo o Escape
  $$(".modal-fondo").forEach((fondo) => {
    fondo.addEventListener("click", (e) => {
      if (e.target === fondo || e.target.closest("[data-cerrar]")) cerrarModal(`#${fondo.id}`);
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$(".modal-fondo:not([hidden])").forEach((f) => cerrarModal(`#${f.id}`));
  });
}

/* ---------- Comprobar estado de la API ---------- */
async function comprobarSalud() {
  const el = $("#pie-estado");
  try {
    await api("/api/salud");
    el.textContent = "API conectada";
    el.classList.add("ok");
  } catch (_) {
    el.textContent = "API sin conexión";
    el.classList.add("error");
  }
}

/* ---------- Sesión: chip de usuario ---------- */
function pintarUsuario(usuario) {
  const chip = $("#usuario-chip");
  chip.hidden = false;
  const nombre = usuario.nombre || usuario.email || "jugador";
  $("#usuario-nombre").textContent = nombre;
  $("#usuario-avatar").textContent = nombre.trim().charAt(0).toUpperCase() || "?";

  // Rol actual en el chip.
  const rol = usuario.rol || (usuario.es_admin ? "admin" : "usuario");
  const etiqueta = $("#usuario-rol");
  etiqueta.textContent = etqRol(rol);
  etiqueta.className = `usuario-rol rol-${rol}`;

  // Permisos: el catálogo lo gestionan admin y gestor; la pestaña de usuarios
  // la ven ambos, pero solo el admin puede cambiar roles (ver filaUsuario).
  $("#btn-nuevo").hidden = !puedeGestionar();
  $("#tab-btn-usuarios").hidden = !puedeGestionar();
}

function usuarioGuardado() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_USUARIO) || "null");
  } catch (_) {
    return null;
  }
}

/* ---------- Arranque ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  // Aviso procedente del login (sesión caducada, etc.).
  const aviso = sessionStorage.getItem("ludoteca_aviso");
  if (aviso) {
    sessionStorage.removeItem("ludoteca_aviso");
    toast(aviso, "error");
  }

  // Pinta el chip con los datos guardados y, si no los hay, pídelos a la API.
  const guardado = usuarioGuardado();
  if (guardado) pintarUsuario(guardado);

  $("#btn-salir").addEventListener("click", () => {
    if (confirm("¿Cerrar sesión?")) cerrarSesion();
  });

  conectarEventos();
  comprobarSalud();
  await cargarFiltros();
  cargarCatalogo();

  // Verifica el token y refresca el nombre real del usuario.
  try {
    const usuario = await api("/api/auth/yo");
    localStorage.setItem(CLAVE_USUARIO, JSON.stringify(usuario));
    pintarUsuario(usuario);
  } catch (_) { /* api() ya redirige si es 401 */ }
});
