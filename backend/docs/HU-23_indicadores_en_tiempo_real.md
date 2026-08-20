# HU-23 · Visualizar indicadores en tiempo real

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor o administrador, quiero visualizar indicadores en tiempo real para monitorear el avance del operativo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · JavaScript nativo (sin librerías)
**Estado:** implementada y **verificada en un navegador real** (Chromium vía Playwright, instalado temporalmente)

> Se conversó con el usuario si esto chocaba con la HU-21/HU-22 (autoguardado offline),
> porque las tres presionan contra el mismo principio de `CLAUDE.md`: *"Sin API REST ni
> JavaScript de aplicación"*. No chocan: resuelven problemas distintos, en pantallas
> distintas, con mecanismos independientes. Esta historia es, además, la más simple de
> las tres: los paneles ya leían la base de datos al vuelo desde que existen; lo único
> que faltaba era que se refrescaran solos.

---

## Índice

1. [Qué existía y qué faltaba](#1-qué-existía-y-qué-faltaba)
2. [La decisión: recarga periódica, no WebSockets ni AJAX](#2-la-decisión)
3. [Por qué se pausa con la pestaña oculta](#3-por-qué-se-pausa)
4. [Alcance: solo los dos paneles de solo lectura](#4-alcance)
5. [Archivos creados y modificados](#5-archivos)
6. [Verificación en un navegador real](#6-verificación)
7. [Explicación para la defensa](#7-explicación-para-la-defensa)
8. [Posibles preguntas del profesor](#8-posibles-preguntas-del-profesor)

---

## 1. Qué existía y qué faltaba

Antes de escribir código se revisó `dashboards/views.py`, y no había ningún caché de
por medio: `DashboardSupervisorView` y `DashboardAdministradorView` consultan
PostgreSQL en cada petición, sin `@cache_page` ni nada parecido. El único backend de
caché configurado (`LocMemCache`) se usa para el control de fuerza bruta de la HU-01,
no para las vistas.

Es decir: **los datos ya eran "en tiempo real" en el sentido que importa** —nunca
mentían, nunca mostraban un número viejo—. Lo único que exigía intervención humana era
el momento de pedirlos: un supervisor tenía que apretar F5 para ver un número que
cambió hace un minuto. Esta historia resuelve exactamente eso, y nada más.

---

## 2. La decisión

Se evaluaron tres formas de lograr que un panel se actualice solo:

| Opción | Qué exige | Se descartó porque |
|---|---|---|
| WebSockets / Server-Sent Events | Una conexión persistente, `django-channels`, un servidor ASGI corriendo de verdad (`config/asgi.py` hoy es un `get_asgi_application()` sin usar) | Es la primera infraestructura de servidor en tiempo real del proyecto, para un problema que no la necesita: nadie pidió que el número cambiara en el instante exacto, solo que no hubiera que recargar a mano. |
| Sondeo por AJAX a un endpoint JSON | Una vista nueva que devuelva JSON en vez de HTML, y JavaScript que la consulte y reescriba el DOM | Es la primera API del proyecto (`CLAUDE.md`: "sin API REST"), para actualizar una pantalla que de todas formas se puede recargar entera sin que nadie note la diferencia. |
| **Recarga periódica de la página completa** (elegida) | Un `location.reload()` cada cierto tiempo | Ninguna infraestructura nueva. La vista ya arma el HTML completo con datos frescos; solo hacía falta pedirlo de nuevo cada tanto. |

Con conexión intermitente descartada como el problema real en la HU-21, y sin ningún
indicio de que el operativo necesite ver un cambio en menos de medio minuto, la
recarga periódica es la respuesta más simple que cumple lo que pide el enunciado —y la
única de las tres que no cruza ninguna línea de arquitectura nueva.

---

## 3. Por qué se pausa

```js
function tick() {
  if (document.hidden) {
    return; // pestaña en segundo plano: no cuenta, no recarga
  }
  ...
}
```

Recargar una pestaña que nadie está mirando no cumple ningún propósito: solo gasta
batería y ancho de banda del servidor sin que nadie vea el resultado. El script usa la
Page Visibility API (`document.hidden`, estándar en todos los navegadores modernos)
para detener la cuenta regresiva mientras la pestaña está oculta, y la reinicia entera
—no la retoma desde donde iba— al volver a estar visible. Retomarla habría significado
recargar de golpe con un número de segundos acumulados mientras nadie miraba, lo que
en la práctica sería una recarga sorpresa justo cuando el supervisor vuelve a la
pestaña.

---

## 4. Alcance

Solo dos pantallas, las dos de solo lectura:

| Pantalla | ¿Auto-actualización? | Por qué |
|---|---|---|
| Panel del Supervisor | Sí | Es la pantalla que la historia describe: "monitorear el avance del operativo". Sin formularios, sin filtros: recargar no puede interrumpir nada. |
| Panel del Administrador | Sí | Mismo criterio. Tiene tarjetas de acceso directo (crear usuario, exportar, etc.), pero ninguna es un formulario abierto en la propia pantalla. |
| Bandeja de revisión (HU-13/HU-18) | **No** | Tiene un formulario de filtros y una tabla paginada. Una recarga automática en medio de completar un filtro, o justo cuando el supervisor está leyendo la fila número 18 de 25, sería una interrupción real, no una comodidad. |
| Cualquier pantalla de la encuesta | **No** | Ya tienen su propio mecanismo, y es el opuesto: la HU-21 protege contra recargas justamente porque ahí sí hay algo que perder. |

---

## 5. Archivos

### Creados

```
backend/static/js/actualizacion_automatica.js       el módulo de auto-actualización
backend/docs/HU-23_indicadores_en_tiempo_real.md     este documento
```

### Modificados

```
backend/templates/dashboards/supervisor.html
    + {% load static %}
    + <span id="opso-actualizacion-indicador"> en la cabecera
    + {% block js_extra %} con OPSOActualizacionAutomatica.iniciar()

backend/templates/dashboards/administrador.html
    + static agregado a {% load static permisos %}
    + <span id="opso-actualizacion-indicador"> junto al badge «Acceso total»
    + {% block js_extra %} con OPSOActualizacionAutomatica.iniciar()

backend/README.md
    ~ fila de HU-23: «✅ Implementada», con enlace
```

Ninguna migración, ninguna vista nueva, ningún modelo tocado: es JavaScript de cliente
puro sobre plantillas que ya existían, igual que la HU-21.

---

## 6. Verificación

Igual que en la HU-21, se instaló Playwright de forma temporal (sin tocar el
repositorio) y se verificó contra el `runserver` real con PostgreSQL, con sesiones
reales de supervisor y de administrador. Esta vez las 14 verificaciones pasaron sin
encontrar ningún error:

| # | Verificación | Panel Supervisor | Panel Administrador |
|---|---|---|---|
| 1 | Hay exactamente un indicador en la página (sin duplicados) | ✅ | ✅ |
| 2 | El texto inicial es "Se actualiza en 30 s" | ✅ | ✅ |
| 3 | Tras ~2 segundos reales, la cuenta bajó a 27-28 s | ✅ | ✅ |
| 4 | Con la pestaña marcada como oculta (`document.hidden`), la cuenta NO avanza durante 3 s | ✅ | ✅ |
| 5 | Al volver a estar visible, la cuenta se reinicia a 30 s (no retoma un número acumulado) | ✅ | ✅ |
| 6 | Con un intervalo corto de prueba, la página se recarga sola (navegación real detectada) | ✅ | ✅ |

No se detectó ningún error de consola ni de página durante las pruebas (a diferencia
de la HU-21, donde la misma clase de verificación sí encontró un error real).

---

## 7. Explicación para la defensa

**En una frase:** los paneles ya mostraban datos frescos en cada carga; esta historia
solo automatiza el momento de pedirlos de nuevo, con la opción más simple de las tres
que se evaluaron y sin agregar ninguna infraestructura de servidor nueva.

**Lo que conviene poder defender:**

1. **Se investigó antes de programar y no había nada que optimizar en el servidor.**
   `dashboards/views.py` no tenía caché: el "tiempo real" ya era cierto del lado de los
   datos, y solo faltaba el lado de "cuándo se piden".
2. **Se evaluaron tres mecanismos y se justificó por qué no los otros dos.**
   WebSockets y AJAX+JSON habrían sido la primera infraestructura de tiempo real y la
   primera API del proyecto respectivamente, para un problema que la recarga periódica
   resuelve sin ninguna de las dos.
3. **Se pausa cuando nadie mira.** No es un detalle cosmético: evita peticiones sin
   sentido y evita el efecto sorpresa de una recarga acumulada al volver a la pestaña.
4. **Acotado a dos pantallas de solo lectura, a propósito.** La bandeja de revisión y
   las pantallas de la encuesta quedan fuera porque en esas sí hay algo que una
   recarga automática podría interrumpir.
5. **Se verificó en un navegador real, no solo se dio por hecho.** Mismo nivel de
   rigor que la HU-21, con Playwright instalado y desinstalado para la ocasión.

---

## 8. Posibles preguntas del profesor

**¿Por qué no WebSockets, si "tiempo real" es literalmente para lo que existen?**
Porque el enunciado pide poder monitorear el avance sin recargar a mano, no un cambio
que se vea en el instante exacto en que ocurre. WebSockets exigiría levantar
`django-channels` y un servidor ASGI en producción —la primera infraestructura de
tiempo real del proyecto— para una diferencia que nadie notaría frente a una recarga
cada 30 segundos.

**¿Por qué 30 segundos y no otro número?**
Es un valor conservador: bastante frecuente para que el panel se sienta actualizado,
bastante espaciado para no generar una petición al servidor por segundo entre todos
los supervisores y administradores conectados. No hay un requisito de negocio que
exija un número exacto, así que se eligió el que equilibra ambas cosas sin
complicarse con un valor configurable que nadie pidió.

**¿Por qué no se aplicó también a la bandeja de revisión, que también "monitorea el
avance"?**
Porque ahí sí hay algo que perder: un formulario de filtros a medio completar, o una
tabla paginada que el supervisor está leyendo fila por fila. Una recarga automática
ahí sería una interrupción, no una comodidad — es la distinción que ya se explicó al
acotar el alcance de la HU-21 en la dirección opuesta.

**¿Esto choca con la HU-21 y la HU-22?**
No, porque resuelven problemas distintos en pantallas distintas. La HU-21 protege
datos que alguien está escribiendo en las pantallas de la encuesta; esta historia
refresca paneles de solo lectura que no tienen nada que escribir. Los dos mecanismos
conviven en el mismo proyecto sin tocarse: comparten el mismo patrón de diseño (un
archivo en `static/js/`, cargado solo donde hace falta, con progressive enhancement),
pero no comparten código ni pantallas.

**¿Se agregó algún campo o migración nueva?**
No. Es JavaScript de cliente puro sobre paneles que ya mostraban los datos correctos;
solo cambia cuándo se vuelven a pedir.
