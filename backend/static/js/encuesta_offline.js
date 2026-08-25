"use strict";

/* Asistente de captura de encuestas sin conexión (HU-24).
 *
 * Reemplaza el mecanismo de la HU-21 para el caso de crear una encuesta nueva:
 * en vez de proteger UN formulario mientras se espera que el submit llegue al
 * servidor, este módulo hace vivienda, hogar, integrantes y ubicación enteros
 * en el navegador y los guarda en IndexedDB, sin ningún POST intermedio. El
 * único contacto con el servidor es la sincronización, que reutiliza los
 * mismos Django forms del flujo online (ver SincronizarEncuestaOfflineView).
 *
 * Dos puntos de entrada:
 *   OPSOEncuestaOffline.iniciarAsistente()      -> fichas/encuesta_offline.html
 *   OPSOEncuestaOffline.iniciarCola(opciones)   -> fichas/mis_encuestas.html
 *
 * Comparten el mismo almacén de IndexedDB: una encuesta "en progreso" en el
 * asistente y una encuesta "pendiente de sincronizar" en la cola son el MISMO
 * registro, solo que con `estadoLocal` distinto — no hay dos copias que
 * puedan desincronizarse entre sí.
 */
window.OPSOEncuestaOffline = (function () {
  var NOMBRE_BD = "opso-encuestas-offline";
  var VERSION_BD = 1;
  var ALMACEN = "encuestas";

  // ------------------------------------------------------------------
  // INDEXEDDB — un registro por encuesta, con clienteId (UUID generado en
  // este teléfono) como clave. Sobrevive a cerrar la pestaña, el navegador o
  // reiniciar el teléfono, que es justo lo que localStorage (HU-21) no podía
  // garantizar para algo tan grande como una encuesta completa.
  // ------------------------------------------------------------------

  function abrirBD() {
    return new Promise(function (resolver, rechazar) {
      var peticion = indexedDB.open(NOMBRE_BD, VERSION_BD);

      peticion.onupgradeneeded = function () {
        var bd = peticion.result;
        if (!bd.objectStoreNames.contains(ALMACEN)) {
          bd.createObjectStore(ALMACEN, { keyPath: "clienteId" });
        }
      };
      peticion.onsuccess = function () {
        resolver(peticion.result);
      };
      peticion.onerror = function () {
        rechazar(peticion.error);
      };
    });
  }

  function guardarRegistro(registro) {
    return abrirBD().then(function (bd) {
      return new Promise(function (resolver, rechazar) {
        var transaccion = bd.transaction(ALMACEN, "readwrite");
        transaccion.objectStore(ALMACEN).put(registro);
        transaccion.oncomplete = function () {
          resolver(registro);
        };
        transaccion.onerror = function () {
          rechazar(transaccion.error);
        };
      });
    });
  }

  function eliminarRegistro(clienteId) {
    return abrirBD().then(function (bd) {
      return new Promise(function (resolver, rechazar) {
        var transaccion = bd.transaction(ALMACEN, "readwrite");
        transaccion.objectStore(ALMACEN).delete(clienteId);
        transaccion.oncomplete = resolver;
        transaccion.onerror = function () {
          rechazar(transaccion.error);
        };
      });
    });
  }

  function listarRegistros() {
    return abrirBD().then(function (bd) {
      return new Promise(function (resolver, rechazar) {
        var transaccion = bd.transaction(ALMACEN, "readonly");
        var peticion = transaccion.objectStore(ALMACEN).getAll();
        peticion.onsuccess = function () {
          resolver(peticion.result || []);
        };
        peticion.onerror = function () {
          rechazar(peticion.error);
        };
      });
    });
  }

  function generarUUID() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    // Respaldo para navegadores sin crypto.randomUUID (poco probable en un
    // teléfono moderno, pero un UUID mal formado solo importaría si dos
    // colisionaran, y esto ya es criptográficamente improbable).
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // ------------------------------------------------------------------
  // RUT — el mismo algoritmo que usuarios/validators.py (calcular_digito_
  // verificador), portado para dar feedback inmediato sin depender del
  // servidor. La comprobación que SÍ depende del servidor —que no se repita
  // dentro del mismo hogar— la sigue haciendo únicamente IntegranteForm.
  // clean_rut() al sincronizar.
  // ------------------------------------------------------------------

  function limpiarRut(valor) {
    if (!valor) return "";
    var limpio = String(valor).trim().toUpperCase().replace(/\./g, "").replace(/\s/g, "");
    if (limpio.indexOf("-") === -1 && limpio.length > 1) {
      limpio = limpio.slice(0, -1) + "-" + limpio.slice(-1);
    }
    return limpio;
  }

  function calcularDV(cuerpo) {
    var suma = 0;
    var multiplicador = 2;

    for (var i = cuerpo.length - 1; i >= 0; i--) {
      suma += parseInt(cuerpo.charAt(i), 10) * multiplicador;
      multiplicador = multiplicador === 7 ? 2 : multiplicador + 1;
    }

    var resto = 11 - (suma % 11);
    if (resto === 11) return "0";
    if (resto === 10) return "K";
    return String(resto);
  }

  function rutValido(valorBruto) {
    var limpio = limpiarRut(valorBruto);
    if (!limpio) return true; // el RUT es opcional en todos los formularios que lo usan

    var partes = /^(\d{7,8})-([\dkK])$/.exec(limpio);
    if (!partes) return false;

    return calcularDV(partes[1]) === partes[2].toUpperCase();
  }

  function calcularEdad(fechaISO) {
    var hoy = new Date();
    var nacimiento = new Date(fechaISO + "T00:00:00");
    var edad = hoy.getFullYear() - nacimiento.getFullYear();
    var mes = hoy.getMonth() - nacimiento.getMonth();

    if (mes < 0 || (mes === 0 && hoy.getDate() < nacimiento.getDate())) {
      edad -= 1;
    }

    return edad;
  }

  // ------------------------------------------------------------------
  // EL ASISTENTE — fichas/encuesta_offline.html
  // ------------------------------------------------------------------

  function iniciarAsistente() {
    var datos = JSON.parse(document.getElementById("opso-datos-iniciales").textContent);
    var PASOS = ["vivienda", "hogar", "integrantes", "ubicacion", "resultado"];

    var registro = registroVacio();
    var pasoActual = 0;

    var elForm = document.getElementById("of-form");
    var elConfirmacion = document.getElementById("of-confirmacion");
    var elMensaje = document.getElementById("of-mensaje");
    var elIndicador = document.getElementById("of-paso-indicador");

    // Nada de este formulario se envía nunca por el método nativo del
    // navegador: cada paso lo maneja este script. Sin este freno, el teclado
    // de un teléfono (botón "Ir"/"Siguiente") o pulsar Enter en un campo de
    // texto dispararía un submit real -> GET a esta misma URL -> se pierde
    // todo lo que no se había guardado todavía en IndexedDB.
    elForm.addEventListener("submit", function (evento) {
      evento.preventDefault();
    });

    function registroVacio() {
      return {
        clienteId: generarUUID(),
        estadoLocal: "en_progreso",
        pasoGuardado: "vivienda",
        creadaEn: new Date().toISOString(),
        actualizadaEn: new Date().toISOString(),
        direccionEtiqueta: "",
        vivienda: {},
        hogar: null,
        integrantes: [],
        ubicacion: null,
        resultado: "borrador",
        borrador: {},
        cierre: {},
        errorSync: null,
      };
    }

    function el(id) {
      return document.getElementById(id);
    }

    function valor(id) {
      return el(id).value.trim();
    }

    function llenarCatalogo(select, opciones) {
      var vacio = document.createElement("option");
      vacio.value = "";
      vacio.textContent = "Elige una opción";
      select.appendChild(vacio);

      opciones.forEach(function (par) {
        var opcion = document.createElement("option");
        opcion.value = par[0];
        opcion.textContent = par[1];
        select.appendChild(opcion);
      });
    }

    function poblarCatalogos() {
      var zonaSelect = el("of-zona");
      datos.zonas.forEach(function (zona) {
        var opcion = document.createElement("option");
        opcion.value = zona.id;
        opcion.textContent = zona.etiqueta;
        zonaSelect.appendChild(opcion);
      });
      if (datos.zonas.length === 1) {
        zonaSelect.value = datos.zonas[0].id;
      } else {
        var vacio = document.createElement("option");
        vacio.value = "";
        vacio.textContent = "Elige la zona";
        zonaSelect.insertBefore(vacio, zonaSelect.firstChild);
        zonaSelect.value = "";
      }

      Array.prototype.forEach.call(document.querySelectorAll("[data-catalogo]"), function (select) {
        llenarCatalogo(select, datos.catalogos[select.dataset.catalogo] || []);
      });

      // A diferencia de nivel_educacional/situacion_ocupacional (opcionales
      // según edad), pueblo_originario es obligatorio en el servidor
      // (Integrante.pueblo_originario no admite blank=True) pero con un
      // valor por defecto sensato ("No pertenece a ninguno"): se preselecciona
      // para que la mayoría de los casos no exijan un toque extra, y la
      // persona solo lo cambia cuando corresponde.
      el("of-i-pueblo_originario").value = "NINGUNO";
    }

    function mostrarError(idContenedor, mensajes) {
      var contenedor = el(idContenedor);
      if (!mensajes || !mensajes.length) {
        contenedor.classList.add("d-none");
        contenedor.textContent = "";
        return;
      }
      contenedor.classList.remove("d-none");
      contenedor.innerHTML = mensajes.map(function (m) {
        return "<div>" + m + "</div>";
      }).join("");
    }

    function irAPaso(nombrePaso) {
      pasoActual = PASOS.indexOf(nombrePaso);
      Array.prototype.forEach.call(document.querySelectorAll("[data-paso]"), function (seccion) {
        seccion.classList.toggle("d-none", seccion.dataset.paso !== nombrePaso);
      });
      elIndicador.textContent = "Paso " + (pasoActual + 1) + " de " + PASOS.length;
      window.scrollTo(0, 0);
    }

    // -- Paso 1: vivienda -----------------------------------------------

    function validarVivienda() {
      var errores = [];
      var requeridos = [
        ["of-zona", "Elige la zona."],
        ["of-direccion", "Escribe la dirección."],
        ["of-tipo", "Elige el tipo de vivienda."],
        ["of-tenencia", "Elige la tenencia."],
        ["of-materialidad_muros", "Elige la materialidad de los muros."],
        ["of-origen_agua", "Elige el origen del agua."],
        ["of-sistema_sanitario", "Elige el sistema sanitario."],
        ["of-tiene_electricidad", "Indica si la vivienda tiene electricidad."],
      ];
      requeridos.forEach(function (par) {
        if (!valor(par[0])) errores.push(par[1]);
      });
      return errores;
    }

    function leerVivienda() {
      var electricidad = valor("of-tiene_electricidad");
      return {
        zona: valor("of-zona"),
        direccion: valor("of-direccion"),
        referencia: valor("of-referencia"),
        tipo: valor("of-tipo"),
        tenencia: valor("of-tenencia"),
        materialidad_muros: valor("of-materialidad_muros"),
        origen_agua: valor("of-origen_agua"),
        sistema_sanitario: valor("of-sistema_sanitario"),
        tiene_electricidad: electricidad === "" ? null : electricidad === "True",
        observaciones: valor("of-vivienda-observaciones"),
        confirmar_duplicado: false,
      };
    }

    // -- Paso 2: hogar ----------------------------------------------------

    function validarHogar() {
      var errores = [];
      if (valor("of-jefe_hogar_nombre").length < 3) {
        errores.push("Escribe el nombre completo de la jefa o jefe de hogar.");
      }
      if (!valor("of-integrantes_declarados") || Number(valor("of-integrantes_declarados")) < 1) {
        errores.push("Indica cuántas personas viven en el hogar.");
      }
      if (valor("of-jefe_hogar_rut") && !rutValido(valor("of-jefe_hogar_rut"))) {
        errores.push("El RUT de la jefa o jefe de hogar no es válido.");
      }
      var ingreso = valor("of-ingreso_mensual");
      if (ingreso && Number(ingreso) > datos.limites.ingreso_maximo) {
        errores.push("Ese ingreso parece tener un dígito de más. Revísalo.");
      }
      return errores;
    }

    function leerHogar() {
      return {
        jefe_hogar_nombre: valor("of-jefe_hogar_nombre"),
        jefe_hogar_rut: valor("of-jefe_hogar_rut"),
        telefono_contacto: valor("of-telefono_contacto"),
        integrantes_declarados: valor("of-integrantes_declarados"),
        ingreso_mensual: valor("of-ingreso_mensual"),
        observaciones: valor("of-hogar-observaciones"),
      };
    }

    // -- Paso 3: integrantes ----------------------------------------------

    function hayJefeEnLista() {
      return registro.integrantes.some(function (i) {
        return i.parentesco === "JEFE_HOGAR";
      });
    }

    function validarIntegrante() {
      var errores = [];
      if (valor("of-i-nombres").length < 2) errores.push("Escribe los nombres completos.");
      if (valor("of-i-apellidos").length < 2) errores.push("Escribe los apellidos completos.");
      if (!valor("of-i-parentesco")) errores.push("Elige el parentesco.");
      if (!valor("of-i-sexo")) errores.push("Elige el sexo.");
      if (!valor("of-i-pueblo_originario")) errores.push("Elige el pueblo originario (puede ser «No pertenece a ninguno»).");
      var fecha = valor("of-i-fecha_nacimiento");
      if (!fecha) {
        errores.push("Escribe la fecha de nacimiento.");
      } else if (new Date(fecha) > new Date()) {
        errores.push("La fecha de nacimiento no puede ser futura.");
      }
      if (valor("of-i-rut") && !rutValido(valor("of-i-rut"))) {
        errores.push("Ese RUT no es válido.");
      }
      if (valor("of-i-rut")) {
        var rutLimpio = limpiarRut(valor("of-i-rut"));
        if (registro.integrantes.some(function (i) { return limpiarRut(i.rut) === rutLimpio; })) {
          errores.push("Ese RUT ya está en la lista de este hogar.");
        }
      }
      if (valor("of-i-parentesco") === "JEFE_HOGAR" && hayJefeEnLista()) {
        errores.push("Este hogar ya tiene una jefa o jefe registrado.");
      }
      if (fecha) {
        var edad = calcularEdad(fecha);
        if (edad >= datos.limites.edad_escolaridad && !valor("of-i-nivel_educacional")) {
          errores.push("Desde los " + datos.limites.edad_escolaridad + " años hay que registrar el nivel educacional.");
        }
        if (edad >= datos.limites.edad_ocupacion && !valor("of-i-situacion_ocupacional")) {
          errores.push("Desde los " + datos.limites.edad_ocupacion + " años hay que registrar la situación ocupacional.");
        }
      }
      return errores;
    }

    function leerIntegranteFormulario() {
      return {
        parentesco: valor("of-i-parentesco"),
        nombres: valor("of-i-nombres"),
        apellidos: valor("of-i-apellidos"),
        rut: valor("of-i-rut"),
        sexo: valor("of-i-sexo"),
        fecha_nacimiento: valor("of-i-fecha_nacimiento"),
        nivel_educacional: valor("of-i-nivel_educacional"),
        situacion_ocupacional: valor("of-i-situacion_ocupacional"),
        pueblo_originario: valor("of-i-pueblo_originario"),
        tiene_discapacidad: el("of-i-tiene_discapacidad").checked,
        observaciones: valor("of-i-observaciones"),
      };
    }

    function limpiarFormularioIntegrante() {
      ["of-i-nombres", "of-i-apellidos", "of-i-rut", "of-i-fecha_nacimiento", "of-i-observaciones"].forEach(function (id) {
        el(id).value = "";
      });
      ["of-i-parentesco", "of-i-sexo", "of-i-nivel_educacional", "of-i-situacion_ocupacional"].forEach(function (id) {
        el(id).value = "";
      });
      el("of-i-pueblo_originario").value = "NINGUNO"; // ver poblarCatalogos(): tiene valor por defecto, no queda en blanco
      el("of-i-tiene_discapacidad").checked = false;
    }

    function etiquetaCatalogo(catalogo, valorInterno) {
      var par = (datos.catalogos[catalogo] || []).find(function (p) { return p[0] === valorInterno; });
      return par ? par[1] : valorInterno;
    }

    function pintarListaIntegrantes() {
      var contenedor = el("of-integrantes-lista");
      if (!registro.integrantes.length) {
        contenedor.innerHTML = '<p class="text-secondary small mb-0">Todavía no agregas a nadie.</p>';
      } else {
        contenedor.innerHTML = registro.integrantes.map(function (i, indice) {
          return (
            '<div class="d-flex justify-content-between align-items-center border rounded p-2 mb-2">' +
            "<div><strong>" + i.nombres + " " + i.apellidos + "</strong>" +
            '<span class="text-secondary small"> · ' + etiquetaCatalogo("parentesco", i.parentesco) + "</span></div>" +
            '<button type="button" class="btn btn-outline-danger btn-sm" data-quitar-integrante="' + indice + '">Quitar</button>' +
            "</div>"
          );
        }).join("");
      }

      var declarados = Number(registro.hogar ? registro.hogar.integrantes_declarados : 0) || 0;
      var texto = "Van " + registro.integrantes.length;
      if (declarados) texto += " de " + declarados + " declarados";
      el("of-integrantes-resumen").textContent = texto + ".";
    }

    // -- Paso 4: ubicación --------------------------------------------------

    function validarUbicacion() {
      var lat = valor("of-latitud");
      var lon = valor("of-longitud");
      var errores = [];
      if ((lat && !lon) || (!lat && lon)) {
        errores.push("La latitud y la longitud van juntas, o ninguna.");
        return errores;
      }
      if (!lat) return errores; // la ubicación es opcional

      var limites = datos.limites;
      if (Number(lat) < Number(limites.latitud_minima) || Number(lat) > Number(limites.latitud_maxima)) {
        errores.push("La latitud cae fuera de Chile. En Chile siempre es negativa.");
      }
      if (Number(lon) < Number(limites.longitud_minima) || Number(lon) > Number(limites.longitud_maxima)) {
        errores.push("La longitud cae fuera de Chile. En Chile siempre es negativa.");
      }
      return errores;
    }

    function leerUbicacion() {
      var lat = valor("of-latitud");
      if (!lat) return null;
      return {
        latitud: lat,
        longitud: valor("of-longitud"),
        precision_metros: valor("of-precision_metros"),
        confirmar_lejania: false,
        capturada_por_gps: el("of-latitud").dataset.capturadaPorGps === "1",
      };
    }

    // -- Paso 5: resultado ----------------------------------------------

    function resultadoElegido() {
      var marcado = elForm.querySelector('input[name="of-resultado"]:checked');
      return marcado ? marcado.value : "borrador";
    }

    function actualizarBloqueResultado() {
      var resultado = resultadoElegido();
      el("of-bloque-borrador").classList.toggle("d-none", resultado !== "borrador");
      el("of-bloque-completar").classList.toggle("d-none", resultado !== "completar");
      el("of-bloque-cerrar").classList.toggle("d-none", resultado !== "cerrar_sin_datos");

      if (resultado === "completar") {
        var faltan = [];
        if (!registro.hogar) faltan.push("registrar el hogar");
        if (!hayJefeEnLista()) faltan.push("registrar a la jefa o jefe de hogar");
        var declarados = registro.hogar ? Number(registro.hogar.integrantes_declarados) || 0 : 0;
        if (registro.integrantes.length < declarados) {
          faltan.push("registrar a las " + (declarados - registro.integrantes.length) + " persona(s) que faltan");
        }
        el("of-completar-pendientes").textContent = faltan.length
          ? "El servidor probablemente la va a rechazar: falta " + faltan.join(", ") + "."
          : "Con lo capturado hasta ahora, se puede dar por terminada.";
      }
    }

    function validarResultado() {
      var resultado = resultadoElegido();
      var errores = [];
      if (resultado === "cerrar_sin_datos" && valor("of-motivo_cierre").length < datos.limites.motivo_cierre_minimo) {
        errores.push("Explica el motivo con una frase de al menos " + datos.limites.motivo_cierre_minimo + " caracteres.");
      }
      return errores;
    }

    // -- Guardado en IndexedDB (en cada paso, no solo al final) --------

    function guardarProgreso(pasoDestino) {
      registro.actualizadaEn = new Date().toISOString();
      registro.direccionEtiqueta = registro.vivienda.direccion || "(sin dirección todavía)";
      if (pasoDestino) registro.pasoGuardado = pasoDestino;
      return guardarRegistro(registro);
    }

    // -- Recuperar un borrador si se cerró la pestaña a mitad de camino ---
    //
    // guardarProgreso() escribe en IndexedDB en cada paso, así que los datos
    // ya sobreviven a cerrar la pestaña. Lo que falta para que eso sirva de
    // algo es ESTO: al volver a abrir el asistente, ofrecer continuar donde
    // se quedó en vez de arrancar con una encuesta nueva y dejar la anterior
    // huérfana en el almacén.

    function llenarSelect(id, valorGuardado) {
      if (valorGuardado !== undefined && valorGuardado !== null) el(id).value = String(valorGuardado);
    }

    function restaurarCampos() {
      var v = registro.vivienda || {};
      llenarSelect("of-zona", v.zona);
      el("of-direccion").value = v.direccion || "";
      el("of-referencia").value = v.referencia || "";
      llenarSelect("of-tipo", v.tipo);
      llenarSelect("of-tenencia", v.tenencia);
      llenarSelect("of-materialidad_muros", v.materialidad_muros);
      llenarSelect("of-origen_agua", v.origen_agua);
      llenarSelect("of-sistema_sanitario", v.sistema_sanitario);
      el("of-tiene_electricidad").value = v.tiene_electricidad === null || v.tiene_electricidad === undefined
        ? ""
        : String(v.tiene_electricidad);
      el("of-vivienda-observaciones").value = v.observaciones || "";

      var h = registro.hogar || {};
      el("of-jefe_hogar_nombre").value = h.jefe_hogar_nombre || "";
      el("of-jefe_hogar_rut").value = h.jefe_hogar_rut || "";
      el("of-telefono_contacto").value = h.telefono_contacto || "";
      el("of-integrantes_declarados").value = h.integrantes_declarados || "";
      el("of-ingreso_mensual").value = h.ingreso_mensual || "";
      el("of-hogar-observaciones").value = h.observaciones || "";

      var u = registro.ubicacion || {};
      el("of-latitud").value = u.latitud || "";
      el("of-longitud").value = u.longitud || "";
      el("of-precision_metros").value = u.precision_metros || "";

      pintarListaIntegrantes();
    }

    function ofrecerRecuperarBorrador() {
      return listarRegistros().then(function (registros) {
        var enProgreso = registros.filter(function (r) { return r.estadoLocal === "en_progreso"; });
        if (!enProgreso.length) return;

        // Solo puede haber uno realista a la vez (se censa una casa por
        // vez); si hubiera más de uno por alguna razón, se ofrece el más
        // reciente y los otros quedan disponibles para una próxima vez.
        var candidato = enProgreso.sort(function (a, b) {
          return b.actualizadaEn.localeCompare(a.actualizadaEn);
        })[0];

        elMensaje.classList.remove("d-none");
        elMensaje.className = "alert alert-info";
        elMensaje.innerHTML =
          "<strong>Recuperamos una encuesta a medias" +
          (candidato.direccionEtiqueta ? " de " + candidato.direccionEtiqueta : "") +
          ".</strong> ¿Sigues completándola?" +
          '<div class="mt-2 d-flex gap-2">' +
          '<button type="button" class="btn btn-sm btn-opso" id="of-recuperar-continuar">Continuar</button>' +
          '<button type="button" class="btn btn-sm btn-outline-secondary" id="of-recuperar-descartar">Empezar de nuevo</button>' +
          "</div>";

        el("of-recuperar-continuar").addEventListener("click", function () {
          registro = candidato;
          restaurarCampos();
          actualizarBloqueResultado();
          irAPaso(registro.pasoGuardado || "vivienda");
          elMensaje.classList.add("d-none");
        });

        el("of-recuperar-descartar").addEventListener("click", function () {
          eliminarRegistro(candidato.clienteId).then(function () {
            elMensaje.classList.add("d-none");
          });
        });
      });
    }

    // -- Navegación -------------------------------------------------------

    elForm.addEventListener("click", function (evento) {
      var botonSiguiente = evento.target.closest("[data-siguiente]");
      var botonVolver = evento.target.closest("[data-volver]");

      if (botonVolver) {
        irAPaso(botonVolver.dataset.volver);
        return;
      }

      if (!botonSiguiente) return;

      var paso = botonSiguiente.dataset.siguiente;
      var errores;

      if (paso === "vivienda") {
        errores = validarVivienda();
        mostrarError("of-error-vivienda", errores);
        if (errores.length) return;
        registro.vivienda = leerVivienda();
        guardarProgreso("hogar");
        irAPaso("hogar");
      } else if (paso === "hogar") {
        errores = validarHogar();
        mostrarError("of-error-hogar", errores);
        if (errores.length) return;
        registro.hogar = leerHogar();
        guardarProgreso("integrantes");
        pintarListaIntegrantes();
        irAPaso("integrantes");
      } else if (paso === "integrantes") {
        registro.direccionEtiqueta = registro.vivienda.direccion;
        guardarProgreso("ubicacion");
        irAPaso("ubicacion");
      } else if (paso === "ubicacion") {
        errores = validarUbicacion();
        mostrarError("of-error-ubicacion", errores);
        if (errores.length) return;
        registro.ubicacion = leerUbicacion();
        guardarProgreso("resultado");
        actualizarBloqueResultado();
        irAPaso("resultado");
      }
    });

    el("of-agregar-integrante").addEventListener("click", function () {
      var errores = validarIntegrante();
      mostrarError("of-error-integrante", errores);
      if (errores.length) return;

      registro.integrantes.push(leerIntegranteFormulario());
      guardarProgreso();
      pintarListaIntegrantes();
      limpiarFormularioIntegrante();
      mostrarError("of-error-integrante", []);
    });

    el("of-integrantes-lista").addEventListener("click", function (evento) {
      var boton = evento.target.closest("[data-quitar-integrante]");
      if (!boton) return;
      registro.integrantes.splice(Number(boton.dataset.quitarIntegrante), 1);
      guardarProgreso();
      pintarListaIntegrantes();
    });

    Array.prototype.forEach.call(elForm.querySelectorAll('input[name="of-resultado"]'), function (radio) {
      radio.addEventListener("change", actualizarBloqueResultado);
    });

    el("of-guardar-en-el-telefono").addEventListener("click", function () {
      var errores = validarResultado();
      mostrarError("of-error-resultado", errores);
      if (errores.length) return;

      registro.resultado = resultadoElegido();
      if (registro.resultado === "borrador") {
        registro.borrador = {
          nota_avance: valor("of-nota_avance"),
          proxima_visita: valor("of-proxima_visita"),
        };
      } else if (registro.resultado === "cerrar_sin_datos") {
        var marcado = elForm.querySelector('input[name="of-cierre-estado"]:checked');
        registro.cierre = {
          estado: marcado ? marcado.value : "NO_UBICADA",
          motivo_cierre: valor("of-motivo_cierre"),
        };
      }
      registro.estadoLocal = "pendiente";

      guardarProgreso().then(function () {
        elForm.classList.add("d-none");
        elConfirmacion.classList.remove("d-none");
      });
    });

    el("of-censar-otra").addEventListener("click", function () {
      window.location.reload();
    });

    // -- Ubicación por GPS (mismo patrón que ubicacion_form.html, HU-11) --

    (function () {
      var boton = el("of-capturar-gps");
      var aviso = el("of-gps-estado");

      if (!("geolocation" in navigator)) {
        boton.disabled = true;
        return;
      }

      boton.addEventListener("click", function () {
        boton.disabled = true;
        aviso.className = "small mt-3 text-secondary";
        aviso.textContent = "Buscando la señal… puede tardar unos segundos.";

        navigator.geolocation.getCurrentPosition(
          function (posicion) {
            var precision = Math.round(posicion.coords.accuracy);
            el("of-latitud").value = posicion.coords.latitude.toFixed(6);
            el("of-longitud").value = posicion.coords.longitude.toFixed(6);
            el("of-precision_metros").value = precision;
            el("of-latitud").dataset.capturadaPorGps = "1";
            boton.disabled = false;

            if (precision > datos.limites.precision_aceptable) {
              aviso.className = "small mt-3 text-warning-emphasis fw-semibold";
              aviso.textContent = "Punto capturado, pero con " + precision + " m de error. Sal a la calle y vuelve a intentarlo.";
            } else {
              aviso.className = "small mt-3 text-success fw-semibold";
              aviso.textContent = "Punto capturado con " + precision + " m de precisión.";
            }
          },
          function (error) {
            boton.disabled = false;
            var mensajes = {
              1: "No diste permiso para usar la ubicación. Puedes escribir las coordenadas a mano.",
              2: "El aparato no consigue señal aquí. Prueba al aire libre, o sigue sin ubicación.",
              3: "La búsqueda tardó demasiado. Vuelve a intentarlo al aire libre.",
            };
            aviso.className = "small mt-3 text-danger";
            aviso.textContent = mensajes[error.code] || "No se pudo obtener la ubicación.";
          },
          { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
        );
      });

      el("of-latitud").addEventListener("input", function () {
        delete el("of-latitud").dataset.capturadaPorGps;
      });
    })();

    // -- Service worker: instalarlo para que el asistente cargue offline --

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(function () {
        // Sin service worker el asistente sigue funcionando mientras la
        // pestaña siga abierta; solo se pierde la carga en frío con cero
        // señal. No hay nada más que hacer desde aquí si el registro falla.
      });
    }

    poblarCatalogos();
    irAPaso("vivienda");
    ofrecerRecuperarBorrador();
  }

  // ------------------------------------------------------------------
  // LA COLA — templates/fichas/mis_encuestas.html
  // ------------------------------------------------------------------

  function iniciarCola(opciones) {
    var contenedor = document.getElementById("opso-cola-offline");
    var lista = document.getElementById("opso-cola-offline-lista");
    var botonSincronizar = document.getElementById("opso-cola-offline-sincronizar");

    function pintar(registros) {
      var pendientes = registros.filter(function (r) {
        return r.estadoLocal === "pendiente";
      });

      if (!pendientes.length) {
        contenedor.classList.add("d-none");
        return;
      }
      contenedor.classList.remove("d-none");

      lista.innerHTML = pendientes.map(function (r) {
        var estado = r.errorSync
          ? '<span class="badge text-bg-danger">Rechazada al sincronizar</span>'
          : '<span class="badge text-bg-secondary">Por sincronizar</span>';

        var detalleError = "";
        if (r.errorSync) {
          detalleError = '<div class="small text-danger mt-1">' + r.errorSync.mensaje + "</div>";

          var confirmable = r.errorSync.campoConfirmar;
          if (confirmable) {
            detalleError +=
              '<div class="form-check small mt-1">' +
              '<input class="form-check-input" type="checkbox" id="conf-' + r.clienteId + '">' +
              '<label class="form-check-label" for="conf-' + r.clienteId + '">' +
              "Confirmar de todas formas y reintentar" +
              "</label></div>";
          }
        }

        return (
          '<div class="d-flex justify-content-between align-items-start border-bottom py-2" data-item="' + r.clienteId + '">' +
          "<div>" +
          "<div>" + (r.direccionEtiqueta || "(sin dirección)") + " " + estado + "</div>" +
          detalleError +
          "</div>" +
          '<div class="d-flex gap-1 flex-shrink-0">' +
          '<button type="button" class="btn btn-outline-danger btn-sm" data-quitar-cola="' + r.clienteId + '">Eliminar</button>' +
          "</div>" +
          "</div>"
        );
      }).join("");
    }

    function refrescar() {
      return listarRegistros().then(pintar);
    }

    lista.addEventListener("click", function (evento) {
      var quitar = evento.target.closest("[data-quitar-cola]");
      if (quitar) {
        eliminarRegistro(quitar.dataset.quitarCola).then(refrescar);
      }
    });

    function sincronizarUna(registro) {
      var payload = {
        cliente_id: registro.clienteId,
        vivienda: registro.vivienda,
        hogar: registro.hogar,
        integrantes: registro.integrantes,
        ubicacion: registro.ubicacion,
        resultado: registro.resultado,
        borrador: registro.borrador,
        cierre: registro.cierre,
      };

      return fetch(opciones.urlSincronizar, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": leerCookie("csrftoken"),
        },
        body: JSON.stringify(payload),
      })
        .then(function (respuesta) {
          return respuesta.json().then(function (cuerpo) {
            return { ok: respuesta.ok, cuerpo: cuerpo };
          });
        })
        .then(function (resultado) {
          if (resultado.ok && resultado.cuerpo.exito) {
            return eliminarRegistro(registro.clienteId).then(function () {
              return resultado.cuerpo.advertencia
                ? {
                    direccion: registro.direccionEtiqueta,
                    advertencia: resultado.cuerpo.advertencia,
                    encuestaId: resultado.cuerpo.encuesta_id,
                  }
                : null;
            });
          }
          registro.errorSync = interpretarError(resultado.cuerpo);
          return guardarRegistro(registro).then(function () {
            return null;
          });
        })
        .catch(function () {
          registro.errorSync = { mensaje: "No se pudo enviar: revisa tu conexión e inténtalo de nuevo.", campoConfirmar: null };
          return guardarRegistro(registro).then(function () {
            return null;
          });
        });
    }

    // Recorre cualquiera de las formas que puede tener `errores` —dict de
    // campo -> [{message,...}] de un Form, la lista de {indice, errores} de
    // los integrantes, o un texto plano como el de "completar"— y devuelve
    // el primer mensaje legible que encuentra.
    function primerMensaje(nodo) {
      if (typeof nodo === "string") return nodo;

      if (Array.isArray(nodo)) {
        for (var i = 0; i < nodo.length; i++) {
          var resultado = primerMensaje(nodo[i]);
          if (resultado) return resultado;
        }
        return null;
      }

      if (nodo && typeof nodo === "object") {
        if (typeof nodo.message === "string") return nodo.message;
        if (nodo.errores) return primerMensaje(nodo.errores);
        for (var clave in nodo) {
          var resultado2 = primerMensaje(nodo[clave]);
          if (resultado2) return resultado2;
        }
      }

      return null;
    }

    // Los únicos dos campos del proyecto donde "confirmar y reintentar"
    // basta para que la sincronización pase: dirección duplicada
    // (ViviendaForm) y punto lejos del resto de la zona (UbicacionForm). Se
    // enumeran a mano y no se detectan por prefijo en cualquier bloque,
    // porque son los únicos dos casos donde marcar la casilla y reenviar
    // EXACTAMENTE los mismos datos es una corrección válida; cualquier otro
    // error necesita datos distintos, no una confirmación.
    function bloqueConConfirmar(bloques) {
      var candidatos = [
        ["vivienda", "confirmar_duplicado"],
        ["ubicacion", "confirmar_lejania"],
      ];
      for (var i = 0; i < candidatos.length; i++) {
        var bloque = candidatos[i][0];
        var campo = candidatos[i][1];
        if (bloques[bloque] && bloques[bloque][campo]) {
          return { bloque: bloque, campo: campo };
        }
      }
      return null;
    }

    function interpretarError(cuerpo) {
      if (!cuerpo || !cuerpo.errores) {
        return { mensaje: (cuerpo && cuerpo.error) || "El servidor rechazó esta encuesta.", campoConfirmar: null };
      }

      return {
        mensaje: primerMensaje(cuerpo.errores) || "El servidor rechazó esta encuesta.",
        campoConfirmar: bloqueConConfirmar(cuerpo.errores),
      };
    }

    function leerCookie(nombre) {
      var partes = document.cookie.split("; ");
      for (var i = 0; i < partes.length; i++) {
        var par = partes[i].split("=");
        if (par[0] === nombre) return decodeURIComponent(par[1]);
      }
      return "";
    }

    function pintarAvisos(avisos) {
      var contenedor = document.getElementById("opso-cola-offline-avisos");
      if (!avisos.length) {
        contenedor.innerHTML = "";
        return;
      }

      contenedor.innerHTML = avisos.map(function (aviso) {
        var url = aviso.encuestaId
          ? opciones.patronUrlEncuesta.replace(/0(\/?)$/, aviso.encuestaId + "$1")
          : null;
        return (
          '<div class="alert alert-warning small mb-2" role="alert">' +
          "<strong>" + (aviso.direccion || "Una encuesta") + ":</strong> " + aviso.advertencia +
          (url ? ' <a href="' + url + '">Ir a la encuesta</a>' : "") +
          "</div>"
        );
      }).join("");
    }

    botonSincronizar.addEventListener("click", function () {
      botonSincronizar.disabled = true;
      botonSincronizar.textContent = "Sincronizando…";

      var avisos = [];

      listarRegistros()
        .then(function (registros) {
          var pendientes = registros.filter(function (r) { return r.estadoLocal === "pendiente"; });
          // Una por una, en orden: sobre una señal débil es más predecible
          // que mandarlas todas a la vez, y así cada una se confirma antes
          // de intentar la siguiente (mismo criterio que "guardar y agregar
          // otra" en la HU-09).
          return pendientes.reduce(function (cadena, registro) {
            // Antes de reintentar, aplica cualquier casilla de "confirmar"
            // que el censista haya marcado en la pantalla.
            var casilla = document.getElementById("conf-" + registro.clienteId);
            if (casilla && casilla.checked && registro.errorSync && registro.errorSync.campoConfirmar) {
              var destino = registro.errorSync.campoConfirmar;
              if (registro[destino.bloque]) {
                registro[destino.bloque][destino.campo] = true;
              }
            }
            return cadena.then(function () {
              return sincronizarUna(registro).then(function (aviso) {
                if (aviso) avisos.push(aviso);
              });
            });
          }, Promise.resolve());
        })
        .then(refrescar)
        .then(function () {
          pintarAvisos(avisos);
          botonSincronizar.disabled = false;
          botonSincronizar.textContent = "Sincronizar";
        });
    });

    refrescar();
  }

  return {
    iniciarAsistente: iniciarAsistente,
    iniciarCola: iniciarCola,
    _rutValido: rutValido,
    _limpiarRut: limpiarRut,
  };
})();
