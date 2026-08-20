/**
 * Actualización automática de los paneles (HU-23).
 *
 * ------------------------------------------------------------------------
 * QUÉ HACE Y QUÉ NO HACE
 * ------------------------------------------------------------------------
 * Las vistas de los paneles ya consultan la base de datos en cada carga —no
 * hay ningún caché de por medio—, así que "tiempo real" no necesitaba una
 * conexión persistente (WebSockets) ni sondeo por AJAX: alcanza con volver a
 * pedir la página completa cada cierto tiempo. Este script solo decide
 * CUÁNDO recargar y muestra una cuenta regresiva visible; no cambia qué
 * datos se muestran ni cómo se calculan.
 *
 * Se usa SOLO en los dos paneles de solo lectura (supervisor y
 * administrador). No se puso en pantallas con formularios o filtros —la
 * bandeja de revisión, por ejemplo— porque ahí una recarga automática sí
 * podría interrumpir algo a medio llenar. Ver docs/HU-23_*.md.
 *
 * ------------------------------------------------------------------------
 * POR QUÉ SE PAUSA CON LA PESTAÑA EN SEGUNDO PLANO
 * ------------------------------------------------------------------------
 * Recargar una pestaña que nadie está mirando no cumple ningún propósito:
 * solo gasta batería y ancho de banda. La cuenta regresiva se detiene
 * mientras `document.hidden` es verdadero y se reinicia entera al volver,
 * en vez de recargar de golpe con el tiempo acumulado de fondo.
 *
 * Uso, en la plantilla:
 *
 *     {% block js_extra %}
 *     <script src="{% static 'js/actualizacion_automatica.js' %}"></script>
 *     <script>OPSOActualizacionAutomatica.iniciar();</script>
 *     {% endblock %}
 *
 * Y en el HTML, un elemento para el texto de la cuenta regresiva:
 *
 *     <span id="opso-actualizacion-indicador" role="status" aria-live="polite"></span>
 */
(function () {
  "use strict";

  var SEGUNDOS_POR_DEFECTO = 30;

  function iniciar(segundos) {
    var indicador = document.getElementById("opso-actualizacion-indicador");
    var total = typeof segundos === "number" ? segundos : SEGUNDOS_POR_DEFECTO;
    var restantes = total;

    function mostrar() {
      if (indicador) {
        indicador.textContent = "Se actualiza en " + restantes + " s";
      }
    }

    function tick() {
      if (document.hidden) {
        return; // pestaña en segundo plano: no cuenta, no recarga
      }
      restantes -= 1;
      if (restantes <= 0) {
        location.reload();
        return;
      }
      mostrar();
    }

    mostrar();
    setInterval(tick, 1000);

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        restantes = total;
        mostrar();
      }
    });
  }

  window.OPSOActualizacionAutomatica = { iniciar: iniciar };
})();
