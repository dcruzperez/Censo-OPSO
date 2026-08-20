/**
 * Autoguardado local de formularios de encuesta (HU-21).
 *
 * ------------------------------------------------------------------------
 * POR QUÉ EXISTE
 * ------------------------------------------------------------------------
 * OPSO es "vistas renderizadas en servidor con plantillas", sin JavaScript
 * de aplicación ni API REST (ver CLAUDE.md). Este archivo es la primera
 * excepción deliberada a esa regla, y acotada a propósito: un censista en
 * terreno con conexión intermitente puede perder lo que llevaba escrito si
 * la señal se corta ANTES de enviar el formulario (se queda sin cobertura a
 * medio llenar la ficha, se le acaba la batería y el navegador descarta la
 * pestaña, sale sin querer). El servidor no puede proteger contra eso: no
 * hay conexión para avisarle. Solo el propio navegador puede.
 *
 * ------------------------------------------------------------------------
 * QUÉ NO HACE
 * ------------------------------------------------------------------------
 * No es una app offline. No intercepta la carga de la página (no hay
 * service worker), no guarda encuestas completas para reenviarlas después,
 * y no funciona si el navegador no puede ni siquiera ABRIR la pantalla —
 * eso exigiría poder servir la página sin red, que es un cambio de
 * arquitectura que esta historia no pidió (ver docs/HU-21_*.md). Cubre
 * exactamente el problema real de una conexión que se corta A RATOS: el
 * navegador sigue pudiendo cargar la pantalla: solo hay que protegerse de
 * un envío que no llega a tiempo.
 *
 * ------------------------------------------------------------------------
 * QUÉ GUARDA Y CUÁNDO SE BORRA
 * ------------------------------------------------------------------------
 * Los valores de los campos de texto, número, fecha y desplegable del
 * formulario (NO las casillas de verificación: dos de ellas,
 * "confirmar_duplicado" y "confirmar_lejania", son banderas de confirmación
 * de ESTE intento de envío, y restaurar una marcada de un intento anterior
 * podría saltarse una validación que ya no aplica; la tercera,
 * "tiene_discapacidad", es la única casilla con datos reales y perder un
 * solo campo booleano no justifica la complejidad de tratarla aparte). Se
 * borra al enviar el formulario (se asume que el envío va a llegar) y al
 * apretar "Descartar" en el aviso de recuperación.
 *
 * Uso, en cada plantilla que lo necesite:
 *
 *     {% block js_extra %}
 *     <script src="{% static 'js/autoguardado.js' %}"></script>
 *     <script>OPSOAutoguardado.iniciar("vivienda-42");</script>
 *     {% endblock %}
 */
(function () {
  "use strict";

  var PREFIJO_CLAVE = "opso:borrador:";
  var DEMORA_DEBOUNCE_MS = 800;
  var INTERVALO_RESPALDO_MS = 5000;
  var HORAS_EXPIRACION_POR_DEFECTO = 24;

  // Tipos de campo que NO se autoguardan: csrf y ocultos (no son texto que
  // el censista haya escrito), archivos (no caben en localStorage) y
  // casillas/radios (ver la razón en el comentario de cabecera).
  var TIPOS_EXCLUIDOS = [
    "hidden",
    "checkbox",
    "radio",
    "file",
    "submit",
    "button",
    "reset",
  ];

  function camposGuardables(formulario) {
    var todos = formulario.querySelectorAll("input[name], select[name], textarea[name]");
    return Array.prototype.filter.call(todos, function (campo) {
      return (
        campo.name !== "csrfmiddlewaretoken" &&
        TIPOS_EXCLUIDOS.indexOf(campo.type) === -1
      );
    });
  }

  function leerValores(campos) {
    var valores = {};
    campos.forEach(function (campo) {
      valores[campo.name] = campo.value;
    });
    return valores;
  }

  function iniciar(clave, expiraHoras) {
    // "main form" y no "form" a secas: base.html tiene un <form> propio para
    // el botón de cerrar sesión de la barra de navegación, ANTES en el HTML
    // que el contenido de la página. Un selector sin acotar ataría el
    // autoguardado a ese formulario en vez de al de la encuesta.
    var formulario = document.querySelector("main form");
    if (!formulario) {
      return;
    }

    var claveCompleta = PREFIJO_CLAVE + clave;
    var horasExpiracion =
      typeof expiraHoras === "number" ? expiraHoras : HORAS_EXPIRACION_POR_DEFECTO;
    var temporizadorDebounce = null;

    function guardar() {
      try {
        localStorage.setItem(
          claveCompleta,
          JSON.stringify({
            valores: leerValores(camposGuardables(formulario)),
            guardadoEn: Date.now(),
          })
        );
      } catch (error) {
        // localStorage lleno, deshabilitado (modo privado) o inexistente:
        // el formulario sigue funcionando igual que antes de esta historia,
        // solo sin la protección extra.
      }
    }

    function guardarConDemora() {
      clearTimeout(temporizadorDebounce);
      temporizadorDebounce = setTimeout(guardar, DEMORA_DEBOUNCE_MS);
    }

    function borrar() {
      try {
        localStorage.removeItem(claveCompleta);
      } catch (error) {
        // Igual que en guardar(): sin localStorage no hay nada que limpiar.
      }
    }

    function mostrarAvisoDeRecuperacion() {
      var aviso = document.createElement("div");
      aviso.className =
        "alert alert-warning small d-flex justify-content-between " +
        "align-items-center gap-2 flex-wrap mb-3";
      aviso.setAttribute("role", "status");
      aviso.setAttribute("aria-live", "polite");
      aviso.innerHTML =
        "<span>Recuperamos lo que estabas completando antes de que se " +
        "cortara la conexión o se cerrara la pantalla.</span>" +
        '<button type="button" class="btn btn-sm btn-outline-dark">Descartar</button>';

      aviso.querySelector("button").addEventListener("click", function () {
        borrar();
        formulario.reset();
        aviso.remove();
      });

      formulario.parentNode.insertBefore(aviso, formulario);
    }

    function restaurar() {
      var crudo;
      try {
        crudo = localStorage.getItem(claveCompleta);
      } catch (error) {
        return;
      }
      if (!crudo) {
        return;
      }

      var borrador;
      try {
        borrador = JSON.parse(crudo);
      } catch (error) {
        borrar(); // un valor corrupto no sirve ni para reintentarlo
        return;
      }

      var horasTranscurridas = (Date.now() - borrador.guardadoEn) / 3600000;
      if (horasTranscurridas > horasExpiracion) {
        borrar();
        return;
      }

      var huboAlgoQueRestaurar = false;
      camposGuardables(formulario).forEach(function (campo) {
        var valorGuardado = borrador.valores[campo.name];
        if (valorGuardado && valorGuardado !== campo.value) {
          campo.value = valorGuardado;
          huboAlgoQueRestaurar = true;
        }
      });

      if (huboAlgoQueRestaurar) {
        mostrarAvisoDeRecuperacion();
      }
    }

    restaurar();

    formulario.addEventListener("input", guardarConDemora);
    formulario.addEventListener("change", guardarConDemora);

    // Red de respaldo: un valor puesto por OTRO script (la captura de GPS de
    // ubicacion_form.html, por ejemplo) no dispara "input" ni "change" al
    // asignarse por código, así que sin este muestreo periódico ese dato no
    // quedaría protegido.
    setInterval(guardar, INTERVALO_RESPALDO_MS);

    // Se asume que el envío va a llegar al servidor: es la misma apuesta
    // optimista que hacen los borradores de Gmail o de WordPress. Si el envío
    // falla igual por falta de conexión, el navegador no navega a ningún
    // lado y el formulario sigue en pantalla con lo ya escrito — no se pierde
    // nada en ese instante. El caso que de verdad importaba proteger era el
    // de ANTES de apretar enviar, y ese ya quedó cubierto.
    formulario.addEventListener("submit", borrar);
  }

  window.OPSOAutoguardado = { iniciar: iniciar };
})();
