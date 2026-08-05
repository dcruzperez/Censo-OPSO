# HU-10 · Borradores y cierre de la encuesta

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero guardar borradores para continuar posteriormente una encuesta incompleta.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **85 pruebas automáticas** propias (**986** en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no agrega ni un permiso** y **cierra el ciclo de vida** que la
> HU-07 definió: hasta ahora ninguna pantalla producía `COMPLETADA`, así que todo
> lo que el encuestador tocaba quedaba en borrador para siempre y el supervisor no
> recibía nada. Reutiliza `fichas.crear` y `fichas.editar` de la HU-04, los siete
> estados de la HU-07 y el `CASE` de SQL que aquella estrenó.

---

## Índice

1. [Explicación inicial: ¿qué falta si todo ya se guarda?](#1-explicación-inicial)
2. [El ciclo de vida, por fin completo](#2-el-ciclo-de-vida)
3. [Las tres columnas nuevas](#3-las-tres-columnas-nuevas)
4. [La migración que falló a la primera](#4-la-migración-que-falló)
5. [`pasos_pendientes()`: no decir «no puedes»](#5-pasos-pendientes)
6. [La visita anotada](#6-la-visita-anotada)
7. [Cerrar sin levantar, con motivo obligatorio](#7-cerrar-sin-levantar)
8. [Un ModelForm que no podía serlo](#8-un-modelform-que-no-podía-serlo)
9. [El error que encontró una prueba: `update_fields`](#9-el-error-que-encontró-una-prueba)
10. [Vistas, URLs y templates](#10-vistas-urls-y-templates)
11. [Seguridad](#11-seguridad)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 La pregunta incómoda

Desde la HU-08, **cada pantalla guarda lo que se escribió en cuanto se pulsa su
botón**. No hay ningún dato del censo que se pierda al salir de la aplicación.
Entonces, ¿qué implementa una historia que pide «guardar borradores»?

Dos cosas que faltaban de verdad:

**a) Poder CONTINUAR, que no es lo mismo que tener los datos guardados.** Lo que se
pierde al día siguiente no son los campos: es **por dónde iba la conversación**.
«Falta el módulo de ingresos y la señora vuelve del trabajo a las 19:00» vive hoy
en la cabeza del encuestador. Una encuesta a medias sin esa nota hay que
reconstruirla de memoria, y cuando pasan cuatro días se vuelve a empezar —con la
familia respondiendo dos veces las mismas preguntas—.

**b) Poder TERMINAR.** El estado `COMPLETADA` estaba definido desde la HU-07 y
**ninguna pantalla lo producía**. Todo lo que el encuestador tocaba quedaba en
`BORRADOR` para siempre y el supervisor no recibía nada que validar. Un borrador
solo tiene sentido si existe la versión final.

### 1.2 Lo que aporta, en una tabla

| Antes de la HU-10 | Después |
|---|---|
| «Ya guardé los datos… ¿y por dónde iba?» | la nota de avance, a la vista al abrir la ficha |
| Volver a una casa se recuerda o se olvida | fecha de próxima visita, con aviso cuando vence |
| Nada llegaba nunca al supervisor | `COMPLETADA` y el envío a revisión |
| «No puedes terminar» (si acaso) | la lista de lo que falta, con un enlace a cada paso |
| Una puerta que no se pudo quedaba pendiente para siempre | cierre con motivo obligatorio |

---

## 2. El ciclo de vida

```
PENDIENTE ──registra algo──> BORRADOR ──completar──> COMPLETADA ──> (supervisor)
    │                            │
    └────────── cerrar ──────────┴──> NO_UBICADA / RECHAZADA
```

Con esta historia, **el camino del encuestador está entero**. Lo que sigue faltando
es la parte del supervisor: `VALIDADA` y `OBSERVADA`, que produce el permiso
`fichas.validar` en su propia historia.

### 2.1 El encuestador no puede reabrir lo que envió

Y es deliberado. Reabrir una encuesta ya enviada permitiría cambiar los datos que
el supervisor está mirando en ese momento, o los que ya aprobó. **El camino de
vuelta existe y es del supervisor**: devolverla como `OBSERVADA`, que la convierte
otra vez en trabajo abierto.

No hizo falta escribir ninguna regla nueva para esto: `puede_registrarse()`, de la
HU-08, ya rechaza cualquier escritura sobre una encuesta cerrada. Hay una prueba de
que intentarlo redirige a la ficha.

### 2.2 Dos transiciones automáticas, y una que NO lo es

| Situación | Qué pasa |
|---|---|
| Se deja una nota en una encuesta `PENDIENTE` | pasa a `BORRADOR`: dejar una nota implica haber estado ahí, y «pendiente» significa «sin visitar» |
| Se deja una nota en una encuesta `OBSERVADA` | **sigue observada**: bajarla a borrador borraría de la pantalla el aviso más urgente que tiene el encuestador |
| Se registra el hogar o una persona | ya pasaba a `BORRADOR` desde la HU-08 |

---

## 3. Las tres columnas nuevas

| Columna | Para qué |
|---|---|
| `nota_avance` | la nota que uno se deja: «por dónde iba» |
| `proxima_visita` | cuándo conviene volver |
| `motivo_cierre` | por qué no se pudo levantar (obligatorio en dos estados) |

### 3.1 `nota_avance` resuelve una ambigüedad de la HU-07

La HU-07 declaró `observaciones` como «indicaciones del supervisor **o** notas del
propio encuestador». Esa «o» era una ambigüedad, y se paga en cuanto los dos
escriben en el mismo campo: **la nota que el encuestador se deja a sí mismo pisaría
las instrucciones que recibió, o al revés**.

La HU-10 parte la responsabilidad:

| Campo | Autor | Contenido |
|---|---|---|
| `observaciones` | quien encarga la encuesta | «pasar después de las 19:00» |
| `nota_avance` | el encuestador | «falta el módulo de ingresos» |

**Dos autores, dos propósitos, dos columnas.** La migración no reparte el contenido
existente: nadie puede saber hoy cuál de las dos cosas escribió cada quien en las
filas que ya están, y adivinarlo sería inventar autoría.

---

## 4. La migración que falló

`fichas/0004_borradores_y_cierre.py` **falló al primer intento**, y conviene contar
por qué porque la corrección es la parte interesante:

```
django.db.utils.IntegrityError: CHECK constraint failed: encuesta_cierre_con_motivo
```

La causa: la HU-07 permitía cerrar una encuesta como no ubicada o rechazada **sin
ningún campo donde escribir por qué**, así que el motivo —cuando se escribió— acabó
en `observaciones`. Al crear la restricción, esas filas la contradecían.

La corrección es un paso de datos (`rellenar_motivos`) **antes** de crear la
restricción, con dos casos y ninguno inventa nada:

- **Si hay algo en `observaciones`, se copia.** Es el motivo real, guardado en el
  único sitio que había.
- **Si no hay nada, se escribe la constancia de que no se anotó.** No es un motivo
  inventado: es la información verdadera. Mismo criterio que la migración 0002 al
  dejar «sin describir» las viviendas heredadas — **un dato inventado es peor que un
  dato ausente, porque nadie puede distinguirlo después**.

Se **copia** y no se mueve: `observaciones` conserva su contenido, porque vaciarla
supondría que todo lo que había ahí era el motivo del cierre, y no se puede saber.

> Que la restricción se cree al final tiene una consecuencia buena: en cualquier
> base con filas que contradigan la regla, **la migración falla en vez de
> aceptarlas**. Fallar ruidosamente obliga a mirar esas filas en vez de heredar el
> problema — que es exactamente lo que pasó aquí.

**Verificada de ida y vuelta**: aplicada, revertida con `migrate fichas 0003` y
reaplicada, con los motivos intactos.

---

## 5. `pasos_pendientes()`

Es el corazón de la historia, y lo que la convierte en algo más que un botón.

```python
def pasos_pendientes(self):
    """Lo que falta para poder dar la encuesta por terminada."""
```

Devuelve una **lista de diccionarios con `texto` y `ruta`**, no una lista de textos
ni un booleano. Es deliberado:

> «No puedes completar la encuesta» obliga a adivinar qué falta y a buscarlo
> pantalla por pantalla. «Falta describir la vivienda → **[Ir]**» se resuelve en un
> toque.

Es el mismo criterio con que la HU-05 devuelve el **motivo** en
`puede_desactivarse()` en vez de un booleano suelto.

### 5.1 Los cuatro requisitos

| Orden | Requisito | De qué historia viene |
|---|---|---|
| 1 | la vivienda está descrita | HU-08 |
| 2 | el hogar está registrado | HU-08 |
| 3 | tiene jefe de hogar identificado | HU-09 |
| 4 | están todas las personas declaradas | HU-08 + HU-09 |

**El orden de la lista es el orden en que hay que hacer las cosas**, no el orden en
que se comprobaron. Así el primer elemento es siempre el siguiente paso.

**Si falta el hogar, se corta ahí** y no se listan los pasos de personas: tres
avisos que dicen lo mismo no ayudan a nadie.

Es también la primera pregunta del proyecto que **ninguna tabla puede responder
sola**: depende de la vivienda, del hogar y de las personas. Por eso vive en
`Encuesta`, que es lo único que conoce las tres.

---

## 6. La visita anotada

`proxima_visita` convierte el listado en una agenda: al mirarlo por la mañana se ve
a qué puertas hay que volver hoy **sin abrir cada ficha**.

- **No puede ser una fecha pasada.** Una fecha pasada no es una cita, es un olvido:
  el listado la mostraría como vencida el mismo día en que se escribió.
- **Hoy sí se acepta**, que es el caso real de «vuelvo esta tarde».
- **Una visita vencida se avisa arriba del listado**, junto al aviso de fichas
  devueltas, que es el otro caso donde el tiempo corre en contra.
- **Al cerrar la encuesta se borra**: ya no espera a nadie, y seguir avisando sería
  ruido.

El recuento de vencidas se calcula **en la misma consulta agregada** que los demás
contadores, con `Count(filter=...)`, y no recorriendo las encuestas en Python con
`visita_pendiente_vencida`. La propiedad del modelo sigue existiendo para una
encuesta suelta; para el recuento manda PostgreSQL.

---

## 7. Cerrar sin levantar

La HU-07 definió `NO_UBICADA` y `RECHAZADA` argumentando que **son resultados, no
fracasos**: sin ellos, una dirección que no existe quedaría pendiente para siempre y
el avance del operativo mentiría hacia abajo.

Lo que aquella historia no tenía era **dónde escribir el motivo**. Esta lo agrega
con una restricción que lo exige:

```sql
CHECK (estado NOT IN ('NO_UBICADA','RECHAZADA') OR motivo_cierre <> '')
```

Sin ella, una zona podría acumular veinte encuestas cerradas sin que nadie
distinga **«la dirección no existe»** de **«pasé y no había nadie»**, que exigen
decisiones opuestas del supervisor.

### 7.1 El formulario exige más que la restricción

La restricción solo pide que no esté vacío, así que un punto la satisfaría. El
formulario exige **15 caracteres**, porque el motivo tiene un lector concreto: el
supervisor que decide si manda a otra persona a esa dirección. «x» no le sirve para
decidir; «la dirección no existe, el pasaje llega hasta el 40» sí.

### 7.2 Se puede cerrar en cualquier punto, incluso sin nada registrado

Es el caso más frecuente —se llega, no hay nadie, se cierra— y exigir el hogar
registrado obligaría a **inventar una familia para poder decir que no se encontró a
ninguna**.

Si la encuesta **sí** tenía datos, la pantalla avisa de que se conservan y la ficha
queda marcada como no levantada. Puede ser correcto: la familia se arrepintió a
mitad de la encuesta.

---

## 8. Un ModelForm que no podía serlo

`CerrarSinDatosForm` empezó siendo un `ModelForm` con `estado` y `motivo_cierre`, y
**no funcionó**. Vale la pena contarlo porque la razón es una lección de diseño, no
un detalle de Django:

```
ValidationError: {'cerrada_en': ['Una encuesta en estado «No ubicada» tiene que
tener fecha de cierre.']}
```

Un ModelForm con `estado` entre sus campos ejecuta `Encuesta.clean()` al validar,
**con el estado nuevo ya puesto y las fechas todavía sin mover**. La validación de
coherencia de la HU-07 rechaza esa combinación, y con razón: la fila estaría a
medias.

El diagnóstico correcto no es «desactivar la validación», es que **este formulario
no edita campos: pide una TRANSICIÓN**, y eso es otra cosa. Se reescribió como
`Form` normal, y las tres columnas las mueve `cambiar_estado()` junto y en la vista.

Es el mismo razonamiento que llevó a que `AsignarSectorForm` (HU-06) y
`PermisosRolForm` (HU-04) fueran `Form` y no `ModelForm`: **cuando lo que se envía
no es «el contenido de un objeto», el ModelForm estorba en vez de ayudar.**

---

## 9. El error que encontró una prueba

Una prueba de la HU-07 —`test_no_ubicada_desde_pendiente_tambien_marca_el_inicio`—
empezó a fallar con la restricción nueva, y al arreglarla apareció un **error real
en `cambiar_estado()`**:

```python
self.save(update_fields=["estado", "iniciada_en", "cerrada_en", "actualizada_en"])
```

Quien escribía `encuesta.motivo_cierre = "..."` y llamaba después a
`cambiar_estado()` veía cómo la base rechazaba la fila **por falta de motivo… con
el motivo delante**, puesto en el objeto pero nunca guardado: `update_fields`
descarta en silencio cualquier cambio que no esté nombrado.

La corrección es una línea y una regla que conviene recordar:

> **Si una columna participa en la misma restricción que el estado, tiene que
> viajar con él.**

`motivo_cierre` entró en `update_fields`. Ahora la lista es exactamente el conjunto
de columnas que gobiernan las restricciones de coherencia de la tabla.

---

## 10. Vistas, URLs y templates

| URL | Qué hace |
|---|---|
| `/encuestas/<pk>/borrador/` | guarda la nota y la próxima visita |
| `/encuestas/<pk>/completar/` | lista de comprobación y envío a revisión |
| `/encuestas/<pk>/cerrar/` | cierra sin levantar, con motivo |

`EncuestaPropiaMixin` centraliza «la encuesta es mía y admite cambios». A
diferencia del mixin de la HU-09, **no exige que el hogar exista**: se puede dejar
una nota —o cerrar por no ubicada— en una encuesta a la que todavía no se le
registró nada.

| Plantilla | Detalle |
|---|---|
| `fichas/borrador_form.html` | dice explícitamente que **lo ya escrito está guardado**, para deshacer el malentendido |
| `fichas/encuesta_completar.html` | dos caras: la lista de lo que falta, o el resumen antes de enviar |
| `fichas/encuesta_cerrar.html` | radios en vez de desplegable: dos opciones se leen a la vez |
| `fichas/_pasos_pendientes.html` | fragmento reutilizado por las tres pantallas |

**El fragmento de pasos pendientes es un fragmento y no HTML repetido** porque
aparece en tres pantallas y en las tres tiene que decir lo mismo: escrito tres
veces, bastaría con agregar un quinto requisito para que dos pantallas lo pidieran y
la tercera dijera que ya está todo listo.

**La pantalla de terminar muestra un resumen** de la casa, el hogar y las personas
antes de enviar. No es decorativo: es la última oportunidad de detectar un dato mal
escrito, porque después el encuestador ya no puede modificarlo.

---

## 11. Seguridad

- **Séptima historia seguida sin agregar permisos.** `fichas.crear` y
  `fichas.editar`, de la HU-04, concedidos solo al rol Censista: un supervisor no
  puede completar ni cerrar encuestas.
- **Solo encuestas propias**, ni siquiera con `fichas.ver_todas`: completar la
  encuesta de otro sería firmar su trabajo.
- **Todo se comprueba en GET y en POST.** Hay pruebas de POST directo para cada
  caso: completar con pasos pendientes, cerrar sin motivo, escribir en una encuesta
  validada, y en un operativo cerrado.
- **Ocultar el botón no es una validación.** La pantalla de terminar esconde el
  botón cuando falta algo **y** el POST lo rechaza igual.

---

## 12. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0004_borradores_y_cierre.py    con paso de datos
backend/templates/fichas/borrador_form.html
backend/templates/fichas/encuesta_completar.html
backend/templates/fichas/encuesta_cerrar.html
backend/templates/fichas/_pasos_pendientes.html
backend/docs/HU-10_borradores_y_cierre.md                este documento
```

### Modificados

```
backend/fichas/models.py     + 3 columnas, + ESTADOS_SIN_LEVANTAR, + restricción,
                             + pasos_pendientes() / puede_completarse /
                               visita_pendiente_vencida, corrección de update_fields
backend/fichas/forms.py      + BorradorForm, + CerrarSinDatosForm
backend/fichas/views.py      + 3 vistas y su mixin; + contador de visitas vencidas
backend/fichas/urls.py       + 3 rutas
backend/fichas/tests.py      + 85 pruebas
backend/fichas/management/commands/crear_encuestas_demo.py  notas, visitas y motivos
backend/templates/fichas/encuesta_detalle.html   + nota, motivo y las tres salidas
backend/templates/fichas/mis_encuestas.html      + aviso y fecha de visita
backend/README.md · README.md
```

---

## 13. Pruebas

```bash
python manage.py test fichas          # 440 (HU-07 a HU-10)
python manage.py test                 # 986 en total
```

| Bloque | Qué comprueba |
|---|---|
| `PasosPendientesTest` | los cuatro requisitos, el corte cuando falta el hogar, que cada paso tiene ruta válida |
| `VisitaVencidaTest` | futura no, hoy sí, pasada sí, cerrada no |
| `MotivoDeCierreTest` | la restricción en los dos estados, y que los otros cinco no la sufren |
| `BorradorFormTest` | campos opcionales, fecha pasada rechazada, hoy aceptado |
| `CerrarSinDatosFormTest` | solo dos estados ofrecidos, motivo obligatorio y legible |
| `GuardarBorradorTest` | pendiente→borrador, observada sigue observada, 404 ajena |
| `CompletarEncuestaTest` | POST rechazado con pasos pendientes, resumen, observada sí se puede |
| `CerrarSinDatosTest` | los dos cierres, fechas, borra la visita, conserva el hogar |
| `BorradorEnLasPantallasTest` | nota y motivo en la ficha, contador de vencidas en el listado |
| `IntegracionHU10Test` | recorrido completo del ciclo de vida, y el de una puerta que no se pudo |

---

## 14. Explicación para la defensa

**En una frase:** la historia parecía resuelta —todo se guardaba ya— y lo que
faltaba era poder **continuar** y poder **terminar**.

**Las tres cosas que conviene poder defender:**

1. **`pasos_pendientes()` devuelve rutas, no un booleano.** Es lo que convierte
   «no puedes terminar» en «falta esto → [Ir]». Y es la primera pregunta del
   proyecto que ninguna tabla puede responder sola.
2. **Cerrar sin levantar exige un motivo, y lo garantiza la base de datos.** Sin
   él, «la dirección no existe» y «pasé y no había nadie» serían indistinguibles, y
   exigen decisiones opuestas del supervisor.
3. **La migración falló a la primera y eso fue lo correcto.** La restricción se crea
   al final, así que los datos incoherentes que heredaba de la HU-07 la hicieron
   fallar en vez de pasar inadvertidos. El paso de datos que lo arregla no inventa
   ningún motivo.

**Lo que demuestra el proceso:** dos errores reales los encontraron las pruebas y la
migración —el `ModelForm` que no podía validar una transición y el `update_fields`
que descartaba el motivo en silencio—. Los dos están documentados en el código
donde ocurrieron.

---

## 15. Posibles preguntas del profesor

**Si todo se guardaba ya, ¿qué hace esta historia?**
Dos cosas: permite continuar —la nota de «por dónde iba» y la fecha de vuelta, que
antes vivían en la memoria del encuestador— y permite terminar, porque `COMPLETADA`
estaba definida desde la HU-07 y ninguna pantalla la producía.

**¿Por qué no puede el encuestador reabrir una encuesta enviada?**
Porque permitiría cambiar los datos que el supervisor está revisando o ya aprobó. El
camino de vuelta es suyo: devolverla como observada.

**¿Por qué la nota no va en el campo `observaciones` que ya existía?**
Porque ese campo lo escribe quien encarga la encuesta y la nota la escribe quien la
levanta. Con un solo campo, uno pisa al otro. La HU-07 lo dejó ambiguo y esta
historia parte la responsabilidad.

**¿Por qué el motivo del cierre lo exige la base de datos y no solo el formulario?**
Porque el formulario protege a la persona y la restricción protege al dato: una
importación o un script no pasan por el formulario. El formulario además exige que
sea legible, que es una regla distinta.

**¿No es raro que la migración fallara?**
Fue lo correcto. La restricción se crea después de las columnas, así que los datos
heredados que la contradecían la hicieron fallar en vez de colarse. Se resolvió con
un paso de datos que copia el motivo desde donde estaba y, cuando no había ninguno,
deja constancia de que no se anotó.

**¿Por qué una fecha de visita pasada no se acepta?**
Porque el listado la mostraría como vencida el mismo día en que se escribió. Se
anota cuándo se va a volver, no cuándo se estuvo. Hoy sí se acepta: «vuelvo esta
tarde» es un caso real.

**¿Qué pasa con los datos si se cierra una encuesta que ya tenía información?**
Se conservan y la ficha queda marcada como no levantada. La pantalla avisa. Puede
ser correcto: la familia se arrepintió a mitad de la encuesta.

---

## 16. Conclusión técnica

La HU-10 agrega **tres columnas, una restricción, tres pantallas y ningún permiso**,
y cierra el ciclo de vida que la HU-07 había definido tres historias antes.

Su valor técnico está en tres cosas:

1. **Distingue «guardado» de «continuable».** El dato ya estaba a salvo; lo que
   faltaba era el contexto para retomar el trabajo sin repetirlo.
2. **Convierte una regla en una lista accionable.** `pasos_pendientes()` no dice si
   se puede: dice qué falta y dónde arreglarlo.
3. **Deja documentados dos errores reales y su causa**, en el código donde
   ocurrieron: la transición que no cabe en un ModelForm y el `update_fields` que
   descarta cambios en silencio.

Lo que queda del sprint son las dos últimas historias, y ninguna necesita cambiar
el modelo existente: la **ubicación GPS** (HU-11) y las **fotografías** (HU-12),
que cuelgan de `Vivienda`.
