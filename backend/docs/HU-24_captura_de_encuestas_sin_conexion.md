# HU-24 · Capturar encuestas completas sin conexión

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como censista, quiero completar una encuesta entera —vivienda, hogar, integrantes y ubicación— aunque no tenga conexión, y sincronizarla cuando la recupere, para poder censar varias viviendas seguidas en una zona sin señal.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · JavaScript nativo (IndexedDB, Service Worker, `fetch`)
**Estado:** implementada. Servidor con batería completa de pruebas automáticas; asistente (HTML + JavaScript) verificado en un navegador real (Chromium vía Playwright, instalado temporalmente).

> Reemplaza el mecanismo de la [HU-21](HU-21_autoguardado_sin_conexion.md)/[HU-22](HU-22_sincronizar_al_recuperar_conexion.md) para el caso de **crear una encuesta nueva**. No nace de un enunciado del backlog original: nace de que, en uso real, se reportó que la HU-21 "no servía" — protegía un formulario mientras la pestaña seguía abierta esperando conexión, pero no permitía avanzar de pantalla sin servidor, y por lo tanto no permitía censar una vivienda sin señal, que es exactamente el problema que un censista describió: *"hay 10 casas que no tienen señal en esa zona y se deben registrar; luego, en algún lugar con internet o en la tarde, presionando un botón sincronizar, se puedan subir estas encuestas."*

---

## Índice

1. [Por qué la HU-21 no alcanzaba](#1-por-qué-la-hu-21-no-alcanzaba)
2. [La decisión de arquitectura](#2-la-decisión-de-arquitectura)
3. [Alcance: qué cubre el asistente y qué no](#3-alcance)
4. [Captura: IndexedDB, no localStorage](#4-captura)
5. [Sincronización: reutilizar los forms de siempre](#5-sincronización)
6. [Idempotencia: sincronizar dos veces es seguro](#6-idempotencia)
7. [El service worker: solo para la carga en frío](#7-service-worker)
8. [Lo que el navegador no puede validar solo](#8-validación)
9. [Archivos](#9-archivos)
10. [Verificación en un navegador real](#10-verificación)
11. [Limitaciones que quedan documentadas a propósito](#11-limitaciones)
12. [Explicación para la defensa](#12-defensa)
13. [Posibles preguntas del profesor](#13-preguntas)

---

## 1. Por qué la HU-21 no alcanzaba

Hasta la HU-23, crear una encuesta era una cadena de pantallas donde **cada una es un
POST real que devuelve un `pk` real**, y la siguiente pantalla necesita ese `pk` para
poder existir (`fichas/urls.py`: `viviendas/nueva/` → `<pk>/hogar/` →
`<encuesta_pk>/integrantes/nuevo/` → …). `autoguardado.js` (HU-21) protegía el
contenido de un formulario mientras se esperaba que ese POST llegara a internet, pero
si no hay conexión el POST simplemente no llega, y sin él no hay `pk`, y sin `pk` no
hay pantalla siguiente. No es un defecto de implementación: es una limitación
estructural del diseño. La HU-21 lo dice en su propio documento (§7): *"no es una app
offline… no guarda encuestas completas para reenviarlas después"*.

Separar la CAPTURA de la SINCRONIZACIÓN es la única forma honesta de resolver el caso
real: la captura ocurre entera en el navegador, sin ningún viaje al servidor; la
sincronización es un solo POST por encuesta, cuando hay señal, que reutiliza toda la
validación de servidor que ya existía.

---

## 2. La decisión de arquitectura

Se conversó con el usuario antes de escribir código (igual que la HU-21) porque esto
cruza el mismo límite de `CLAUDE.md` que ya había cruzado la HU-21/HU-23 —*"sin API
REST ni JavaScript de aplicación"*— y lo cruza más profundamente: es la primera vez
que el proyecto necesita un endpoint que recibe JSON en vez de un formulario, y la
primera vez que hace falta un Service Worker.

Dos preguntas se resolvieron explícitamente con el usuario:

| Pregunta | Decisión | Por qué |
|---|---|---|
| ¿El avance debe sobrevivir a cerrar la pestaña o el navegador? | **Sí, con `IndexedDB`** | Con 10 viviendas en una jornada de terreno, exigir que la pestaña siga abierta todo el día es una condición que se va a violar. `localStorage` (como usa la HU-21) no es la herramienta correcta para algo del tamaño de una encuesta completa; `IndexedDB` sí. |
| ¿Hace falta poder cargar el asistente con **cero señal desde el arranque** (celular reiniciado, app cerrada del todo)? | **Sí, con un Service Worker mínimo** | Es exactamente el escenario descrito ("no hay señal en esa zona"): el celular puede quedarse sin batería o la app puede cerrarse del todo en terreno. Sin un Service Worker, un navegador no puede mostrar una página que nunca cacheó. |

Con las dos respondidas en "sí", y dado que el flujo de creación ya no puede vivir en
un formulario servidor-renderizado por pantalla, se decidió además: **el asistente
offline es la única forma de crear una encuesta nueva**, con o sin conexión — no se
mantienen dos interfaces paralelas (una online, otra offline) para la misma tarea.

---

## 3. Alcance

**Cubre:** crear una encuesta **desde cero** — vivienda → hogar → integrantes →
ubicación (opcional) → borrador/completar/cerrar sin datos — en una sola pantalla,
sin recargar, guardando en `IndexedDB` en cada paso.

**No cubre, a propósito**, todo lo que actúa sobre una encuesta que **ya existe en el
servidor**:

| Situación | Sigue funcionando exactamente igual que antes |
|---|---|
| Continuar un borrador otro día | `GuardarBorradorView`/`CompletarEncuestaView` (HU-10), con `autoguardado.js` protegiéndolos |
| Agregar un integrante más tarde | `RegistrarIntegranteView` (HU-09) |
| Corregir tras una devolución del supervisor | El flujo de la HU-15, sin cambios |
| Editar la vivienda, agregar GPS a una ya registrada | `EditarViviendaView`, `CapturarUbicacionView` (HU-11) |
| Fotografías | `SubirFotografiaView` (HU-12) — **fuera del asistente offline por decisión explícita**, ver más abajo |

La razón es simple: todas esas operaciones necesitan el `pk` real del servidor para
saber qué fila tocar, así que ya son inherentemente online. Rehacerlas offline sería
resolver un problema que nadie planteó, y duplicaría toda esa lógica sin necesidad.

**Fotografías fuera del asistente.** Se confirmó revisando
`Encuesta.pasos_pendientes()`/`puede_completarse` (`fichas/models.py`) que **nada**
exige fotografías para completar una encuesta. Diferirlas es seguro: el censista las
agrega después, con conexión, por la pantalla que ya existe. Meterlas en el asistente
habría significado guardar archivos binarios en `IndexedDB` para un dato que el propio
modelo de datos ya trata como opcional y postergable.

---

## 4. Captura

`static/js/encuesta_offline.js` guarda cada encuesta en curso como un registro de
`IndexedDB` (base `opso-encuestas-offline`, almacén `encuestas`), con clave
`clienteId` — un UUID que **genera el teléfono** (`crypto.randomUUID()`) antes de que
exista ningún `pk` del servidor.

Se guarda **en cada paso**, no solo al final (`guardarProgreso()` en cada botón
"Siguiente" y cada vez que se agrega un integrante), con dos estados:

- `estadoLocal: "en_progreso"` — la encuesta actual del asistente, mientras se está
  llenando.
- `estadoLocal: "pendiente"` — ya se completó el paso 5 ("Guardar en este teléfono") y
  está lista para sincronizar.

**Recuperar un borrador a medias.** Si se cierra la pestaña con una encuesta a medio
capturar, al volver a abrir `/encuestas/nueva/` el asistente busca un registro
`en_progreso` en `IndexedDB` y ofrece continuar donde quedó (rellena los campos
guardados y salta directo al paso correcto) o descartarlo. Esto es lo que convierte
"los datos sobreviven en `IndexedDB`" en "el censista realmente puede seguir
trabajando" — sin esto, los datos estarían a salvo pero inalcanzables.

---

## 5. Sincronización

`SincronizarEncuestaOfflineView` (`fichas/views.py`, POST JSON,
`/encuestas/sincronizar/`) recibe el objeto completo de una encuesta y, dentro de
`transaction.atomic()`, construye **los mismos formularios que usa el flujo online**:
`ViviendaForm`, `GrupoFamiliarForm`, un `IntegranteForm` por cada persona,
`UbicacionForm` si hay GPS, y `BorradorForm`/`CerrarSinDatosForm` según el resultado
elegido — con `censista=request.user`, exactamente como
`RegistrarViviendaView`/`RegistrarHogarView`/etc. hacían antes.

Esto no es una economía de líneas: es la garantía de que **una encuesta capturada
offline pasa por las mismas reglas de negocio que una capturada online**, sin
mantener esas reglas escritas dos veces. Si algún día cambia una regla —el largo
mínimo de un motivo de cierre, el rango de coordenadas de Chile—, cambia en un solo
sitio y las dos vías la heredan.

Si cualquier formulario falla, no se crea nada (`transaction.atomic()` revierte la
vivienda, el hogar y los integrantes que sí se habían guardado) y se devuelve
`{"exito": false, "errores": {...}}` con el detalle por campo.

El botón **"Sincronizar"** (en `templates/fichas/mis_encuestas.html`, cargando
`encuesta_offline.js` en modo "gestionar cola") recorre la cola local **una por una,
en orden** — no en paralelo, más predecible sobre una señal débil — y nunca en
segundo plano ni de forma silenciosa: el censista ve, encuesta por encuesta, cuál se
sincronizó y cuál no. Es el mismo criterio que ya había fijado la HU-22 al rechazar un
motor de sincronización automático.

### El servidor no confía en lo que el celular asegura

El JavaScript del asistente no puede validar offline nada que dependa de una consulta
a la base de datos en ese instante: si la dirección ya está registrada, si la zona
elegida sigue asignada a ese censista, si el punto GPS queda lejos del resto de la
zona. `ViviendaForm` reconstruye el `queryset` de zonas permitidas con
`censista=request.user` **en el momento de sincronizar**, así que una zona que dejó de
estar asignada (por ejemplo, porque el supervisor reasignó el sector mientras el
censista estaba en terreno) se rechaza igual que se rechazaría online, aunque el
`payload` la incluya. Verificado con una prueba dedicada
(`test_una_zona_ajena_no_crea_nada`).

---

## 6. Idempotencia

Una conexión débil puede cortar la **respuesta** de un POST que en realidad sí llegó a
guardarse en el servidor, y el asistente no tiene forma de distinguir eso de un fallo
real — reintentaría y crearía una encuesta duplicada.

Se agrega `Encuesta.origen_offline_id` (`UUIDField`, `null=True`, `unique=True`,
migración `0009_encuesta_origen_offline_id`), que guarda el `clienteId` generado en el
teléfono. Si llega un `clienteId` que ya existe, `SincronizarEncuestaOfflineView`
devuelve la encuesta ya creada en vez de duplicarla. Sincronizar dos veces la misma
encuesta es, por diseño, un no-op seguro — verificado con
`test_reenviar_el_mismo_cliente_id_no_duplica`.

---

## 7. Service worker

`static/js/encuesta_offline_sw.js`, servido desde **la raíz del dominio** (`/sw.js`,
vía `ServirServiceWorkerView` en `fichas/views.py` y una ruta explícita en
`config/urls.py`) — no desde `/static/js/...`, porque el "alcance" (`scope`) de un
service worker nunca puede ser más amplio que la ruta desde la que el navegador lo
obtuvo, y servido bajo `/static/` solo podría vigilar `/static/`.

Alcance deliberadamente mínimo: cachea únicamente la página `/encuestas/nueva/` y los
`/static/js/encuesta_offline*`, `/static/vendor/` y `/static/css/` que esa página usa
— nada de datos, ninguna otra pantalla del sitio, y nunca un POST (el `fetch` handler
ignora explícitamente cualquier método distinto de `GET`). Estrategia "red primero,
caché de respaldo": cada visita con señal refresca lo cacheado; sin señal, se sirve lo
último bueno.

**Por qué no se hardcodea la lista de archivos a cachear.** En producción,
`ManifestStaticFilesStorage` (`config/settings.py`, activo cuando `DEBUG=False`)
sirve los archivos estáticos con un nombre hasheado que cambia en cada despliegue
(`encuesta_offline.abc123.js`). El `install` del service worker no adivina esos
nombres: pide la propia página `/encuestas/nueva/` y **lee de su HTML ya renderizado**
qué `<script src>`/`<link href>` de `/static/` contiene, y cachea exactamente esas
URLs. Es correcto en desarrollo y en producción sin mantener una lista a mano.

**Detrás del login, sin `login_not_required`.** El navegador solo necesita descargar
`/sw.js` una vez, estando conectado y autenticado, para instalarlo; una vez activo no
necesita volver a pedirlo por red para seguir sirviendo la página offline.

---

## 8. Validación

División deliberada entre lo que el navegador puede comprobar sin servidor y lo que
no:

**Sí, en el cliente** (feedback inmediato, mismo criterio que cada `Form`):
campos requeridos, largos mínimos (`nombres`, `apellidos`, `jefe_hogar_nombre`,
`motivo_cierre`), rangos numéricos (`ingreso_mensual`, coordenadas dentro de Chile),
fecha de nacimiento no futura, dígito verificador del RUT (algoritmo portado de
`usuarios/validators.py:calcular_digito_verificador` a JavaScript), un solo jefe de
hogar, RUT único **dentro de la misma encuesta** (los integrantes ya están todos en
la lista local).

**No, queda para el servidor**: dirección duplicada en la zona, que la zona siga
vigente para ese censista, distancia al resto de la zona ya ubicada, tope de
fotografías (no aplica, fuera de alcance). Todas dependen de una consulta a la base de
datos en el instante de sincronizar, que offline no existe.

**Confirmar y reintentar, sin reabrir el asistente.** Dos de esos rechazos del
servidor son exactamente el mismo tipo de aviso que ya existía online —"hay un
posible duplicado, confirma si es así a propósito"—: dirección duplicada
(`confirmar_duplicado`) y punto lejos del resto de la zona (`confirmar_lejania`). La
cola de "Mis encuestas" detecta estos dos casos en la respuesta de error y ofrece una
casilla "Confirmar de todas formas y reintentar" que reenvía el mismo `payload` con el
campo en `true` — sin tener que volver a capturar nada. Cualquier otro rechazo
(un dato realmente inválido) se queda en la cola con el motivo visible; corregirlo
significa eliminar esa encuesta de la cola y volver a capturarla — ver §11.

---

## 9. Archivos

### Nuevos

```
backend/templates/fichas/encuesta_offline.html      el asistente (estructura, sin lógica)
backend/static/js/encuesta_offline.js                IndexedDB + validación + sincronización
backend/static/js/encuesta_offline_sw.js             el service worker
backend/fichas/migrations/0009_encuesta_origen_offline_id.py
backend/docs/HU-24_captura_de_encuestas_sin_conexion.md
```

### Modificados

```
backend/fichas/models.py     + Encuesta.origen_offline_id

backend/fichas/views.py      - RegistrarViviendaView (reemplazada)
                              + EncuestaOfflineView, SincronizarEncuestaOfflineView,
                                ServirServiceWorkerView

backend/fichas/urls.py       ~ vivienda_registrar -> encuesta_nueva
                              + sincronizar_encuesta_offline

backend/config/urls.py       + path("sw.js", ...) antes del include raíz

backend/templates/fichas/mis_encuestas.html
                              ~ el botón "Registrar una vivienda" apunta al asistente
                              + cola de "Encuestas pendientes de sincronizar" + botón

backend/fichas/tests.py      ~ RegistrarViviendaTest -> EncuestaOfflineViewTest
                                (recorta las pruebas de creación, que se movieron)
                              + SincronizarEncuestaOfflineTest (sección HU-24)
                              ~ IntegracionHU08Test/IntegracionHU10Test: el paso 1
                                (registrar la vivienda) usa el helper de la clase
                                base en vez de POST a la vista eliminada

backend/README.md            ~ filas HU-21/HU-22 marcadas como superadas, fila HU-24,
                                conteo de pruebas actualizado

backend/docs/HU-21_*.md,
backend/docs/HU-22_*.md      + nota al inicio: superadas por esta historia
```

`vivienda_form.html`, `hogar_form.html`, `integrante_form.html`, `borrador_form.html`
y su cableado de `autoguardado.js` **no se tocan**: siguen sirviendo para
editar/continuar encuestas que ya existen en el servidor, exactamente como los dejó la
HU-21.

---

## 10. Verificación

Servidor: `DB_ENGINE=sqlite3 manage.py test fichas` — 24 pruebas nuevas
(`SincronizarEncuestaOfflineTest`, `EncuestaOfflineViewTest`) cubriendo el caso feliz,
permisos, zona ajena rechazada pese al `payload`, formulario incompleto sin dejar
nada a medias, dirección duplicada (rechazo y confirmación), RUT repetido entre
integrantes (transacción completa revertida), ubicación fuera de Chile, completar con
y sin todos los integrantes, cerrar sin datos, e idempotencia por `clienteId`. Batería
completa: **1.398 pruebas**, `makemigrations --check --dry-run` limpio, `check
--deploy` en los 5 warnings conocidos.

Navegador real (Playwright, Chromium, instalado y desinstalado para la ocasión, contra
`runserver` + PostgreSQL real, con `censista@opso.cl`):

| # | Verificación | Resultado |
|---|---|---|
| 1 | El asistente carga y trae las zonas asignadas al censista | ✅ |
| 2 | El service worker queda activo tras la primera carga con conexión | ✅ |
| 3 | Vivienda → hogar → integrantes → ubicación → resultado, sin ningún POST intermedio | ✅ |
| 4 | El asistente calcula localmente si faltan datos para "completar" | ✅ |
| 5 | Guardar en el teléfono deja el registro en `IndexedDB` como pendiente | ✅ |
| 6 | La cola en "Mis encuestas" muestra la pendiente y el botón la sincroniza | ✅ |
| 7 | La encuesta sincronizada existe de verdad en el servidor (con los datos correctos) | ✅ |
| 8 | Con `context.setOffline(true)` (offline real, no simulado a medias): el asistente carga con la pestaña ya abierta | ✅ |
| 9 | Se captura una encuesta **completa**, de principio a fin, sin ninguna conexión | ✅ |
| 10 | Con progreso a medias (vivienda + hogar guardados) se cierra la pestaña y se abre una nueva, siempre offline: la pestaña nueva carga `/encuestas/nueva/` desde el service worker, sin red | ✅ |
| 11 | Ofrece recuperar el borrador a medias y salta directo al paso donde había quedado | ✅ |
| 12 | Los datos ya guardados (nombre de la jefa de hogar) se restauran correctamente | ✅ |
| 13 | Se termina de capturar la encuesta recuperada, sigue offline | ✅ |
| 14 | Al volver la señal, las dos encuestas capturadas offline aparecen en la cola | ✅ |
| 15 | Se sincronizan y quedan creadas en el servidor | ✅ |

Un primer intento de esta batería encontró tres errores reales antes de comitear
—mismo patrón que la verificación de la [HU-21](HU-21_autoguardado_sin_conexion.md)
encontró un error real con `autoguardado.js` (su §9), y que sin probar en un
navegador de verdad no se habría notado—: la migración nueva no se había aplicado a
la base PostgreSQL real de desarrollo (solo corría en la base SQLite desechable de las
pruebas automáticas); el bloque `{{ datos_iniciales|json_script:"..." }}` estaba
escrito **fuera** de cualquier `{% block %}` en una plantilla que extiende
`base.html`, y Django descarta en silencio todo lo que queda fuera de un bloque —el
asistente cargaba (200 OK) pero sin ningún dato, sin que nada avisara del error; y
`Integrante.pueblo_originario` resultó ser un campo obligatorio en el servidor
(`blank` no declarado, con `default=PuebloOriginario.NINGUNO`) que el asistente
dejaba pasar en blanco. Los tres se corrigieron y se volvió a verificar la batería
completa hasta que quedó limpia.

---

## 11. Limitaciones

**Corregir un dato rechazado al sincronizar (fuera de duplicado/lejanía) exige volver
a capturar.** La cola de "Mis encuestas" no reabre el asistente pre-rellenado para
editar una encuesta ya guardada localmente con un error de validación genuino (un RUT
mal escrito, por ejemplo): solo ofrece eliminarla de la cola. Es una limitación real,
aceptada a propósito por alcance: reabrir el asistente en modo edición para una
encuesta que todavía no tiene `pk` del servidor habría significado duplicar buena
parte de la lógica de "restaurar campos" que ya existe para la recuperación de
borradores, para un caso que en la práctica debería ser raro (el asistente ya replica
en el cliente casi todas las reglas de formato que producen ese tipo de rechazo).

**Solo un borrador "en progreso" a la vez.** El asistente resuelve "cerré la pestaña a
medio camino de la vivienda que estoy censando ahora mismo", no "tengo tres viviendas
a medio empezar en simultáneo". Encaja con el flujo real (se censa una casa, se
termina o se cierra, se pasa a la siguiente), y mantiene la recuperación de borrador
simple: un solo banner, no una lista de borradores para elegir.

**La primera carga alguna vez tiene que ser online.** El service worker no puede
cachear lo que nunca se sirvió: si el celular jamás cargó `/encuestas/nueva/` con
conexión, no hay nada que mostrar offline. En la práctica esto se resuelve solo
—el censista abre la app al salir de la oficina, con señal, antes de entrar a la zona
sin cobertura—, pero es una dependencia real y queda dicha.

---

## 12. Explicación para la defensa

**En una frase:** la HU-21 protegía un formulario esperando que el envío llegara al
servidor; esta historia separa CAPTURAR (enteramente en el navegador, con
`IndexedDB`) de SINCRONIZAR (un solo POST por encuesta, reutilizando los mismos
formularios de Django de siempre), y agrega un service worker mínimo para que la
pantalla de captura cargue incluso con cero señal desde el arranque.

**Lo que conviene poder defender:**

1. **Por qué esto no se pudo resolver dentro de la HU-21.** El diagnóstico está en
   el §1: cada pantalla del flujo online es un POST que devuelve un `pk`, y sin `pk`
   no hay pantalla siguiente. No es una mejora incremental, es un cambio de
   arquitectura para esa parte del sistema.
2. **Por qué se reutilizan los `Form` de Django en vez de reimplementar las reglas en
   el servidor.** `SincronizarEncuestaOfflineView` construye exactamente los mismos
   `ViviendaForm`/`GrupoFamiliarForm`/`IntegranteForm` que usaban las vistas
   eliminadas: una regla de negocio vive en un solo sitio, la valide quien la valide.
3. **Por qué la idempotencia importa y cómo se resuelve.** `origen_offline_id`
   convierte "reintentar una sincronización que en realidad ya había funcionado" en
   un no-op seguro, en vez de una encuesta duplicada.
4. **Por qué el service worker no cachea una lista fija de archivos.** Producción
   hashea los nombres de los estáticos; el `install` lee la propia página renderizada
   para descubrir qué cachear, en vez de adivinar nombres que van a cambiar.
5. **Qué queda deliberadamente fuera** (fotografías, continuar una encuesta que ya
   existe en el servidor) y por qué: son problemas distintos, ya resueltos, que no
   necesitaban este cambio.
6. **Se verificó en un navegador real con offline verdadero** (`context.setOffline`
   de Playwright, no solo "se asume que funciona"), y esa verificación encontró tres
   errores reales antes de comitear — ver §10.

---

## 13. Posibles preguntas del profesor

**¿Por qué no una PWA completa, con manifest.json e instalable en la pantalla de
inicio?** Porque nadie pidió eso: el enunciado pide poder censar sin señal y
sincronizar después, no una app instalable. Un manifest y un ícono de instalación son
una capa más de superficie que mantener sin que resuelvan un problema adicional.

**¿Qué pasa si dos censistas capturan la misma dirección offline, cada uno sin saber
del otro?** Exactamente lo mismo que pasaría online: la segunda sincronización recibe
el aviso de "dirección duplicada, confirma si es distinta" —la validación corre en el
servidor, con los datos reales del servidor, en el momento de sincronizar, nunca
antes—.

**¿El código JavaScript nuevo tiene pruebas automáticas?** No, por la misma razón que
la HU-21 y la HU-23: el proyecto no tiene Selenium ni Playwright configurado de forma
permanente. Se verificó con Playwright instalado temporalmente contra el servidor y la
base de datos reales, incluyendo offline real vía `context.setOffline`, y se
desinstaló al terminar. La parte de servidor —donde vive toda la validación real— sí
tiene batería completa con el corredor de Django.

**¿Por qué las fotografías no se pueden capturar (aunque sea el archivo, para subirlo
después) desde el asistente offline?** Se evaluó y se descartó: habría exigido
guardar archivos binarios en `IndexedDB` (con su propio límite de espacio, distinto al
de `localStorage`) para un dato que el propio modelo ya trata como opcional y
postergable — nada en `pasos_pendientes()` lo exige. El censista las agrega después,
con conexión, por la pantalla que ya existía.

**¿Cómo sabe el servidor que la encuesta la capturó ese censista y no otro, si se
creó offline?** La identidad la pone la sesión que hace el POST de sincronización, no
un campo del `payload`: `SincronizarEncuestaOfflineView` usa `request.user` igual que
hacía `RegistrarViviendaView`. El `payload` nunca declara quién es el censista; si lo
hiciera, sería un vector para que alguien atribuyera una encuesta a otra persona.
