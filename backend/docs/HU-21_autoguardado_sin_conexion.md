# HU-21 · Almacenar temporalmente la información sin conexión

> **⚠️ Superada por la [HU-24](HU-24_captura_de_encuestas_sin_conexion.md).** En uso
> real se reportó que este mecanismo no servía: protegía el contenido de UN
> formulario mientras la pestaña seguía abierta esperando conexión, pero no permitía
> avanzar de una pantalla a la siguiente sin servidor —y por lo tanto no permitía
> capturar una encuesta completa sin conexión, que era el problema real—. La HU-24 lo
> reemplaza con un asistente que hace vivienda, hogar, integrantes y ubicación
> enteros en el navegador (IndexedDB, no `localStorage`) y sincroniza al final. Este
> documento se conserva tal cual quedó entonces: explica un diseño real, verificado y
> con su propio mérito para el problema que sí resolvía (proteger ediciones sobre
> encuestas que ya existen en el servidor, donde `autoguardado.js` SIGUE en uso), y
> deja constancia de por qué no alcanzaba para el caso que la HU-24 sí cubre.

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como censista, quiero que el sistema almacene temporalmente la información para asegurar la continuidad del trabajo sin conexión.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · JavaScript nativo (sin librerías)
**Estado:** implementada y **verificada manualmente** — es la primera funcionalidad del proyecto sin pruebas automáticas (ver §7)

> Esta historia y la HU-20 tienen algo en común y algo muy distinto: las dos son la
> primera vez que su capacidad no existía de ninguna forma en el proyecto. Pero
> mientras la HU-20 fue "una función más, con datos que ya existían", esta es la
> primera vez que el código de OPSO cruza la línea que `CLAUDE.md` traza como
> arquitectura firme: *"Sin API REST ni JavaScript de aplicación: son vistas
> renderizadas en servidor con plantillas."* Por eso el diseño se conversó ANTES de
> escribir una sola línea (ver §1) y quedó acotado a propósito.

---

## Índice

1. [La conversación previa: qué problema es este, en realidad](#1-la-conversación-previa)
2. [Por qué no es una PWA](#2-por-qué-no-es-una-pwa)
3. [Alcance: en qué pantallas, y en cuáles no](#3-alcance)
4. [Cómo funciona `autoguardado.js`](#4-cómo-funciona)
5. [Las claves de `localStorage`, y el caso ambiguo de "vivienda nueva"](#5-las-claves)
6. [Por qué se limpia al enviar, y no al confirmar que llegó](#6-por-qué-se-limpia-al-enviar)
7. [Sin pruebas automáticas: qué se hizo en su lugar](#7-sin-pruebas-automáticas)
8. [Archivos creados y modificados](#8-archivos)
9. [Verificación manual](#9-verificación-manual)
10. [Explicación para la defensa](#10-explicación-para-la-defensa)
11. [Posibles preguntas del profesor](#11-posibles-preguntas-del-profesor)

---

## 1. La conversación previa

El enunciado —"almacenar temporalmente sin conexión"— admite dos lecturas de tamaño
completamente distinto, y la diferencia importaba antes de tocar código:

- **Conexión intermitente**: se corta a ratos durante la visita (mala señal en el
  sector), pero el navegador sigue pudiendo cargar páginas del servidor en algún
  momento cercano.
- **Sin conexión todo el día**: el censista sale sin señal desde el principio y
  sincroniza recién al volver a un lugar con wifi o datos. El navegador no puede
  cargar NADA del servidor mientras tanto.

Se confirmó con el usuario que el escenario real es el primero. Es una diferencia de
arquitectura, no de detalle: el segundo escenario exige poder **abrir la página sin
red** (service worker + caché), lo que no se puede resolver con JavaScript de una
pantalla — hace falta interceptar la navegación misma. El primero, en cambio, es un
problema que el propio navegador ya resuelve la mayor parte del tiempo (el POST
llega), y lo único que hay que proteger es la ventana en que el censista **ya escribió
algo pero todavía no lo envió**.

También se acotó qué pantallas necesitan esto: **solo las de la encuesta** (vivienda,
hogar, integrantes, ubicación y la nota de borrador), no el resto del sistema —
bandeja de revisión, paneles, gestión de usuarios—. Un supervisor revisando fichas
desde una oficina no tiene el problema que esta historia resuelve.

---

## 2. Por qué no es una PWA

Vale la pena decirlo explícitamente porque es la alternativa que cualquiera pensaría
primero al leer "trabajar sin conexión": una PWA (service worker, caché de la
aplicación, cola de sincronización en `IndexedDB`, y casi seguro una API en JSON
porque un service worker no puede interceptar un formulario HTML normal de la misma
manera). Es un cambio de arquitectura real —el primero de todo el proyecto que tocaría
"sin API REST ni JavaScript de aplicación" en serio— y no es lo que el escenario
confirmado necesita.

Lo que se construyó en su lugar es **progresivo**: la pantalla sigue siendo la misma
vista renderizada en servidor de siempre. El JavaScript no la reemplaza ni intercepta
nada; solo la vigila mientras está abierta y guarda una copia de lo que se escribe.
Sin JavaScript, o con `localStorage` deshabilitado, el formulario funciona exactamente
igual que antes de esta historia — ni una línea de HTML depende de que el script se
haya ejecutado. Es el mismo principio de *progressive enhancement* que ya usa
`ubicacion_form.html` (HU-11) para la captura de GPS.

---

## 3. Alcance

| Pantalla | ¿Autoguardado? | Por qué |
|---|---|---|
| Vivienda (alta y edición) | Sí | Formulario largo, de pie en la puerta |
| Hogar | Sí | Datos personales de la familia, toma tiempo |
| Integrantes (agregar y editar) | Sí | Se repite por cada persona del hogar |
| Ubicación GPS | Sí | Campos de texto simples; también protege lo que pone el botón "Capturar" (HU-11) |
| Borrador (nota y próxima visita) | Sí | Es exactamente la clase de nota que se escribe deprisa y se puede perder |
| Fotografías | **No** | Es un archivo binario, no texto. `localStorage` solo guarda cadenas de texto y tiene un límite de unos pocos MB; guardar una foto ahí exigiría codificarla en base64 (mucho más pesado) o usar `IndexedDB` con Blobs, un mecanismo bastante más grande que el de esta historia. La foto se sube cuando hay señal, igual que hoy. |
| Cerrar sin levantar / anular / validar | **No** | Son pantallas de decisión, no de captura de datos a lo largo del tiempo: se completan en un momento, no se van llenando de a poco de pie en una puerta. |
| Bandeja de revisión, paneles, gestión de usuarios, operativos | **No** | Fuera del flujo de la encuesta, que es lo único que pidió esta historia. |

---

## 4. Cómo funciona `autoguardado.js`

Un único archivo en `static/js/autoguardado.js`, cargado solo en las cinco plantillas
de la tabla anterior. Expone una función:

```js
OPSOAutoguardado.iniciar(clave, expiraHoras);  // expiraHoras es opcional, 24 por defecto
```

Que hace cuatro cosas:

1. **Al cargar la pantalla**, busca en `localStorage` un borrador guardado bajo esa
   clave. Si existe y no expiró, rellena los campos del formulario con esos valores y
   muestra un aviso: *"Recuperamos lo que estabas completando antes de que se cortara
   la conexión o se cerrara la pantalla"*, con un botón para descartarlo.
2. **Mientras se escribe**, guarda los valores de los campos en `localStorage` con un
   pequeño retraso (800 ms) para no escribir en cada tecla.
3. **Cada 5 segundos**, guarda igual, sea cual sea el origen del cambio. Es la red de
   respaldo para un caso concreto: el botón "Capturar mi ubicación" de
   `ubicacion_form.html` (HU-11) pone las coordenadas por código, y asignar `.value`
   desde JavaScript **no dispara** los eventos `input` ni `change` — sin este
   muestreo, una ubicación capturada por GPS no quedaría protegida.
4. **Al enviar el formulario**, borra el borrador guardado (ver §6).

No sabe nada de Django, de CSRF ni de las reglas de negocio de OPSO: encuentra el
`<form>` de la página con `document.querySelector("main form")`, mira los campos que
tienen `name`, y guarda y restaura por nombre. Es deliberadamente genérico para que
las cinco plantillas lo usen sin que el script tenga que conocer los campos de cada
una.

**Es `"main form"` y no `"form"` a secas** porque `base.html` tiene su propio
`<form>` para el botón de cerrar sesión de la barra de navegación, y ese formulario
aparece ANTES en el HTML que el contenido de la página. Un selector sin acotar habría
atado el autoguardado al formulario de cerrar sesión en vez de al de la encuesta —y de
hecho eso fue exactamente lo primero que pasó: ver §7, donde una prueba en un
navegador real lo encontró antes de llegar a producción.

**Lo que NO guarda:** casillas de verificación ni botones de radio. Por dos razones
distintas: `tiene_discapacidad` (integrante) es la única casilla con un dato real, y
perder un solo campo booleano no justifica la complejidad de tratarla aparte;
`confirmar_duplicado` (vivienda) y `confirmar_lejania` (ubicación) son banderas de
confirmación de **ese** intento de envío —restaurar una marcada de un intento anterior
podría saltarse una validación que ya no aplica, porque el conjunto de viviendas
"duplicadas" o la distancia a la zona pudo cambiar entretanto—.

---

## 5. Las claves

Cada pantalla llama a `iniciar()` con una clave que identifica de forma única lo que
se está completando:

| Pantalla | Clave |
|---|---|
| Vivienda, edición | `vivienda-{{ vivienda.pk }}` |
| Vivienda, alta | `vivienda-nueva` |
| Hogar | `hogar-{{ encuesta.pk }}` |
| Integrante, edición | `integrante-{{ integrante.pk }}` |
| Integrante, alta | `integrante-nuevo-{{ encuesta.pk }}` |
| Ubicación | `ubicacion-{{ vivienda.pk }}` |
| Borrador | `borrador-{{ encuesta.pk }}` |

Cuatro de las siete tienen un identificador estable en la URL (la vivienda, la
encuesta o el integrante ya existen), así que no hay ambigüedad posible: volver a esa
misma URL siempre corresponde al mismo borrador.

**"Vivienda, alta" es la excepción**, y se decidió no resolverla con más ingeniería.
`RegistrarViviendaView` vive en una única URL fija (`/encuestas/viviendas/nueva/`) para
CUALQUIER vivienda nueva —la zona se elige dentro del formulario, no en la URL—, así
que no hay ningún identificador disponible todavía cuando la pantalla se abre. Si un
censista abandona un alta a medias y, días después, empieza a registrar una vivienda
completamente distinta, técnicamente podría ver el aviso de recuperación con datos que
no le sirven. La mitigación es doble y deliberadamente simple: un vencimiento de 24
horas (pasado ese tiempo, el borrador se descarta solo) y que el aviso **siempre pide
confirmación visible** antes de usar nada — nunca sobrescribe en silencio, así que un
censista que no reconoce lo restaurado simplemente aprieta "Descartar" y sigue.
Resolver esta ambigüedad del todo exigiría inventar una noción de "sesión de alta" que
esta historia no necesita para el problema real que resuelve.

---

## 6. Por qué se limpia al enviar

`autoguardado.js` borra el borrador en el evento `submit` del formulario, **antes** de
que el navegador confirme si el envío llegó al servidor. Es una apuesta optimista, y es
deliberada: es el mismo criterio que usan los borradores de Gmail o de WordPress
—se marcan como enviados al hacer clic, no al recibir la confirmación del servidor—.

La alternativa —esperar una confirmación antes de borrar— exigiría convertir el envío
en una petición por AJAX para poder inspeccionar la respuesta, y eso es exactamente
la frontera que esta historia decidió no cruzar (§2): seguiría siendo un formulario
HTML normal, con recarga de página completa.

**¿Qué pasa si el envío falla justo en ese instante por falta de señal?** El navegador
no llega a cambiar de página —la solicitud nunca salió o no llegó respuesta—, así que
la pantalla sigue abierta con todo lo que el censista escribió todavía visible en los
campos. No se perdió nada en ESE momento. El único caso realmente afectado es que, si
además de fallar el envío el censista cierra la pestaña sin volver a intentarlo, el
borrador ya no está para protegerlo. Es una limitación conocida y documentada, no un
descuido: proteger también ese caso exigiría no limpiar en `submit` sino en una
confirmación de éxito, que es la puerta a la complejidad de AJAX que el diseño evitó a
propósito.

---

## 7. Sin pruebas automáticas

Este proyecto corre **1.389 pruebas** con el corredor de Django, y ninguna ejecuta
JavaScript: no hay Selenium, Playwright, ni ningún navegador headless configurado. Se
conversó explícitamente con el usuario antes de programar: agregar un corredor de
pruebas de navegador por primera vez en el proyecto era una opción, y se descartó a
favor de verificación manual, dado el alcance acotado de esta historia.

**Lo que sí se hizo, sin agregarlo al repositorio** —porque no hay infraestructura de
pruebas JS que lo sostenga—, en dos niveles:

**1. Lógica aislada, con Node.js.** Un script que carga `autoguardado.js` en un
sandbox (`vm.createContext`) con un `document`, un `localStorage` y un formulario
simulados, y comprueba: que un valor tecleado se guarda (con el retraso de 800 ms) y
se restaura en una "recarga" simulada con un formulario nuevo; que un borrador vencido
se descarta; que enviar el formulario borra el borrador; que un valor puesto por otro
script (simulando la captura de GPS) queda protegido por el muestreo periódico. Los
cuatro casos pasan, pero un DOM simulado con un solo `<form>` no puede detectar un
error que depende de CÓMO está armada la página real.

**2. Navegador real, con Chromium vía Playwright** (instalado temporalmente, sin
tocar `requirements.txt` ni el proyecto — Playwright y su navegador viven en un
directorio aparte y se desinstalaron al terminar), contra el `runserver` de Django
sobre PostgreSQL real, con una sesión de censista real. Este nivel **encontró un
error real** que ni la lectura del código ni el sandbox de Node.js habían detectado:

> `base.html` tiene su propio `<form>` para el botón de cerrar sesión de la barra de
> navegación, y ese formulario aparece en el HTML ANTES que el contenido de la
> página. La primera versión de `autoguardado.js` usaba
> `document.querySelector("form")` sin acotar, así que en la práctica el
> autoguardado se estaba atando al formulario de **cerrar sesión**, no al de la
> encuesta — nada se guardaba nunca, y la primera prueba real de "escribir y
> enviar" cerró la sesión del censista en pleno vuelo. El sandbox de Node.js no lo
> detectó porque ahí solo existía un `<form>` para encontrar; hacía falta la página
> completa, con su barra de navegación real, para que el error apareciera. Se corrigió
> acotando el selector a `"main form"` (§4) y la prueba se volvió a correr completa.

Con la corrección, los quince casos verificados en el navegador real pasan:

| # | Verificación | Resultado |
|---|---|---|
| 1 | Escribir en el campo de referencia guarda el valor en `localStorage` tras el debounce | ✅ |
| 2 | El valor guardado coincide exactamente con lo escrito | ✅ |
| 3 | Al recargar la misma pantalla (simulando volver tras un corte), el campo se rellena solo | ✅ |
| 4 | Aparece el aviso "Recuperamos lo que estabas completando…" | ✅ |
| 5 | "Descartar" borra el valor de `localStorage` | ✅ |
| 6 | "Descartar" hace desaparecer el aviso | ✅ |
| 7 | Hay un borrador guardado justo antes de enviar el formulario (verificación del propio montaje de la prueba) | ✅ |
| 8 | Enviar el formulario navega fuera de la pantalla de edición (POST-redirect-GET real) | ✅ |
| 9 | Tras un envío exitoso, `localStorage` queda sin el borrador (HU-22: el POST *es* la sincronización) | ✅ |
| 10 | El botón "Capturar mi ubicación" (HU-11) rellena el campo de latitud vía `navigator.geolocation` simulado por Playwright | ✅ |
| 11 | El muestreo periódico de 5 s guarda ese valor en `localStorage` | ✅ |
| 12 | El valor guardado coincide con el capturado — **aunque la asignación por GPS nunca disparó `input` ni `change`** | ✅ |
| 13 | Con el script de autoguardado bloqueado (`page.route(...).abort()`), la pantalla igual carga | ✅ |
| 14 | Con el script bloqueado, el campo de texto sigue siendo editable | ✅ |
| 15 | (Diagnóstico previo) confirmar con `django.test.Client` que las cinco pantallas cargan el script y llaman a `OPSOAutoguardado.iniciar()` con la clave correcta | ✅ |

No sustituye tener Selenium o Playwright instalados de forma permanente en el
proyecto —esa decisión se conversó con el usuario y se descartó por alcance (§ver
arriba)—, pero es una verificación real, no una simulación de una: un Chromium de
verdad, cargando el HTML real, con la sesión real de un censista, contra PostgreSQL.

---

## 8. Archivos

### Creados

```
backend/static/js/autoguardado.js                    el módulo de autoguardado
backend/docs/HU-21_autoguardado_sin_conexion.md       este documento
```

### Modificados

```
backend/templates/fichas/vivienda_form.html
    + {% load static %}
    + {% block js_extra %} con OPSOAutoguardado.iniciar("vivienda-...")

backend/templates/fichas/hogar_form.html
    + {% load static %}
    + {% block js_extra %} con OPSOAutoguardado.iniciar("hogar-...")

backend/templates/fichas/integrante_form.html
    + {% load static %}
    + {% block js_extra %} con OPSOAutoguardado.iniciar("integrante-...")

backend/templates/fichas/borrador_form.html
    + {% load static %}
    + {% block js_extra %} con OPSOAutoguardado.iniciar("borrador-...")

backend/templates/fichas/ubicacion_form.html
    + {% load static %}
    ~ cabecera actualizada: ya no es "la única pantalla con JavaScript propio"
    + OPSOAutoguardado.iniciar("ubicacion-...") dentro del mismo {% block js_extra %}
      que ya existía para la captura de GPS (HU-11)

backend/README.md
    ~ fila de HU-21: «✅ Implementada, verificada manualmente», con enlace
```

Ninguna migración, ninguna vista nueva, ningún modelo tocado: es JavaScript de cliente
puro sobre plantillas que ya existían.

---

## 9. Verificación manual

Con `runserver` sobre PostgreSQL, como censista:

| Paso | Resultado esperado | Resultado obtenido |
|---|---|---|
| `GET /encuestas/viviendas/nueva/` | La página incluye `<script src=".../autoguardado.js">` y `OPSOAutoguardado.iniciar("vivienda-nueva")` | ✅ (confirmado con `django.test.Client`) |
| `GET /encuestas/<pk>/hogar/`, `.../integrantes/nuevo/`, `.../integrantes/<id>/editar/`, `.../borrador/`, `viviendas/<pk>/ubicacion/`, `viviendas/<pk>/editar/` | Cada una con la clave correspondiente de la tabla del §5 | ✅ (confirmado con `django.test.Client` contra una encuesta en BORRADOR real) |
| `curl http://127.0.0.1:8000/static/js/autoguardado.js` | 200, contenido del módulo | ✅ |
| Verificación de lógica con Node.js (sandbox simulado) | Guardar+restaurar, expiración, limpieza al enviar, muestreo periódico | ✅ los cuatro casos |
| **Navegador real (Chromium/Playwright) contra `runserver` + PostgreSQL** | Los 15 casos del §7 — escribir, "cortar conexión", recuperar, descartar, enviar, GPS, y que la pantalla siga funcionando con el script bloqueado | ✅ los 15, después de corregir el error real que la propia prueba encontró (§7) |

No queda pendiente la prueba manual en un teléfono real que se planteó al principio:
la verificación con Chromium cubre el mismo recorrido (escribir, simular corte,
recuperar) de forma repetible, y de hecho encontró un error que una pasada manual
única podría no haber notado si el aviso de recuperación simplemente no aparecía. Lo
que sigue sin cubrir esta verificación es específico del hardware: el comportamiento
exacto de un teléfono real quedándose sin señal a mitad de una petición HTTP en curso
(no simulable con Playwright, que corta la red de forma limpia, no a mitad de una
petición).

---

## 10. Explicación para la defensa

**En una frase:** esta historia protege el trabajo en curso de una conexión que se
corta a ratos, con la menor cantidad de JavaScript posible y sin convertir OPSO en una
aplicación offline completa, que es un problema distinto al que el enunciado
confirmado realmente planteaba.

**Lo que conviene poder defender:**

1. **Se conversó el alcance antes de programar.** "Sin conexión" tiene una lectura
   chica (intermitente) y una grande (PWA completa); confirmar cuál era la real
   cambiaba por completo el diseño, y se confirmó con el usuario antes de escribir
   código.
2. **Progressive enhancement, no reemplazo.** El formulario funciona exactamente
   igual sin JavaScript. La HU-11 ya sentó este principio para la captura de GPS; esta
   historia lo extiende, no lo inventa.
3. **Genérico por nombre de campo, no por formulario.** Un solo archivo sirve para
   las cinco pantallas porque opera sobre cualquier `<form>` mirando los `name` de sus
   campos, sin necesitar conocer la vivienda, el hogar o el integrante.
4. **Limitaciones documentadas, no escondidas.** El caso ambiguo de "vivienda nueva"
   (§5) y el límite del borrado optimista al enviar (§6) están explicados con su
   porqué, no se descubren leyendo el código.
5. **Primera funcionalidad sin pruebas automáticas *permanentes* del proyecto, y se
   dice.** No se simuló cobertura que no existe. Sí se verificó con un navegador real
   (Chromium vía Playwright, instalado temporalmente) antes de dar la historia por
   cerrada, y esa verificación encontró y corrigió un error real —el autoguardado
   estaba atado al formulario de cerrar sesión, no al de la encuesta (§7)— que ni la
   lectura del código ni una prueba con un DOM simulado habían detectado. Es la
   demostración concreta de por qué "probarlo en un navegador de verdad" no es un paso
   protocolar: encontró algo que las otras dos formas de verificar, ya hechas antes,
   no habían encontrado.

---

## 11. Posibles preguntas del profesor

**¿Por qué esto no es una PWA, si "trabajar sin conexión" es literalmente lo que
hacen las PWA?**
Porque el escenario confirmado con el usuario fue conexión intermitente, no
desconexión total durante horas. Una PWA resuelve un problema que nadie planteó
—poder abrir la pantalla sin red— a costa de un cambio de arquitectura real (service
worker, `IndexedDB`, probablemente una API en JSON), cuando el problema real solo
necesitaba proteger lo escrito antes de que un envío no llegara a tiempo.

**¿Por qué las fotografías quedan fuera?**
Por una razón técnica, no de alcance: son archivos binarios, y `localStorage` solo
guarda texto con un límite de unos pocos megabytes. Meter una foto ahí exigiría
codificarla en base64 (mucho más pesada) o pasar a `IndexedDB` con Blobs, un mecanismo
bastante más grande que el resto de esta historia.

**¿Qué pasa si dos censistas usan el mismo teléfono?**
El borrador queda en `localStorage`, que es del navegador, no de la cuenta. Si el
segundo censista abre la misma vivienda o encuesta (lo cual ya requiere que el sistema
se la haya asignado a él), vería el borrador del primero. El borrado al enviar (§6)
acota la ventana de exposición: en cuanto el primer censista guarda con éxito, el
borrador desaparece.

**¿Por qué el muestreo cada 5 segundos, y no confiar solo en los eventos `input` y
`change`?**
Porque hay un caso real en el propio proyecto donde esos eventos no alcanzan: el botón
"Capturar mi ubicación" de la HU-11 asigna `.value` a los campos de latitud y longitud
por código, y una asignación por código no dispara esos eventos en ningún navegador.
Sin el muestreo periódico, una ubicación capturada por GPS —el dato más costoso de
recuperar en terreno— quedaría sin proteger.

**¿Se agregó algún campo o migración nueva?**
No. Es JavaScript de cliente puro sobre formularios que ya existían desde la HU-08,
HU-09, HU-10 y HU-11.

**¿Realmente se probó en un navegador, o quedó solo en la lógica simulada con
Node.js?**
Se probó en un Chromium real, con Playwright instalado temporalmente solo para esta
verificación (no quedó en el proyecto). Y no fue una formalidad: encontró un error de
verdad. La primera versión de `autoguardado.js` usaba `document.querySelector("form")`
sin acotar, y como `base.html` tiene su propio `<form>` para el botón de cerrar
sesión —que aparece antes en el HTML que el contenido de la página—, el autoguardado
se estaba enganchando al formulario equivocado: nada se guardaba nunca, y la primera
prueba de "escribir y enviar" cerró la sesión del censista en pleno vuelo, en vez de
guardar la vivienda. El sandbox de Node.js no lo detectó porque ahí solo existía un
`<form>` para encontrar. Se corrigió acotando a `"main form"`, y las quince
verificaciones del §7 pasan con la corrección.
