# HU-13 · Revisión de las encuestas recibidas

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor, quiero revisar las encuestas recibidas para validar la calidad de la información.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **67 pruebas automáticas** propias (**1.172** en total en el proyecto → `python manage.py test` → OK)

> Primera historia del **sprint 3 (supervisión)** y primera del módulo cuyo
> protagonista no es el encuestador. **No agrega ni un permiso** —usa
> `fichas.ver_todas`, sembrado por la HU-04— y **no crea ninguna tabla ni
> migración**: es una historia de lectura sobre lo que las seis anteriores dejaron
> guardado.

---

## Índice

1. [Explicación inicial: qué es «revisar»](#1-explicación-inicial)
2. [La excepción que la HU-07 dejó anunciada](#2-la-excepción-anunciada)
3. [Orden de llegada, no de urgencia](#3-orden-de-llegada)
4. [La espera, y por qué se mide](#4-la-espera)
5. [Las señales de la fila](#5-las-señales-de-la-fila)
6. [Dos pantallas para el mismo dato](#6-dos-pantallas-para-el-mismo-dato)
7. [Permisos: `ver_todas` y no `validar`](#7-permisos)
8. [Rendimiento](#8-rendimiento)
9. [Archivos creados y modificados](#9-archivos-creados-y-modificados)
10. [Pruebas](#10-pruebas)
11. [Explicación para la defensa](#11-explicación-para-la-defensa)
12. [Posibles preguntas del profesor](#12-posibles-preguntas-del-profesor)
13. [Conclusión técnica](#13-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 El otro lado del sprint anterior

Las seis historias del encuestador terminaron con una encuesta que llega al estado
`COMPLETADA` y **queda ahí esperando a alguien**. Ese alguien no tenía pantalla:
existían los estados `VALIDADA` y `OBSERVADA` desde la HU-07, pero nadie podía
verlos ni producirlos.

Esta historia construye **la mitad de lectura** de esa espera. Las dos siguientes
del sprint —aprobar/rechazar y devolver con observaciones— construirán la de
escritura.

### 1.2 Revisar no es leer una ficha: es decidir cuál abrir

Es la observación que ordena todo el diseño. Un supervisor con cuarenta encuestas
recibidas no puede leerlas enteras una por una. Lo que necesita es:

1. una **cola** con un orden defendible,
2. **señales por fila** para sospechar sin entrar,
3. y, cuando entra, **todo lo levantado en una sola pantalla**.

Las tres cosas son las tres decisiones de esta historia.

---

## 2. La excepción anunciada

Cuando se escribieron las URL del módulo en la HU-07, se justificó que el listado
propio del encuestador fuera la raíz `/encuestas/` con esta frase:

> «Cuando la historia de supervisión agregue el listado de TODAS las encuestas del
> operativo, esa irá en su propia subruta, **porque será la excepción**.»

Esta es esa pantalla, y va en `/encuestas/revision/`. La predicción se cumplió tal
cual, y eso es lo interesante: **el módulo nació pensado para el encuestador y la
supervisión entró sin reorganizar nada**.

| Ruta | Quién | Qué ve |
|---|---|---|
| `/encuestas/` | encuestador | lo suyo, por urgencia |
| `/encuestas/revision/` | supervisor | lo de todos, por antigüedad |
| `/encuestas/<pk>/` | encuestador | su ficha de trabajo |
| `/encuestas/<pk>/revisar/` | supervisor | la encuesta completa |

---

## 3. Orden de llegada

La bandeja se ordena por **la que lleva más tiempo esperando**. Es el criterio
**opuesto** al de «Mis encuestas» (HU-07), que ordena por urgencia, y no es una
incoherencia: **son dos colas distintas**.

> El encuestador **elige** a qué puerta va, y le conviene atacar primero lo que
> bloquea a otros. El supervisor **no elige**: recibe una cola, y la única política
> justa para una cola es atenderla en orden de llegada.

Ordenarla por «lo más nuevo» o «lo más fácil» produce **fichas antiguas que no se
revisan nunca**, y eso tiene una consecuencia concreta que se explica en la sección
siguiente.

Detalle de implementación: `F("cerrada_en").asc(nulls_last=True)`. Una fila sin
fecha de envío no debería existir —lo garantiza `encuesta_cierre_coherente` desde la
HU-07— pero si existiera, encabezaría la cola con un orden que no significa nada.

---

## 4. La espera

`dias_esperando()` cuenta desde `cerrada_en`, que para una encuesta `COMPLETADA` es
el momento en que el encuestador la envió.

Devuelve **None** cuando la encuesta no está esperando, que es **distinto de cero**:
cero significa «llegó hoy».

### 4.1 Por qué existe un umbral de «espera prolongada»

Siete días, y **no es una opinión sobre la diligencia del supervisor**. Es el punto
a partir del cual **devolver la ficha deja de servir**:

> Si se observa una encuesta tres semanas después, el encuestador ya no se acuerda
> de esa casa y probablemente ya no está trabajando esa zona. Corregirla cuesta
> **otra visita completa** en vez de cinco minutos.

Por eso la bandeja destaca la más antigua con un aviso arriba, y no solo pinta la
fila: **si la cabeza de la cola lleva tres semanas, el problema no es esa ficha, es
el ritmo de revisión**.

---

## 5. Las señales de la fila

Cada fila lleva cuatro datos calculados por `Encuesta.resumen_para_revision()`:

| Señal | Qué permite sospechar |
|---|---|
| personas registradas / declaradas | una ficha enviada a medias |
| vivienda descrita | se saltó el paso de las características |
| tiene ubicación | no se capturó el GPS |
| cuántas fotografías | si hay evidencia adjunta |

**No juzgan: describen.** El sistema no marca fichas como «malas» ni las ordena por
sospecha; quien decide es quien revisa. La bandeja solo hace que una cola de
cuarenta se recorra en un minuto y se entre únicamente a las que lo piden.

> Ese reparto es deliberado y deja sitio a la HU-16, que es la que sí definirá un
> catálogo de **alertas** de registros incompletos. Aquí las señales son
> descriptivas; allí serán una regla del sistema.

`resumen_para_revision()` devuelve un diccionario y no cinco propiedades sueltas
porque la fila las muestra juntas: así se piden una vez y la plantilla no llama a
cinco métodos por encuesta.

---

## 6. Dos pantallas para el mismo dato

`RevisarEncuestaView` **no reutiliza** `EncuestaDetailView` (HU-07), y merece
explicación porque parecen la misma pantalla.

| | Ficha del encuestador (HU-07) | Pantalla de revisión (HU-13) |
|---|---|---|
| Responde | «dónde queda y qué me falta» | «qué levantó esta persona, y cuadra» |
| Muestra | ubicación, indicaciones, pasos pendientes | **todo**: vivienda, hogar, personas, GPS, fotos, trazabilidad |
| Ofrece | acciones para trabajar | nada: solo lee |

Reutilizar aquella habría significado **llenarla de bloques que al encuestador no le
sirven** y, aun así, obligar al supervisor a navegar por cinco pantallas para juntar
lo que necesita ver de una vez.

**Son dos lecturas distintas del mismo dato, y cada una merece su pantalla.**

La de revisión añade además dos cosas que solo importan al supervisar:

- **los otros hogares de la misma vivienda**, porque explican un ingreso por persona
  extraño o una cantidad de gente que no cuadra con la fachada;
- un bloque de **trazabilidad**: quién levantó, cuándo fue la primera visita, cuándo
  se envió, y la nota que el encuestador se dejó a sí mismo (HU-10).

---

## 7. Permisos

Las dos pantallas exigen **`fichas.ver_todas`**, no `fichas.validar`.

Es una decisión, no un descuido: **estas dos pantallas solo leen**. Quien puede ver
el trabajo de todos puede revisarlo; poder aprobarlo o devolverlo es otra cosa y
llega con las historias siguientes, que sí exigirán `fichas.validar`.

Separarlos permite algo real: **un coordinador que necesita mirar cómo va el
operativo puede recibir `ver_todas` sin quedar habilitado para validar fichas**. Con
un solo permiso habría que elegir entre no dejarle mirar o dejarle firmar.

| Rol | `ver_propias` | `ver_todas` | `validar` |
|---|---|---|---|
| Censista | ✅ | — | — |
| Supervisor | ✅ | ✅ | ✅ |
| Administrador | (todos por definición) | | |

El encuestador **no entra a la bandeja** ni a la pantalla de revisión, ni siquiera a
la de una encuesta suya: su lectura es la ficha de la HU-07. Hay pruebas de las dos
cosas.

En el menú, «Revisión» aparece por `fichas.ver_todas`. El supervisor ve los dos
enlaces —«Mis encuestas» y «Revisión»— y es correcto: también puede tener fichas
propias.

---

## 8. Rendimiento

La bandeja muestra por fila datos que viven en cuatro tablas distintas (vivienda,
zona, hogar, integrantes, fotografías). Sin cuidado, eso es una consulta por fila y
por relación.

```python
.select_related("vivienda", "vivienda__zona", ..., "censista", "grupo_familiar")
.prefetch_related("grupo_familiar__integrantes", "vivienda__fotografias")
```

`select_related` para lo que es uno-a-uno hacia arriba; `prefetch_related` para las
colecciones que `resumen_para_revision()` cuenta.

La prueba no fija un número exacto —sería frágil— sino que comprueba que **el coste
no crece** con la cantidad de encuestas, que es el enfoque de la HU-05 en adelante.

Los contadores de la cabecera son **un solo `aggregate` con `Count(filter=...)`**, y
se calculan sobre toda la cola y no sobre lo filtrado: un contador que cambia al
filtrar responde «cuánto hay de lo que estoy mirando», que ya se ve en la lista.

---

## 9. Archivos creados y modificados

### Creados

```
backend/templates/fichas/revision_bandeja.html
backend/templates/fichas/revision_encuesta.html
backend/docs/HU-13_revision_de_encuestas.md        este documento
```

### Modificados

```
backend/fichas/models.py     + esta_en_revision, dias_esperando(),
                               espera_prolongada, resumen_para_revision()
backend/fichas/forms.py      + FiltroRevisionForm
backend/fichas/views.py      + BandejaRevisionView, RevisarEncuestaView y su mixin
backend/fichas/urls.py       + 2 rutas
backend/fichas/tests.py      + 67 pruebas
backend/dashboards/views.py  + la cola de revisión en el panel del supervisor
backend/templates/base.html                       + enlace «Revisión»
backend/templates/dashboards/supervisor.html      + cola y contadores
backend/README.md · README.md
```

**Sin migraciones**: la historia no agrega ni una columna.

---

## 10. Pruebas

```bash
python manage.py test fichas          # 626 (HU-07 a HU-13)
python manage.py test                 # 1.172 en total
```

| Bloque | Qué comprueba |
|---|---|
| `EsperaDeRevisionTest` | solo las completadas esperan, días, umbral, medición a una fecha |
| `ResumenParaRevisionTest` | las cuatro señales, con y sin hogar |
| `BandejaRevisionTest` | acceso por rol, orden de llegada, contadores, señales visibles |
| `FiltrosRevisionTest` | los cinco filtros, los grupos de estados, desplegables acotados |
| `ConsultasBandejaTest` | el coste no crece con el número de encuestas |
| `RevisarEncuestaTest` | todo en una pantalla, avisos, y que **no ofrece acciones** |
| `SupervisionEnElPanelTest` | enlace por permiso, cabeza de la cola, tope de cinco |
| `IntegracionHU13Test` | del envío del encuestador a la bandeja, y que él no entra |

---

## 11. Explicación para la defensa

**En una frase:** la bandeja no está hecha para leer cuarenta fichas, sino para
decidir cuáles abrir.

**Las tres cosas que conviene poder defender:**

1. **Orden de llegada, y es lo contrario de la pantalla del encuestador.** El que
   levanta elige su siguiente puerta; el que supervisa recibe una cola, y una cola
   se atiende por antigüedad o las fichas viejas no se revisan nunca.
2. **El umbral de espera tiene una razón operativa, no moral.** Pasados siete días,
   devolver una encuesta cuesta otra visita completa porque el encuestador ya no
   recuerda esa casa. Por eso el sistema lo avisa.
3. **`ver_todas` y no `validar`.** Estas pantallas solo leen, así que se protegen
   con el permiso de leer. Separarlos permite que un coordinador mire el operativo
   sin quedar habilitado para firmar fichas.

**Lo que demuestra el diseño previo:** la HU-07 predijo por escrito que el listado
de supervisión iría en una subruta «porque será la excepción», y así entró. Siete
historias y **ningún permiso nuevo**.

---

## 12. Posibles preguntas del profesor

**¿Por qué la bandeja ordena distinto que «Mis encuestas»?**
Porque son colas distintas. El encuestador elige a qué puerta va; el supervisor
recibe trabajo y la única política justa para una cola es el orden de llegada.

**¿Por qué siete días y no otro número?**
Porque es aproximadamente lo que un encuestador tarda en dejar de recordar una casa
concreta y en salir de esa zona. Pasado ese punto, devolverle la ficha ya no cuesta
cinco minutos, cuesta otra visita.

**¿Por qué no reutilizaste la ficha que ya existía?**
Porque responde otra pregunta. La del encuestador dice «dónde queda y qué te falta»;
la de revisión dice «qué levantó esta persona y si cuadra». Reutilizarla habría
llenado la del encuestador de bloques inútiles y aun así obligaría a navegar.

**¿Las señales de la fila no deberían bloquear el envío?**
No, y además no es su papel: describen, no juzgan. El catálogo de alertas de
registros incompletos es la HU-16 de este mismo sprint.

**¿Por qué el permiso es `ver_todas` y no `validar`?**
Porque estas pantallas no cambian nada. Con `validar` se excluiría a un perfil que
solo necesita mirar, y con un permiso único no se podría distinguir mirar de
firmar.

**¿Un encuestador puede abrir la pantalla de revisión de su propia encuesta?**
No. Su lectura es la ficha de la HU-07. Hay una prueba de ello, y otra de que sí
sigue entrando a la suya.

**¿Aparecen en la bandeja las encuestas que no se pudieron levantar?**
Sí, filtrables aparte. El supervisor tiene que poder leer el motivo del cierre para
decidir si manda a otra persona a esa dirección — que es justamente para lo que la
HU-10 hizo obligatorio ese motivo.

---

## 13. Conclusión técnica

La HU-13 agrega **dos pantallas, ningún permiso, ninguna tabla y ninguna
migración**. Es la historia más barata del proyecto en código nuevo y una de las que
más se apoya en lo ya construido.

Su valor técnico está en tres cosas:

1. **Elige bien el orden.** La cola por antigüedad no es un detalle de presentación:
   es lo que impide que una ficha se quede sin revisar hasta que corregirla sea
   imposible.
2. **Separa leer de decidir.** `ver_todas` abre estas pantallas; `validar` abrirá
   las siguientes. Ese corte estaba en el catálogo de la HU-04 desde antes de que
   existiera ninguna ficha.
3. **Confirma la arquitectura.** Entró sin migraciones, sin tocar el modelo de datos
   y en la subruta que la HU-07 había reservado por escrito.

Lo que sigue en el sprint: **aprobar o rechazar** (HU-14), **devolver con
observaciones** (HU-15) —las dos con `fichas.validar`, ya sembrado— y las **alertas
de registros incompletos** (HU-16), que convertirán las señales descriptivas de esta
bandeja en un catálogo de reglas.
