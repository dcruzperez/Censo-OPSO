# HU-15 · Devolver encuestas con observaciones

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor, quiero devolver encuestas con observaciones para solicitar correcciones al encuestador.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **80 pruebas automáticas** propias (**1.319** en total en el proyecto → `python manage.py test` → OK)

> Tercera historia del sprint de supervisión. **No agrega ni un permiso ni un estado**:
> reutiliza `fichas.validar` y `OBSERVADA`, que la HU-07 definió ocho historias antes
> sin que nadie pudiera ponerlo todavía. Agrega **un contador, un método, un
> formulario y —lo más importante— la mitad que faltaba: que el encuestador LEA lo que
> se le pide.**

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Lo que ya estaba hecho, y por qué eso es una buena noticia](#2-lo-que-ya-estaba-hecho)
3. [Devolver, validar y anular: tres salidas distintas](#3-tres-salidas-distintas)
4. [La restricción que cambió de nombre](#4-la-restricción-que-cambió-de-nombre)
5. [La migración y su paso de datos](#5-la-migración-y-su-paso-de-datos)
6. [`devolver()`: por qué un método propio](#6-devolver)
7. [`veces_devuelta`: cuando el problema deja de ser la ficha](#7-veces_devuelta)
8. [`problemas_detectados()`: prerrellenar sin decidir](#8-problemas_detectados)
9. [El formulario: aspectos + texto, y ninguna casilla](#9-el-formulario)
10. [La mitad que faltaba: que el encuestador lo lea](#10-la-mitad-que-faltaba)
11. [Vistas, URLs y templates](#11-vistas-urls-y-templates)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Verificación manual](#14-verificación-manual)
15. [Explicación para la defensa](#15-explicación-para-la-defensa)
16. [Posibles preguntas del profesor](#16-posibles-preguntas-del-profesor)
17. [Conclusión técnica](#17-conclusión-técnica)

---

## 1. Explicación inicial

La HU-14 dejó dos salidas para una encuesta recibida, y las dos **cierran**:

```
                        ┌──validar──> VALIDADA   (aprobada, cerrada)
COMPLETADA ─────────────┤
(esperando revisión)    └──anular───> ANULADA    (descartada, cerrada)
```

Faltaba la del medio, que en un censo real es **la más frecuente**: la ficha se puede
salvar, pero le falta algo. Esta historia la agrega:

```
                        ┌──validar──> VALIDADA   (aprobada, cerrada)
                        │
COMPLETADA ─────────────┼──devolver─> OBSERVADA ──corrige──> COMPLETADA ──┐
(esperando revisión)    │             (REABIERTA)                         │
                        │                  ▲                             │
                        └──anular───> ANULADA                             │
                                                                          │
                    ... y vuelve a la bandeja del supervisor  <───────────┘
```

Es la única resolución que **no cierra**: devuelve el trabajo a quien lo hizo y el
circuito puede dar otra vuelta.

Y la historia tiene dos mitades que hay que cumplir juntas, porque una sin la otra no
sirve de nada:

| Mitad | Quién | Qué |
|---|---|---|
| **Escribir** | supervisor | decir qué corregir, con un mínimo de concreción |
| **Leer** | encuestador | ver esas observaciones donde va a trabajar |

Antes de esta historia, la pantalla del encuestador ya decía *«revisa las
observaciones antes de volver a la vivienda»* y **no mostraba ninguna**: el estado
existía desde la HU-07, pero el texto de la devolución no. Era una instrucción
imposible de seguir.

---

## 2. Lo que ya estaba hecho

Casi todo el comportamiento de una encuesta devuelta **ya funcionaba**, y no por
casualidad: cada historia anterior modeló su parte sin saber quién iba a disparar la
transición.

| Pieza | Historia | Qué hace por la HU-15 |
|---|---|---|
| `OBSERVADA` en `EstadoEncuesta` | HU-07 | el estado existe y tiene color propio |
| `OBSERVADA` ∈ `ESTADOS_ABIERTOS` | HU-07 | la ficha vuelve a contar como trabajo pendiente |
| `ORDEN_POR_URGENCIA` | HU-07 | la pone **primera** en la lista del encuestador |
| `puede_registrarse()` | HU-08 | vuelve a ser editable, porque mira si está abierta |
| `cambiar_estado()` | HU-10 | borra `cerrada_en` al volver a un estado abierto |
| `revisada_por` / `revisada_en` / `comentario_revision` | HU-14 | quién resolvió, cuándo y con qué texto |
| `resolver()` | HU-14 | mueve las cuatro columnas juntas |
| `puede_resolverla()` | HU-14 | solo lo recibido, y **nadie resuelve lo propio** |
| `ESTADOS_RESUELTOS` | HU-14 | ya incluía `OBSERVADA` |

Esto no es un dato anecdótico: es la comprobación de que el modelo de estados estaba
bien puesto. **La HU-15 no tuvo que tocar ni una transición.** Solo agrega quién la
dispara, con qué texto, y cuántas veces ha pasado.

---

## 3. Tres salidas distintas

Las tres son «resolver», pasan por el mismo `resolver()` y exigen el mismo permiso.
Pero se diferencian en tres cosas, y el código lo refleja en cada una:

| | Validar | Devolver | Anular |
|---|---|---|---|
| Estado final | `VALIDADA` | `OBSERVADA` | `ANULADA` |
| ¿Cierra la ficha? | sí | **no, la reabre** | sí |
| ¿La puede editar el encuestador después? | no | **sí** | no |
| Comentario | opcional | **obligatorio** | **obligatorio** |
| Casilla de confirmación | no | **no** | **sí** |
| ¿Esa vivienda queda con datos? | sí | todavía no | **no** |
| Contador | — | `veces_devuelta` +1 | — |

Las dos filas en negrita que más cuesta defender son el comentario y la casilla, y
tienen respuestas distintas:

**Por qué devolver exige comentario y validar no.** Aprobar es el resultado esperado
de una revisión: exigir un texto por cada ficha buena produciría cientos de «ok» que
nadie va a leer. Devolver, en cambio, **es una petición**: sin decir qué corregir no
pide una corrección, solo devuelve trabajo. El encuestador abriría la ficha, no
encontraría nada evidente y la reenviaría igual. Se perdieron dos viajes y una
revisión.

**Por qué devolver NO pide casilla de confirmación y anular sí.** No es un olvido.
Anular tira el trabajo de otra persona y deja la vivienda sin datos: en la práctica es
irreversible. Devolver es la acción **esperable** de una revisión y la ficha se puede
volver a resolver después. Poner la misma barrera a las dos las igualaría, y entonces
la casilla dejaría de significar algo justo donde hace falta.

---

## 4. La restricción que cambió de nombre

La HU-14 creó esta restricción, que cubría **solo** `ANULADA`:

```python
models.CheckConstraint(
    condition=(~models.Q(estado="ANULADA") | ~models.Q(comentario_revision="")),
    name="encuesta_anulacion_con_motivo",
)
```

La HU-15 la reemplaza por esta:

```python
models.CheckConstraint(
    condition=(
        ~models.Q(estado__in=["ANULADA", "OBSERVADA"])
        | ~models.Q(comentario_revision="")
    ),
    name="encuesta_resolucion_con_motivo",
)
```

Leída en voz alta: *«o el estado no es una resolución en contra, o hay un comentario
escrito»*. `VALIDADA` queda fuera a propósito, por lo dicho arriba.

**Por qué cambia el nombre y no solo la condición.** Se podía haber conservado
`encuesta_anulacion_con_motivo` y ampliar su condición: habría funcionado igual. Se
prefirió renombrarla porque una restricción llamada «anulacion» que además gobierna
las devoluciones **miente sobre lo que comprueba**, y el nombre es lo único que se ve
cuando la base de datos rechaza una fila: el mensaje de error dice el nombre y nada
más. Un desarrollador futuro que vea `encuesta_anulacion_con_motivo` en un log
buscaría el bug en la pantalla equivocada.

Es el mismo criterio con el que la HU-10 llamó `motivo_cierre` a su campo y no
`observaciones2`: **el nombre es documentación que no se puede desactualizar sin que
alguien se dé cuenta.**

---

## 5. La migración y su paso de datos

`0008_devolucion_con_observaciones.py` hace cuatro cosas, en este orden exacto:

```python
RemoveConstraint("encuesta_anulacion_con_motivo")   # 1. fuera la vieja
AddField("veces_devuelta", default=0)               # 2. la columna nueva
AlterField("comentario_revision")                   # 3. su help_text
RunPython(rellenar_observaciones, vaciar_...)       # 4. arreglar el pasado
AddConstraint("encuesta_resolucion_con_motivo")     # 5. la nueva
```

**El paso 4 es obligatorio y el orden importa.** Hasta ahora `OBSERVADA` solo se podía
alcanzar por el admin o por el comando de demostración, y ninguno escribía
`comentario_revision` —el campo no existía cuando el estado se definió—. Esas filas
contradicen la restricción nueva: crearla sin más las rechazaría y la migración
fallaría, como ya pasó a propósito en la HU-10.

`rellenar_observaciones` usa el mismo criterio que `rellenar_motivos` en la migración
0004:

- **Si hay algo en `observaciones`, se copia.** En esas filas es el único sitio donde
  pudo quedar escrito el motivo de la devolución.
- **Si no hay nada, se escribe la constancia de que no se anotó** —«Observación no
  registrada: la encuesta se devolvió antes de que el sistema exigiera anotarla»—. No
  es una observación inventada: es la información verdadera. Un dato inventado es peor
  que un dato ausente porque después nadie puede distinguirlo.
- **`veces_devuelta` se pone en 1, no en 0.** Si estaba observada, alguien la devolvió
  al menos una vez; dejar el contador en cero afirmaría lo contrario.

Se **copia** y no se mueve: `observaciones` conserva su contenido, porque vaciarla
supondría que todo lo que había ahí era la devolución, y eso no se puede saber.

La migración es **reversible**, y el reverso está escrito con cuidado: solo borra el
comentario si coincide exactamente con lo que la ida escribió, para no destruir una
observación que alguien haya redactado de verdad después.

```bash
python manage.py migrate fichas         # aplica
python manage.py migrate fichas 0007    # revierte
python manage.py migrate fichas         # vuelve a aplicar
```

Las tres pasaron en SQLite antes de tocar PostgreSQL. En la base de desarrollo, el
paso de datos arregló **dos filas heredadas**: copió su texto desde `observaciones` y
les puso el contador en 1.

---

## 6. `devolver()`

```python
def devolver(self, usuario, observaciones):
    self.veces_devuelta = self.veces_devuelta + 1
    self.save(update_fields=["veces_devuelta"])

    return self.resolver(
        EstadoEncuesta.OBSERVADA, usuario=usuario, comentario=observaciones
    )
```

Es una resolución más —pasa por `resolver()`— pero tiene método propio por dos
razones:

1. **Reabre.** No hay código nuevo para eso: `OBSERVADA` pertenece a
   `ESTADOS_ABIERTOS`, así que `cambiar_estado()` borra `cerrada_en` solo. Lo que hace
   el método propio es **nombrar** esa diferencia, para que nadie tenga que deducirla
   leyendo tres archivos.
2. **Cuenta.** `veces_devuelta` se incrementa aquí y **en ningún otro sitio**, para que
   el número no dependa de que cada vista se acuerde de sumarlo. Si mañana la
   devolución se dispara desde una API o desde un comando, el contador sigue bien.

Lo que **no** hace: volver a validar que las observaciones no estén vacías. La
garantía está en la base de datos y en el formulario; repetirla aquí repartiría la
misma regla en tres capas sin reforzarla.

---

## 7. `veces_devuelta`

```python
DEVOLUCIONES_PARA_ALERTAR = 3

@property
def fue_devuelta(self):            return self.veces_devuelta > 0

@property
def devuelta_repetidamente(self):  return self.veces_devuelta >= self.DEVOLUCIONES_PARA_ALERTAR
```

**Por qué un contador y no una tabla de devoluciones.** Una tabla `Devolucion` con
fecha, autor y texto de cada vuelta sería más completa y también más de lo que esta
historia pide: el supervisor necesita saber *cuántas veces* y *qué dice la última*, no
reconstruir el historial. `comentario_revision` guarda la vigente y el contador guarda
el resto. El día en que haga falta el historial completo, el contador no estorba: se
deriva de la tabla nueva.

**Por qué el umbral es 3.** Dos devoluciones son parte del trabajo. A la tercera, lo
que falla probablemente no es esa casa: es que alguien **no entendió cómo se llena el
formulario**, y devolverla otra vez no lo va a arreglar. El aviso aparece justo donde
se toma la decisión —la pantalla de revisión y la de devolver— y sugiere la acción que
sí corresponde: *hablar con la persona*.

**Por qué sobrevive a la validación.** Una ficha validada que se devolvió dos veces
mantiene su contador. Que costara tres intentos es información de calidad del
operativo, y borrarla justo cuando la ficha se cierra bien perdería exactamente el
dato que sirve para formar mejor al equipo.

`fue_devuelta` (¿alguna vez?) y `necesita_correccion` (¿ahora mismo?) son preguntas
distintas y hay dos propiedades porque se usan en sitios distintos.

---

## 8. `problemas_detectados()`

```python
def problemas_detectados(self):
    """Lo que el sistema nota que falta, en frases listas para copiar."""
```

Devuelve frases como:

- `Faltan 2 personas por registrar: la familia declaró 5 y hay 3.`
- `La vivienda no está descrita: falta tipo, materialidad o servicios.`
- `No se capturó la ubicación de la vivienda.`

Y sirven para **prerrellenar** el campo de observaciones. El supervisor recibe escrito
lo que el sistema sabe contar y añade lo que solo él puede ver: que la dirección no
coincide con la foto, que el ingreso declarado no cuadra, que el nombre está mal
escrito.

**Es un borrador, no un veredicto.** Tres consecuencias de esa distinción:

1. Se pasa a `initial` y **solo en el GET**: si el formulario vuelve con un error, lo
   que el supervisor escribió sigue ahí.
2. Se puede borrar. El supervisor puede devolver por algo completamente distinto.
3. **Cuando la lista está vacía, la pantalla lo dice y advierte**: *«El sistema no
   detecta datos faltantes. Si la devuelves, explica qué encontraste al revisarla»*.
   Sin ese aviso, el silencio se leería como «no hay nada que objetar», y no es lo
   mismo: solo significa que no falta nada **contable**.

No reutiliza ni duplica la lógica de la HU-13: llama a `resumen_para_revision()`, que
es el mismo cálculo que alimenta la bandeja. Y **no es** el catálogo de alertas de
registros incompletos: eso es la HU-16, que las convertirá en reglas con umbrales
propios. Aquí solo se ahorra escribir lo evidente.

El texto concuerda en número, verbo incluido —«Falta 1 persona» / «Faltan 2
personas»—. Es un detalle, pero lo lee una persona a la que se le está pidiendo
trabajo extra, y «Faltan 1 personas» delata que nadie revisó el mensaje que se envía.
Hay una prueba para el singular, y encontró el error cuando el verbo todavía estaba
fijo en plural.

---

## 9. El formulario

`DevolverEncuestaForm` pide dos cosas:

```python
aspectos      = MultipleChoiceField(CheckboxSelectMultiple)   # 6 opciones
observaciones = CharField(Textarea, min 15 caracteres útiles)
```

**Los aspectos son una lista, no una causa única.** `AnularEncuestaForm` pide *una*
causa porque una ficha se descarta por *una* razón. Al devolver suele haber varios
problemas a la vez, y devolverla dos veces por dos cosas que se veían juntas es una
visita de más. Como en la HU-14, además permite **contar**: «qué se corrige más» es
una pregunta de calidad del operativo que un campo libre no responde sin leer
doscientos textos.

**El texto es obligatorio y con largo mínimo** (15 caracteres útiles, el mismo umbral
que `CerrarSinDatosForm` en la HU-10 y `AnularEncuestaForm` en la HU-14). Los aspectos
dicen **dónde** mirar; solo el texto dice **qué** está mal. El mensaje de error lo
explica en esos términos: *«Escribe qué hay que corregir. Quien lo lea tiene que poder
arreglarlo sin volver a preguntarte.»*

**El comentario guardado junta las dos cosas**, con el formato armado en un único
sitio —`comentario_completo()`, igual que en la HU-14— y los aspectos ordenados según
el catálogo y **no** según el orden en que se marcaron, para que dos devoluciones por
lo mismo se lean igual:

```
Corregir: Integrantes del hogar, Ubicación.

Faltan los dos hijos menores que declaró la señora y no quedó capturada la ubicación.
```

---

## 10. La mitad que faltaba

Sin esta sección, la historia no está cumplida. `encuesta_detalle.html` —la pantalla
donde el encuestador trabaja— ahora muestra:

- **quién** la devolvió y **cuándo**, con nombre y apellido, para que pueda
  preguntarle si no entiende algo;
- **las observaciones completas**, arriba, en un bloque destacado. No en una pestaña
  ni detrás de un enlace: es lo primero que hay que leer y lo único que dice qué
  hacer;
- **el aviso de reincidencia** si ya van dos o más: *«Es la 3.ª vez que se devuelve.
  Si no entiendes qué falta, pregunta antes de reenviarla.»*

Se usa `linebreaksbr` y no `linebreaks` porque el texto llega con saltos de línea —el
prerrelleno escribe una lista con guiones— y hay que respetarlos. Django escapa el
contenido **antes** de convertir los saltos, así que un comentario que contenga HTML
se muestra como texto; hay una prueba que lo comprueba con un `<script>`.

De paso se arregló un hueco que la HU-14 dejó: el encuestador tampoco veía el
comentario de una ficha **validada** ni el motivo de una **anulada**. Ahora los ve. Es
lo mínimo: en un caso es su trabajo aprobado y en el otro es su trabajo descartado.

Y no hizo falta tocar nada más para que la ficha volviera a su lista, apareciera
primera y fuera editable otra vez: todo eso estaba desde la HU-07 y la HU-10. Hay
pruebas de las tres cosas, porque «no hizo falta tocarlo» y «funciona» no son lo
mismo.

---

## 11. Vistas, URLs y templates

```
GET  /encuestas/<pk>/devolver/   -> formulario, con las observaciones prerrellenadas
POST /encuestas/<pk>/devolver/   -> devuelve y redirige a la bandeja
```

`DevolverEncuestaView` hereda `ResolverEncuestaMixin` (HU-14) y con eso obtiene gratis
el permiso `fichas.validar`, la búsqueda de la encuesta y `comprobar_resoluble()`, que
corre **en el GET y en el POST**: la dirección se puede escribir a mano, y dos
supervisores mirando la misma bandeja pueden pulsar el botón de la misma ficha con
segundos de diferencia. El segundo se encuentra con «ya está resuelta».

**Dos pasos y no un botón directo**, por lo mismo que validar y anular: un GET no debe
cambiar nada, o un `<img src="...">` incrustado en cualquier página devolvería fichas
con la sesión del supervisor. Pero aquí la pantalla intermedia gana un propósito
propio: es donde llega el prerrelleno, y es lo que evita que la devolución se quede en
«revisar» por pereza.

En `revision_encuesta.html` las tres acciones aparecen juntas, descritas **por su
consecuencia y no por su verbo**, y en orden de gravedad creciente:

> Valídala si la información está correcta, devuélvela si se puede corregir, o anúlala
> solo si la ficha no sirve y no hay nada que arreglar.

---

## 12. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0008_devolucion_con_observaciones.py
backend/templates/fichas/encuesta_devolver.html
backend/docs/HU-15_devolver_con_observaciones.md      este documento
```

### Modificados

```
backend/fichas/models.py     + veces_devuelta, + DEVOLUCIONES_PARA_ALERTAR,
                             + devolver() / fue_devuelta / devuelta_repetidamente,
                             + problemas_detectados(),
                             ~ restricción renombrada y extendida a OBSERVADA
backend/fichas/forms.py      + DevolverEncuestaForm
backend/fichas/views.py      + DevolverEncuestaView
backend/fichas/urls.py       + 1 ruta
backend/fichas/tests.py      + 80 pruebas; ajustadas 6 de historias anteriores
backend/fichas/management/commands/crear_encuestas_demo.py
                             las devueltas ahora traen observaciones y contador
backend/templates/fichas/encuesta_detalle.html    + observaciones y resolución visibles
backend/templates/fichas/revision_encuesta.html   + botón, aviso e historial
backend/README.md · README.md
```

Seis pruebas anteriores cambiaron, y el cambio dice algo: hacían
`cambiar_estado(OBSERVADA)` a secas, que ahora la base de datos no acepta. La respuesta
correcta no era añadirles el comentario a mano, sino que pasaran por `devolver()` —
único camino que produce una encuesta observada en la aplicación real—. Se agregó el
ayudante `devolver()` a `BaseEncuestaTest` para eso: **una prueba que construye a mano
un estado que el sistema no puede alcanzar comprueba algo que no existe.**

---

## 13. Pruebas

```bash
python manage.py test fichas          # 773 (HU-07 a HU-15)
python manage.py test                 # 1.319 en total
```

| Bloque | Qué comprueba |
|---|---|
| `EstadoObservadaTest` | reabre, borra `cerrada_en`, conserva `iniciada_en`, vuelve a ser editable, y la restricción cubre **las dos** resoluciones en contra |
| `ContadorDeDevolucionesTest` | suma en cada devolución, validar no lo toca, sobrevive a la validación, el umbral avisa, no admite negativos |
| `ProblemasDetectadosTest` | detecta personas / vivienda / ubicación, acumula varios, singular y plural, sin hogar no habla de personas que faltan |
| `DevolverFormTest` | exige aspecto y texto, rechaza «revisar», ordena los aspectos, prerrellena, **no pisa lo que el supervisor escribió**, no pide confirmación |
| `DevolverEncuestaVistaTest` | permiso, no la propia, no dos veces seguidas, GET no devuelve, guarda las cuatro columnas, no borra el hogar, avisa de reincidencia |
| `ObservacionesParaElEncuestadorTest` | **lee** el texto y quién lo escribió, la ficha vuelve primera a su lista, la puede editar y reenviar, y el HTML del comentario no se interpreta |
| `DevolucionEnLaRevisionTest` | tres salidas juntas, historial, sale de la cola, filtros y panel |
| `IntegracionHU15Test` | devolver → leer → corregir → reenviar → validar, con el contador intacto al final |

Dos pruebas encontraron errores reales durante el desarrollo: la del singular
(«Faltan 1 persona») y la del escenario base duplicado en el hogar.

---

## 14. Verificación manual

Con `runserver` y las cuentas de demostración, sobre PostgreSQL:

| Paso | Resultado |
|---|---|
| `GET /encuestas/23/devolver/` como supervisor | **200**, con `- Faltan 2 personas por registrar: la familia declaró 6 y hay 4.` ya escrito en el textarea |
| `POST` sin aspectos y con «ver» | **200** con los dos errores: «Este campo es obligatorio» y «Escribe qué hay que corregir…» |
| `POST` completo | **302 → /encuestas/revision/**; estado `OBSERVADA`, `veces_devuelta=1`, `cerrada_en=None`, `revisada_por=supervisor@opso.cl`, 4 integrantes intactos, `puede_registrarse=True` |
| La misma ficha como encuestador | **200**, muestra «Carlos Pérez devolvió esta ficha el 04-08-2026», el bloque `Corregir: Integrantes del hogar, Ubicación.` y el texto completo |
| Su lista y `GET /encuestas/23/hogar/` | la ficha aparece como **Observada** y el formulario responde **200**: la puede corregir |
| Ficha sembrada con 3 devoluciones | muestra «3.ª vez» al encuestador y «hablar con…» al supervisor |
| `GET /encuestas/22/revisar/` | las **tres** direcciones presentes: `/validar/`, `/devolver/`, `/anular/` |
| Una ya devuelta | ya **no** ofrece devolver, y muestra «Devoluciones · 1 vez» |

---

## 15. Explicación para la defensa

**En una frase:** devolver una encuesta sin decir qué corregir no pide una corrección,
solo devuelve trabajo; toda la historia está construida para que eso no pueda pasar.

**Las tres cosas que conviene poder defender:**

1. **La historia tiene dos mitades y las dos son obligatorias.** Escribir las
   observaciones y **leerlas**. La pantalla del encuestador ya decía «revisa las
   observaciones» sin mostrar ninguna: era una instrucción imposible de seguir, y
   arreglarlo es la mitad de esta historia.
2. **La regla vive en la base de datos, no en el formulario.**
   `encuesta_resolucion_con_motivo` impide una devolución sin texto aunque se cree por
   el admin, por un comando o por un script. Extenderla obligó a arreglar el pasado
   con un paso de datos, que es exactamente el trabajo que una restricción honesta
   provoca.
3. **No hubo que tocar ni una transición de estado.** `OBSERVADA` ya reabría la ficha,
   ya la ponía primera y ya la volvía editable, porque la HU-07 y la HU-10 lo
   modelaron sin saber quién lo dispararía. Es la prueba de que el modelo de estados
   estaba bien puesto.

**Lo que cuesta el diseño anterior:** seis pruebas dejaron de pasar porque construían
`OBSERVADA` a mano. Es una buena señal: significa que el estado ya no se puede
falsificar. Se arreglaron pasando por `devolver()`, no relajando la restricción.

---

## 16. Posibles preguntas del profesor

**¿Cuál es la diferencia entre devolver y anular?**
Devolver **reabre** la encuesta: vuelve a la lista del encuestador, editable, y cuando
la corrija reaparecerá en la bandeja. Anular la cierra y esa vivienda queda sin datos.
Son la resolución recuperable y la irrecuperable.

**¿Por qué devolver exige comentario si validar no?**
Porque validar es el resultado esperado y exigir un texto por cada ficha buena daría
cientos de «ok». Devolver es una petición: sin decir qué corregir, el encuestador
abriría la ficha, no vería nada evidente y la reenviaría igual.

**¿Por qué anular pide una casilla de confirmación y devolver no?**
Porque anular tira el trabajo de otra persona y en la práctica es irreversible.
Devolver es esperable y reversible. Si las dos pidieran lo mismo, la casilla dejaría
de significar algo donde de verdad importa.

**¿Por qué renombraste la restricción en vez de solo ampliar su condición?**
Porque el nombre es lo único que aparece cuando la base de datos rechaza una fila. Una
restricción llamada «anulacion» que además gobierna las devoluciones mandaría a buscar
el error a la pantalla equivocada.

**¿Por qué la migración necesita un paso de datos?**
Porque ya había encuestas observadas sin comentario: el estado existe desde la HU-07 y
el campo desde la HU-14. Crear la restricción sin arreglarlas la habría hecho fallar.
El paso copia lo que hubiera en `observaciones` y, si no hay nada, deja constancia de
que no se anotó. No inventa una observación: un dato inventado es peor que uno
ausente.

**¿De dónde salen las observaciones prerrellenadas? ¿No es el sistema decidiendo?**
No: es un borrador editable. `problemas_detectados()` reutiliza el mismo cálculo que
alimenta la bandeja desde la HU-13 y escribe lo que sabe contar —personas que faltan,
vivienda sin describir, ubicación ausente—. El supervisor lo corrige, lo borra o lo
completa. Y cuando no detecta nada, la pantalla advierte que el silencio no significa
«nada que objetar».

**¿Y si el supervisor borra el prerrelleno y escribe «revisar»?**
El formulario lo rechaza: pide al menos 15 caracteres útiles y al menos un aspecto
marcado. No garantiza calidad, pero sí que haya una frase y un lugar donde mirar.

**¿Por qué un contador y no una tabla con el historial de devoluciones?**
Porque la historia pide saber cuántas veces y qué dice la última, no reconstruir el
historial. El contador cuesta una columna y responde eso. Si mañana hace falta el
historial completo, se agrega la tabla y el contador se deriva de ella.

**¿Por qué el umbral son 3 devoluciones?**
Porque dos son parte del trabajo. A la tercera, lo que falla probablemente no es esa
ficha sino la formación de quien la levanta, y el aviso sugiere hablar con la persona
en vez de devolverla otra vez.

**¿Se pierde algo de lo que el encuestador ya había registrado?**
Nada. La devolución solo cambia el estado y escribe el comentario: hogar, integrantes,
fotografías y ubicación siguen ahí. Hay una prueba que lo comprueba y se verificó
también sobre la base real.

**¿Puede el encuestador devolver o marcar como revisada su propia ficha?**
No. Devolver exige `fichas.validar`, que un encuestador no tiene, y además
`puede_resolverla()` impide resolver la propia encuesta incluso a un supervisor o al
administrador.

**¿Cuántas veces puede ir y venir una encuesta?**
Sin límite técnico, y es deliberado: cortarlo dejaría fichas atascadas sin salida. El
límite es de gestión, y para eso está el aviso de reincidencia.

---

## 17. Conclusión técnica

La HU-15 agrega **un campo, un método, un formulario, una pantalla y ningún estado ni
permiso nuevo**.

Su valor técnico está en tres cosas:

1. **Cierra el circuito.** La revisión pasa de tener dos salidas que terminan a tener
   tres, y la nueva es la única que devuelve el trabajo a quien puede arreglarlo. El
   camino completo —devolver, leer, corregir, reenviar, validar— está cubierto por una
   prueba de integración de punta a punta.
2. **Cumple la historia entera, no solo la mitad visible.** Lo difícil no era el botón
   del supervisor: era que el encuestador **leyera** lo que se le pide, donde trabaja,
   sin buscarlo. Una devolución que no se lee es trabajo devuelto sin instrucciones.
3. **Confirma el modelo de estados.** No hubo que tocar ninguna transición: la HU-07 y
   la HU-10 ya habían modelado que `OBSERVADA` reabre. Cuando agregar una función
   nueva no obliga a reescribir lo anterior, es que lo anterior estaba bien.

Lo que queda del sprint: las **alertas de registros incompletos** (HU-16), que
convertirán en reglas con umbrales las señales que la HU-13 dejó descriptivas y que
esta historia usa como borrador.
