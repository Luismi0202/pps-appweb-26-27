/* ============================================================
   Ludoteca · login social (Google / GitHub)
   ------------------------------------------------------------
   Se carga ANTES que auth.js. Dos tareas:

   1. Al volver del proveedor, la API redirige a
      login.html#oauth=<tokens en base64url>. Aquí se guardan en
      localStorage con las MISMAS claves que usa el login normal y se
      limpia la URL. Después, auth.js ve el token y entra al panel.
      (También puede llegar #oauth_error=<mensaje>.)
   2. Pregunta a la API qué proveedores están configurados y muestra
      sus botones "Continuar con…".
   ============================================================ */
(() => {
  const API_OAUTH = location.protocol === "file:" ? "http://localhost:8000" : "";
  let errorOAuth = "";

  function decodificarBase64Url(texto) {
    const b64 = texto.replace(/-/g, "+").replace(/_/g, "/")
      + "===".slice((texto.length + 3) % 4);
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  // --- 1. Recoger la sesión que devuelve la API (se hace ya, sin esperar
  //        al DOMContentLoaded, para que auth.js la encuentre al arrancar).
  const fragmento = new URLSearchParams(location.hash.slice(1));
  if (fragmento.has("oauth") || fragmento.has("oauth_error")) {
    // Quita los tokens de la barra de direcciones y del historial.
    history.replaceState(null, "", location.pathname + location.search);
    if (fragmento.has("oauth")) {
      try {
        const sesion = decodificarBase64Url(fragmento.get("oauth"));
        localStorage.setItem("ludoteca_token", sesion.access_token);
        localStorage.setItem("ludoteca_refresh", sesion.refresh_token);
        localStorage.setItem("ludoteca_usuario", JSON.stringify(sesion.usuario));
      } catch (_) {
        errorOAuth = "No se pudo completar el inicio de sesión. Inténtalo de nuevo.";
      }
    } else {
      errorOAuth = fragmento.get("oauth_error") || "No se pudo iniciar sesión.";
    }
  }

  // --- 2. Botones y avisos (cuando el HTML ya está cargado).
  document.addEventListener("DOMContentLoaded", async () => {
    if (errorOAuth) {
      const aviso = document.getElementById("auth-aviso");
      if (aviso) { aviso.textContent = errorOAuth; aviso.hidden = false; }
    }

    const bloque = document.getElementById("auth-social");
    if (!bloque) return;
    try {
      const res = await fetch(API_OAUTH + "/api/auth/oauth/proveedores");
      if (!res.ok) return;
      const disponibles = await res.json();
      let alguno = false;
      bloque.querySelectorAll("[data-proveedor]").forEach((boton) => {
        const prov = boton.dataset.proveedor;
        boton.href = `${API_OAUTH}/api/auth/oauth/${prov}/login`;
        boton.hidden = !disponibles[prov];
        alguno = alguno || Boolean(disponibles[prov]);
      });
      bloque.hidden = !alguno;
    } catch (_) {
      /* Sin API o sin proveedores: solo queda el login con contraseña. */
    }
  });
})();
