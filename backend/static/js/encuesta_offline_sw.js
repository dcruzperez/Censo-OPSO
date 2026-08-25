"use strict";

/* Service worker del asistente de captura sin conexión (HU-24).
 *
 * Alcance deliberadamente mínimo: guarda en caché SOLO lo necesario para que
 * "/encuestas/nueva/" pueda abrirse con cero señal desde el arranque (celular
 * reiniciado, app cerrada del todo). No cachea datos, no cachea ninguna otra
 * pantalla del sitio y nunca intercepta un POST: la sincronización va siempre
 * a la red real, tal cual.
 *
 * Se sirve desde /sw.js en la raíz del dominio (ver ServirServiceWorkerView
 * en fichas/views.py) y no desde /static/js/..., porque el "scope" de un
 * service worker no puede ser más amplio que la ruta desde la que el
 * navegador lo obtuvo: servido bajo /static/ solo podría vigilar /static/.
 */

var CACHE = "opso-offline-v1";
var PAGINA_PRINCIPAL = "/encuestas/nueva/";

// --------------------------------------------------------------------------
// INSTALL: precachea la página y, LEYENDO SU PROPIO HTML, los <script src> y
// <link href> que apunten a /static/. No se hardcodean los nombres de esos
// archivos a propósito: en producción, ManifestStaticFilesStorage los sirve
// con un hash en el nombre que cambia en cada despliegue (ver
// config/settings.py), así que la única forma correcta de saber la URL
// exacta es leerla de la página ya renderizada, no adivinarla aquí.
// --------------------------------------------------------------------------

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    fetch(PAGINA_PRINCIPAL)
      .then(function (respuesta) {
        var paraCachear = respuesta.clone();

        return respuesta.text().then(function (html) {
          var urls = [];
          var patron = /(?:src|href)="(\/static\/[^"]+)"/g;
          var coincidencia = patron.exec(html);

          while (coincidencia !== null) {
            urls.push(coincidencia[1]);
            coincidencia = patron.exec(html);
          }

          return caches.open(CACHE).then(function (cache) {
            return cache.put(PAGINA_PRINCIPAL, paraCachear).then(function () {
              return Promise.all(
                urls.map(function (url) {
                  return fetch(url).then(function (r) {
                    if (r.ok) return cache.put(url, r);
                  });
                })
              );
            });
          });
        });
      })
      .then(function () {
        return self.skipWaiting();
      })
      .catch(function () {
        // Si install ocurre sin conexión, el navegador de todas formas tuvo
        // que descargar este mismo archivo con red hace un instante, así que
        // el caso es rarísimo. Si pasa, no hay nada que precachear todavía;
        // el fetch handler de abajo lo va completando en cuanto haya señal.
      })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches
      .keys()
      .then(function (nombres) {
        return Promise.all(
          nombres
            .filter(function (nombre) {
              return nombre !== CACHE;
            })
            .map(function (nombre) {
              return caches.delete(nombre);
            })
        );
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

// --------------------------------------------------------------------------
// FETCH: red primero, caché como respaldo. Cada visita con señal refresca lo
// que hay cacheado; sin señal, se sirve lo último que se guardó. Solo se
// intercepta lo que está dentro del alcance de este service worker — todo lo
// demás (el resto del sitio, y sobre todo cualquier POST) sigue el
// comportamiento normal del navegador, como si este archivo no existiera.
// --------------------------------------------------------------------------

function dentroDelAlcance(pathname) {
  if (pathname === PAGINA_PRINCIPAL) return true;
  if (pathname.indexOf("/static/js/encuesta_offline") === 0) return true;
  if (pathname.indexOf("/static/vendor/") === 0) return true;
  if (pathname.indexOf("/static/css/") === 0) return true;
  return false;
}

self.addEventListener("fetch", function (evento) {
  var peticion = evento.request;

  if (peticion.method !== "GET") return;

  var ruta = new URL(peticion.url).pathname;
  if (!dentroDelAlcance(ruta)) return;

  evento.respondWith(
    fetch(peticion)
      .then(function (respuesta) {
        var copia = respuesta.clone();
        caches.open(CACHE).then(function (cache) {
          cache.put(peticion, copia);
        });
        return respuesta;
      })
      .catch(function () {
        return caches.match(peticion).then(function (enCache) {
          return enCache || Response.error();
        });
      })
  );
});
