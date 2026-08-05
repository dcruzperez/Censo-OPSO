# HU-14 · Aprobar o anular encuestas

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor, quiero aprobar o rechazar encuestas para asegurar la calidad del censo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **66 pruebas automáticas** propias (**1.239** en total en el proyecto → `python manage.py test` → OK)

> Segunda historia del sprint de supervisión. **No agrega ni un permiso**: usa
> `fichas.validar`, que la HU-04 sembró con esta descripción cuando no existía
> ninguna pantalla de fichas —«Revisar el trabajo de un censista y aprobarlo o
> devolverlo con observaciones. Es el control de calidad del censo»—. Agrega el
> **octavo estado** del ciclo de vida y tres columnas de resolución.

> ⚠️ **Actualización de la HU-15.** La restricción descrita en la sección 6.1 ya no se
> llama `encuesta_anulacion_con_motivo`: la historia siguiente la reemplazó por
> `encuesta_resolucion_con_motivo`, que exige comentario tanto al **anular** como al
> **devolver con observaciones**, y el cambio está explicado en
> [`HU-15_devolver_con_observaciones.md`](HU-15_devolver_con_observaciones.md), sección
> 4. Lo que comprueba para `ANULADA` es idéntico y hay una prueba que lo garantiza;
> solo cambió el nombre, porque el anterior habría mentido sobre su alcance. Todo lo
> demás de esta historia sigue vigente tal cual, incluida la tercera salida que aquí
> se anuncia como pendiente: ya está implementada.

> **Cifras de pruebas.** Las de este documento son las del momento en que se cerró la
> historia (66 propias, 1.239 en total). Con la HU-15 el proyecto va en **1.319**.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [«Rechazar» se llama ANULADA, y por qué](#2-por-qué-anulada)
3. [Anular no es devolver](#3-anular-no-es-devolver)
4. [Las tres columnas de la resolución](#4-las-tres-columnas)
5. [Quien levanta no valida](#5-quien-levanta-no-valida)
6. [Las dos restricciones que hubo que reescribir](#6-las-restricciones-reescritas)
7. [`resolver()`: el único camino correcto](#7-resolver)
8. [Los formularios: uno pide poco y el otro mucho](#8-los-formularios)
9. [Lo que NO hace anular](#9-lo-que-no-hace-anular)
10. [Vistas, URLs y templates](#10-vistas-urls-y-templates)
11. [Archivos creados y modificados](#11-archivos-creados-y-modificados)
12. [Pruebas](#12-pruebas)
13. [Explicación para la defensa](#13-explicación-para-la-defensa)
14. [Posibles preguntas del profesor](#14-posibles-preguntas-del-profesor)
15. [Conclusión técnica](#15-conclusión-técnica)

---

## 1. Explicación inicial

La HU-13 construyó la mitad de **lectura** de la supervisión: una cola ordenada y una
pantalla donde ver la encuesta completa. Lo que faltaba era poder **decidir**.

Con esta historia, una encuesta que llega a la bandeja tiene por fin salida:

```
                        ┌──validar──> VALIDADA   (aprobada, cerrada)
COMPLETADA ─────────────┤
(esperando revisión)    └──anular───> ANULADA    (descartada, cerrada)
```

Falta la tercera salida —**devolver con observaciones**, que reabre la encuesta— y es
la HU-15.

---

## 2. Por qué ANULADA

La historia dice «rechazar» y el estado se llama **ANULADA**. Es una decisión
consciente, no una traducción libre:

> **`RECHAZADA` ya existe desde la HU-07 y significa otra cosa: LA FAMILIA rechazó
> participar.**

Son dos hechos opuestos —uno es una decisión de la familia y el otro del
supervisor— y confundirlos arruinaría cualquier lectura del censo:

| Si compartieran nombre | Se perdería la diferencia entre… |
|---|---|
| «40 rechazadas» | 40 hogares no quisieron participar |
| | 40 fichas estaban mal hechas |

La primera situación exige insistir, cambiar de horario o aceptar la negativa; la
segunda exige revisar el trabajo de un encuestador. **Reutilizar el nombre habría
sido más cómodo y menos cierto.**

Hay una prueba que fija esa distinción para que no se pierda:
`test_anulada_no_es_lo_mismo_que_rechazada`.

---

## 3. Anular no es devolver

Es la otra confusión posible, y esta ocurre en la cabeza de quien pulsa el botón:

| | **Anular** (HU-14) | **Devolver con observaciones** (HU-15) |
|---|---|---|
| Estado | `ANULADA` | `OBSERVADA` |
| ¿Se corrige? | **no**, se cierra | sí, vuelve al encuestador |
| ¿Es trabajo abierto? | no | **sí** |
| La vivienda queda | **sin datos en el censo** | pendiente de corrección |
| Cuándo se usa | duplicada, dirección equivocada, datos no creíbles | falta un dato, hay algo que arreglar |

La pantalla de anular lo dice **arriba y en rojo**, antes del formulario, con un
enlace a la alternativa. No es decoración: anular tira el trabajo de otra persona y
deja una casa sin contar.

---

## 4. Las tres columnas

```python
revisada_por         # quién resolvió
revisada_en          # cuándo
comentario_revision  # qué dejó escrito
```

### 4.1 Por qué tres columnas y no un modelo aparte

Es la razón **contraria** a la que llevó a crear `AsignacionSector` en la HU-06.
Allí se necesitaba una tabla porque una asignación **tiene historia**: la misma
persona entra y sale de un sector varias veces, y cada paso importa.

Aquí no. Una encuesta se resuelve **una vez**: se valida, se anula o se devuelve. Si
vuelve devuelta y se vuelve a resolver, lo que interesa es la resolución **vigente**;
la anterior ya cumplió su función haciendo que el encuestador corrigiera. Un modelo
con historial guardaría filas que nadie consulta.

### 4.2 Por qué no `RegistroAuditoria`

La bitácora de la HU-03 registra acciones **administrativas** sobre cuentas, roles y
territorio. Una resolución no es eso, y además:

> La resolución no es solo un hecho auditable: es un **dato que se consulta a
> diario** —el encuestador lee por qué le devolvieron su ficha— y eso no se resuelve
> leyendo una bitácora.

Es el mismo argumento con el que la HU-06 justificó su tabla propia, aplicado aquí a
tres columnas.

### 4.3 `ESTADOS_RESUELTOS`

Un grupo nuevo, y **no rompe la partición** abierto/cerrado de la HU-07:

```python
ESTADOS_RESUELTOS = (VALIDADA, OBSERVADA, ANULADA)
```

Es un corte **transversal**: `VALIDADA` y `ANULADA` son cerradas, `OBSERVADA` es
abierta. Lo que comparten es otra cosa —**las produce quien revisa, no quien
levanta**— y por eso las tres registran `revisada_por` y `revisada_en`.

La bandeja usa este grupo para su filtro «ya revisadas», así que una cuarta
resolución futura aparecería ahí sola.

---

## 5. Quien levanta no valida

Es la regla más importante de la historia.

```python
if self.censista_id == usuario.pk:
    return False, "No puedes validar tu propia encuesta. Quien levanta la
                   información no puede ser quien la aprueba: eso anularía el
                   control cruzado."
```

Viene directamente de lo que la HU-04 escribió al sembrar los permisos:

> «CENSISTA → solo sus propias fichas. Ni ve las de otros ni valida nada, **porque
> validar su propio trabajo anularía el control cruzado**.»

**El reparto de permisos no basta**, y esa es la parte interesante:

- un **supervisor** puede tener encuestas propias —tiene `ver_propias`—;
- el **administrador** tiene todos los permisos por definición
  (`Usuario.tiene_permiso()`, regla 1 de la HU-04).

Sin esta comprobación, cualquiera de los dos podría firmar su propio trabajo. Hay una
prueba para cada caso, incluida `test_ni_siquiera_el_administrador_valida_la_suya`.

Y se comprueba **en el modelo**, no solo en la vista, porque es una regla del negocio
y no de una pantalla: cualquier camino futuro —otra vista, un comando, una acción del
admin— tiene que respetarla.

---

## 6. Las restricciones reescritas

La migración 0007 **borra y vuelve a crear** `encuesta_estado_valido` y
`encuesta_cierre_coherente`. Conviene poder explicar por qué:

Las dos enumeran los estados como **texto literal**, por la razón que la HU-07 dejó
escrita: *una restricción viaja a la migración y tiene que seguir significando lo
mismo dentro de diez versiones del modelo*.

La contrapartida de esa decisión es esta migración. Agregar un estado obliga a
reescribir ambas, porque `ANULADA` tiene que entrar:

- en la lista de valores válidos;
- en el grupo de estados **cerrados** (una encuesta anulada ya no depende del
  encuestador, así que exige `cerrada_en`).

**Es el precio correcto.** La alternativa —restricciones que leen la lista del
modelo— habría dejado migraciones antiguas cuyo significado cambia al editar código,
y una migración que se comporta distinto según el código de hoy no sirve para
reconstruir una base.

### 6.1 La restricción nueva

```sql
CHECK (estado <> 'ANULADA' OR comentario_revision <> '')
```

Mismo criterio que `encuesta_cierre_con_motivo` (HU-10), aplicado a la decisión del
supervisor: **una ficha descartada sin explicación no se puede defender** —ni ante el
encuestador cuyo trabajo se tira, ni ante quien audite el censo—.

**Solo cubre ANULADA.** Validar no necesita comentario: aprobar es el resultado
esperado y exigir un texto por cada ficha buena produciría cientos de «ok». La HU-15
extenderá la restricción a `OBSERVADA`, que sí lo necesita.

---

## 7. `resolver()`

```python
def resolver(self, nuevo_estado, usuario, comentario=""):
```

Es a la resolución lo que `cambiar_estado()` es al ciclo de vida: **el único camino
correcto**, porque hay cuatro columnas que tienen que moverse juntas —estado,
`revisada_por`, `revisada_en` y el comentario— y repartir eso por las vistas
garantiza que alguna se olvide una.

**No comprueba si la persona puede.** Eso lo responde `puede_resolverla()`, y se
mantienen separados a propósito:

> Una pregunta es «¿está permitido?» y la otra «hazlo». Mezclarlas obligaría a que
> cada llamada interpretara un resultado en vez de confiar en que la comprobación ya
> se hizo, que es justamente el patrón que hace que las comprobaciones se salten.

Detalle: las tres columnas de la resolución se escriben **antes** de llamar a
`cambiar_estado()`, para que viajen en el mismo `save()` y la fila nunca quede a
medias. Es la lección que la HU-10 aprendió con `update_fields`.

---

## 8. Los formularios

Uno pide muy poco y el otro bastante, y la asimetría es el punto:

| | `ValidarEncuestaForm` | `AnularEncuestaForm` |
|---|---|---|
| Campos | un comentario **opcional** | causa + explicación + confirmación |
| Por qué | aprobar es el resultado esperado | anular tira el trabajo de otra persona |

### 8.1 Por qué hay una causa **además** del texto

El texto explica **este** caso; la causa permite **contar**.

> «Cuántas fichas se anulan por duplicado» es una pregunta de calidad del operativo
> que un campo libre no responde: habría que leer doscientos textos.

La causa se guarda al principio del comentario (`"Duplicada: …"`), en una sola
columna, en vez de agregar otra al modelo para un dato que solo tiene sentido junto a
su explicación. El formato lo genera `comentario_completo()` en un único sitio, para
que los reportes futuros busquen un prefijo que solo se construye de una forma.

### 8.2 La casilla de confirmación

Dice la consecuencia en voz alta: *«Entiendo que la encuesta se descarta y que esa
vivienda queda sin datos»*. No es burocracia — es la diferencia entre pulsar un botón
rojo y aceptar lo que hace.

---

## 9. Lo que NO hace anular

**No borra nada.** La encuesta, su hogar, sus integrantes y sus fotografías siguen
ahí, marcados como anulados.

Borrarlos sería tentador —«no sirven»— y sería un error:

> El registro de que **alguien levantó** esa ficha y de que **otra persona la
> descartó**, con su motivo, es justamente lo que permite auditar el operativo y
> detectar si un encuestador está inventando datos.

Es la misma distinción que la HU-09 razonó al **permitir** borrar un integrante: allí
se borraba un dato capturado por error, sin pasado que explicar. **Aquí hay pasado y
explica algo.** Hay una prueba de que el hogar y las personas sobreviven a la
anulación.

---

## 10. Vistas, URLs y templates

| URL | Qué hace | Permiso |
|---|---|---|
| `/encuestas/<pk>/validar/` | GET confirma, POST aprueba | `fichas.validar` |
| `/encuestas/<pk>/anular/` | GET muestra el formulario, POST descarta | `fichas.validar` |

**Aquí sí se exige `fichas.validar`**, y no `fichas.ver_todas` como en la HU-13. Es
el corte que aquella historia dejó preparado: leer el trabajo de todos y firmarlo son
capacidades distintas.

En la pantalla de revisión, los botones **se dibujan con `validar`** aunque la
pantalla **se abra con `ver_todas`**. Quien solo puede mirar ve la ficha completa sin
acciones.

Y cuando no se puede resolver, **se explica por qué** en lugar de esconder los
botones en silencio: un supervisor mirando su propia ficha necesita saber que es la
separación de funciones y no un fallo.

### 10.1 Dos pasos, siempre

GET confirma y POST ejecuta, por lo mismo que en toda la aplicación: si validar se
pudiera hacer con un GET, un `<img src="...">` incrustado en cualquier página
aprobaría fichas con la sesión del supervisor.

Además, la pantalla intermedia de validar **muestra un resumen** y avisa si la ficha
está incompleta, con un enlace a devolverla en lugar de aprobarla. No bloquea —el
supervisor puede tener motivos, por ejemplo que no hubiera señal para el GPS— pero
aprobar sin verlo sería aprobar a ciegas.

### 10.2 Dos supervisores en la misma bandeja

`comprobar_resoluble()` corre en el **GET y en el POST**. No es paranoia: dos
supervisores mirando la misma cola pueden pulsar el botón de la misma ficha con
segundos de diferencia, y el segundo tiene que encontrarse con «ya está resuelta» en
vez de sobrescribir la decisión del primero. Hay una prueba de eso.

---

## 11. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0007_resolucion_del_supervisor.py
backend/templates/fichas/encuesta_validar.html
backend/templates/fichas/encuesta_anular.html
backend/docs/HU-14_aprobar_o_anular.md              este documento
```

### Modificados

```
backend/fichas/models.py     + estado ANULADA, + ESTADOS_RESUELTOS,
                             + 3 columnas de resolución, + 1 restricción,
                             + esta_resuelta / puede_resolverla() / resolver()
backend/fichas/forms.py      + ValidarEncuestaForm, + AnularEncuestaForm,
                               filtro de anuladas en la bandeja
backend/fichas/views.py      + ValidarEncuestaView, + AnularEncuestaView y su mixin,
                               contador de anuladas, banderas de la pantalla de revisión
backend/fichas/urls.py       + 2 rutas
backend/fichas/tests.py      + 66 pruebas; ajustadas 5 de historias anteriores
backend/fichas/management/commands/crear_encuestas_demo.py   siembra una anulada
backend/dashboards/views.py                       + contador de anuladas
backend/templates/fichas/revision_encuesta.html   + acciones y bloque de resolución
backend/README.md · README.md
```

Cinco pruebas anteriores cambiaron por el octavo estado, y una a propósito: la que
comprobaba que la pantalla de revisión **no** ofrecía acciones. Ahora comprueba que
las ofrece **solo con el permiso correcto**.

---

## 12. Pruebas

```bash
python manage.py test fichas          # 693 (HU-07 a HU-14)
python manage.py test                 # 1.239 en total
```

| Bloque | Qué comprueba |
|---|---|
| `EstadoAnuladaTest` | es cerrada, la partición sigue exhaustiva, ≠ rechazada, exige comentario |
| `PuedeResolverlaTest` | solo lo recibido, y **nadie valida lo propio** (ni el administrador) |
| `ResolverTest` | las cuatro columnas se mueven juntas, conserva la fecha de envío |
| `ValidarFormTest` / `AnularFormTest` | comentario opcional vs. causa + motivo + confirmación |
| `ValidarEncuestaVistaTest` | resumen, aviso de ficha incompleta, GET no valida, doble resolución |
| `AnularEncuestaVistaTest` | «anular no es devolver», no borra el hogar, exige confirmar |
| `ResolucionEnLasPantallasTest` | botones por permiso, motivo explicado, contadores y filtros |
| `IntegracionHU14Test` | una se valida y otra se anula; la cola queda vacía |

---

## 13. Explicación para la defensa

**En una frase:** aprobar es barato y anular es caro, y el sistema lo refleja en cada
detalle.

**Las tres cosas que conviene poder defender:**

1. **El estado se llama ANULADA y no RECHAZADA.** Porque «rechazada» ya significa que
   la familia no quiso participar. Con un solo nombre, «40 rechazadas» dejaría de
   distinguir dos situaciones que exigen respuestas opuestas.
2. **Quien levanta no valida, y el permiso no basta.** Un supervisor puede tener
   fichas propias y el administrador tiene todos los permisos por definición. La
   regla vive en el modelo para que ningún camino la esquive.
3. **Anular no borra.** El registro de quién levantó una ficha y quién la descartó,
   con su motivo, es lo que permite auditar el operativo y detectar datos inventados.

**Lo que cuesta el diseño anterior:** agregar un estado obligó a reescribir dos
restricciones, porque enumeran los valores como texto literal. Es el precio de que
una migración antigua siga significando lo mismo años después, y se paga a gusto.

---

## 14. Posibles preguntas del profesor

**La historia dice «rechazar», ¿por qué tu estado se llama «anulada»?**
Porque `RECHAZADA` ya existía y significa que la familia rechazó participar. Son dos
hechos opuestos y mezclarlos haría ilegible cualquier recuento del censo.

**¿Cuál es la diferencia entre anular y devolver con observaciones?**
Devolver reabre la encuesta para que el encuestador la corrija; anular la cierra sin
corregir, y esa vivienda queda sin datos. La pantalla lo advierte antes del
formulario, con enlace a la alternativa.

**¿Por qué el administrador no puede validar su propia encuesta si tiene todos los
permisos?**
Porque la regla no es de permisos, es de negocio: validar el propio trabajo anula el
control cruzado. Vive en el modelo, así que ningún permiso la desactiva.

**¿Por qué validar no exige comentario y anular sí?**
Porque aprobar es el resultado esperado y exigir un texto por cada ficha buena
produciría cientos de «ok» que nadie leería. Anular tira el trabajo de otra persona:
ahí el motivo es obligatorio y lo garantiza una restricción de la base de datos.

**¿Por qué guardas la causa dentro del mismo campo de texto?**
Porque solo tiene sentido junto a su explicación. El prefijo permite contar
anulaciones por causa sin agregar una columna, y lo genera una única función para que
el formato no se bifurque.

**¿Por qué anular no borra los datos?**
Porque el registro de que alguien levantó esa ficha y otro la descartó, con motivo, es
justamente lo que permite auditar el operativo. Es lo contrario del caso de la HU-09,
donde se borra un integrante agregado por error: ahí no había pasado que explicar.

**¿Qué pasa si dos supervisores resuelven la misma ficha a la vez?**
El segundo se encuentra con que ya está resuelta y no sobrescribe nada: la
comprobación corre en el GET y en el POST. Hay una prueba.

**¿Se puede revertir una validación?**
No desde estas pantallas, y es deliberado: revertir una firma es una decisión con
consecuencias distintas y merece su propio diseño. El camino previsto para corregir
una ficha ya enviada es devolverla con observaciones antes de validarla.

---

## 15. Conclusión técnica

La HU-14 agrega **un estado, tres columnas, una restricción, dos pantallas y ningún
permiso**.

Su valor técnico está en tres cosas:

1. **Nombra bien.** `ANULADA` en vez de reutilizar `RECHAZADA` es la diferencia entre
   un censo que se puede leer y uno que confunde la negativa de una familia con un
   error de un encuestador.
2. **Pone la regla donde no se puede esquivar.** «Quien levanta no valida» está en el
   modelo, no en la vista, y ni el administrador la sortea.
3. **Trata distinto lo que es distinto.** Aprobar pide un comentario opcional; anular
   pide causa, explicación y confirmación, y no borra nada.

Lo que queda del sprint: **devolver con observaciones** (HU-15), la tercera salida de
la bandeja y la única que reabre la encuesta; y las **alertas de registros
incompletos** (HU-16), que convertirán en reglas las señales que la HU-13 dejó como
descriptivas.
