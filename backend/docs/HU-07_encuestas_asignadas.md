# HU-07 · Visualización de las encuestas asignadas y su estado

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero visualizar las encuestas asignadas y su estado para organizar mi trabajo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **135 pruebas automáticas** propias (681 en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no agrega ni un permiso**. Reutiliza `fichas.ver_propias` y
> `fichas.ver_todas`, **ya sembrados** por la HU-04, el modelo `Zona` de la HU-05,
> el reparto de sectores de la HU-06, `PermisoRequeridoMixin` y el fragmento
> `_paginacion.html`. Es la **primera historia del sprint del encuestador** y la
> primera cuyo protagonista es quien hace el trabajo de terreno.

> ⚠️ **Actualización de la HU-08.** El modelo descrito en este documento cambió al
> implementarse la historia siguiente: la dirección, la referencia y la zona ya no
> son columnas de `Encuesta`, sino de una tabla `Vivienda` nueva, y `Encuesta`
> apunta a ella. La **decisión de diseño 4** (sección 2.5) se revisó por ese
> motivo, y la revisión está explicada en
> [`HU-08_registro_vivienda_grupo_familiar.md`](HU-08_registro_vivienda_grupo_familiar.md),
> sección 3. Todo lo demás de esta historia —los siete estados, el orden por
> urgencia, los contadores, el control de acceso— sigue vigente tal cual, porque
> `direccion`, `referencia` y `zona` se conservaron como **propiedades** que
> delegan en la vivienda.

---

## Índice

1. [Explicación inicial: del sector a la puerta](#1-explicación-inicial)
2. [El modelo de datos](#2-el-modelo-de-datos)
3. [Base de datos: las tres restricciones](#3-base-de-datos)
4. [El ciclo de vida de una encuesta](#4-el-ciclo-de-vida)
5. [El orden de la jornada y los filtros](#5-el-orden-de-la-jornada)
6. [Vistas](#6-vistas)
7. [URLs](#7-urls)
8. [Templates e interfaz](#8-templates-e-interfaz)
9. [Seguridad y control de acceso](#9-seguridad-y-control-de-acceso)
10. [Rendimiento](#10-rendimiento)
11. [Migraciones y datos de demostración](#11-migraciones-y-datos-de-demostración)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 El problema que resuelve

La HU-05 le dio a OPSO el mapa. La HU-06 repartió el mapa entre personas. Esta
historia baja un nivel más y responde la pregunta que el encuestador se hace de
verdad al levantarse: **¿qué puertas tengo que tocar hoy, y por cuál empiezo?**

Después de la HU-06, un encuestador que abre OPSO ve «tienes Los Boldos a cargo».
Eso es cierto y es insuficiente: no sabe por dónde va, cuánto le queda, ni qué
dejó a medias ayer. La propia HU-05 dejó escrito el argumento al justificar la
existencia de la zona:

> «vamos 3 de 5 zonas» es información útil; «vamos 0 de 1 sector» no dice nada
> durante tres días.

Esta historia lleva ese razonamiento hasta el final: **el avance real se mide en
puertas, no en polígonos**.

| Sin esta historia | Con esta historia |
|---|---|
| «Creo que me faltan unas cuarenta» | 37, y 12 son de la Zona 3 |
| Un borrador olvidado se descubre al cerrar el operativo | Sale primero en la lista, con su fecha |
| El supervisor devuelve una ficha y avisa por teléfono | Aparece en rojo arriba de todo |
| «¿Esta casa ya la hizo alguien?» | La ficha avisa si hay otra encuesta en la misma dirección |
| El avance del operativo se estima | Se calcula: cerradas / total |

### 1.2 Esta historia es la primera de un sprint

El sprint del encuestador tiene seis historias, y esta es la número uno:

1. **Visualizar las encuestas asignadas y su estado** ← esta
2. Registrar una vivienda nueva y su grupo familiar
3. Registrar los integrantes del hogar
4. Guardar borradores para continuar después
5. Capturar la ubicación GPS
6. Adjuntar fotografías de la vivienda

Esto condiciona el diseño de forma deliberada: aquí se modela la encuesta como
**unidad de trabajo** —dónde es, de quién es y en qué estado está— y no como
contenedor de datos del censo. El contenido lo agregan las historias siguientes,
sobre esta misma tabla o colgando de ella.

Se hace en este orden, y no esperando a tener el formulario completo, porque **el
estado es justamente lo que las historias siguientes van a mover**: el borrador de
la historia 4 no es un modelo nuevo, es una encuesta en estado `BORRADOR`. Definir
el ciclo de vida primero evita que cada historia invente el suyo y que después
haya que reconciliarlos.

### 1.3 Una aclaración de vocabulario: encuesta y ficha

El proyecto usa las dos palabras con precisión, y no son sinónimos descuidados:

- La **encuesta** es el trabajo de terreno: ir, tocar la puerta, preguntar.
- La **ficha** es el registro que queda de ese trabajo.

Por eso el modelo se llama `Encuesta` —lo que el encuestador organiza es su
trabajo— y la app se llama `fichas` —lo que el sistema guarda y el supervisor
valida—. El nombre de la app no se eligió en esta historia: lo fijó la HU-04 al
sembrar el módulo `FICHAS` con los permisos `fichas.crear`, `fichas.editar` y
`fichas.validar`. Llamar `encuestas` a la app obligaría a que el código pidiera
permisos de un módulo con otro nombre.

---

## 2. El modelo de datos

### 2.1 Dónde encaja la tabla nueva

```
Region ──< Comuna                       GEOGRAFÍA        (HU-05)
Operativo ──< Sector ──< Zona           ORGANIZACIÓN     (HU-05)
                │
                └──< AsignacionSector   REPARTO          (HU-06)

Zona ──< Encuesta >── Usuario           TRABAJO          (HU-07, esta)
```

Una sola tabla nueva, `fichas_encuesta`, con dos claves foráneas que la definen:
**dónde** (la zona) y **quién** (el encuestador).

### 2.2 Decisión 1 — la encuesta cuelga de la ZONA, no del sector

Lo inmediato sería colgarla del sector, que es lo que la HU-06 asigna a las
personas. Se descartó por dos razones concretas:

1. **La zona ya existe justamente para esto.** Su docstring en la HU-05 dice que
   el sector «no es una unidad de trabajo, es un objetivo de varios días» y que la
   zona lo parte en pedazos abarcables. Colgar las encuestas del sector
   desperdiciaría esa división y dejaría al encuestador con 400 puertas sin ningún
   corte natural.
2. **La zona lleva `viviendas_estimadas`**, que la HU-06 usa para repartir la
   carga. Con las encuestas colgando de la zona, esa estimación **se puede
   contrastar con la realidad**: «la Zona 1 estimaba 80 viviendas y llevamos 93».
   Colgándolas del sector, la estimación y el hecho quedarían en niveles distintos
   y no se podrían comparar.

El sector, la comuna y el operativo siguen a un paso de distancia mediante las
propiedades `encuesta.sector`, `.comuna` y `.operativo`, así que no se pierde nada.

### 2.3 Decisión 2 — el encuestador es obligatorio

`censista` no admite nulos. Se evaluó permitir encuestas «sin dueño» —un padrón
que el supervisor reparte después— y se descartó porque **ese padrón ya existe y
es el territorio**: una vivienda que todavía no es de nadie es, simplemente, una
zona sin encuestas cargadas. Modelar además una encuesta huérfana crearía dos
formas de decir lo mismo, y la pantalla del encuestador tendría que explicar por
qué hay trabajo que no le aparece a nadie.

`on_delete=PROTECT`, igual que `AsignacionSector.censista`: borrar la cuenta de una
persona no puede llevarse por delante las fichas del censo que levantó. La HU-03
estableció que las cuentas se deshabilitan y no se borran; esta clave foránea hace
que ese acuerdo lo garantice PostgreSQL y no la buena voluntad del programador.

### 2.4 Decisión 3 — el estado va acompañado de sus dos fechas

`estado` responde «¿cómo está?» y por sí solo no responde «¿desde cuándo?». Sin
fechas, la pantalla no puede distinguir un borrador de ayer de uno de hace tres
semanas, que es exactamente la diferencia entre «lo termino hoy» y «esto se quedó
olvidado».

| Columna | Qué marca | Cuándo está vacía |
|---|---|---|
| `iniciada_en` | la primera visita a la vivienda | solo si está `PENDIENTE` |
| `cerrada_en` | cuándo dejó de depender del encuestador | mientras siga siendo trabajo suyo |

Las dos están **amarradas al estado** por sendas restricciones de la base de datos
(sección 3), y por eso el estado no se cambia a mano sino con `cambiar_estado()`
(sección 4).

### 2.5 Decisión 4 — NO hay unicidad por dirección

> **Revisada en la HU-08.** El argumento de abajo sigue siendo correcto, pero el
> modelo que lo acompañaba era el provisional: con las características de la
> vivienda encima, dos filas con la misma dirección habrían duplicado también la
> materialidad y los servicios. La HU-08 interpuso la tabla `Vivienda`, así que
> «dos hogares en la misma casa» pasó a ser *una* vivienda con *dos* encuestas.
> Ver la sección 3 del documento de la HU-08.

Sería tentador exigir que no se repita una dirección dentro de una zona, y sería
un error. En terreno **una misma dirección aloja más de un hogar con toda
normalidad**: una casa con dos familias, una parcela con una casa al fondo, un
block sin numeración interna. Una restricción de unicidad ahí impediría registrar
el segundo hogar, y el censo dejaría fuera precisamente a las familias más
difíciles de contar, que son las que un operativo social busca.

La contrapartida —dos encuestas duplicadas por error— es un problema de **calidad
de datos**, no de integridad, y se resuelve donde corresponde: la ficha de detalle
avisa cuando hay otra encuesta en la misma dirección y deja la decisión en manos
de quien mira la pantalla.

> Es la misma forma de razonar que la HU-06 aplicó al índice único parcial: la
> restricción correcta no es la más estricta, es la que coincide con la realidad
> que se está modelando.

### 2.6 Los campos

| Campo | Tipo | Para qué |
|---|---|---|
| `zona` | FK a `operativos.Zona` (PROTECT) | dónde queda la vivienda |
| `censista` | FK a `usuarios.Usuario` (PROTECT) | quién debe levantarla |
| `direccion` | `CharField(200)` | calle y número |
| `referencia` | `CharField(200)`, opcional | cómo reconocerla desde la calle |
| `estado` | `CharField` con opciones, indexado | en qué va |
| `observaciones` | `TextField`, opcional | indicaciones para esa vivienda |
| `asignada_por` | FK a `Usuario` (SET_NULL) | quién encargó la encuesta |
| `creada_en` / `actualizada_en` | `DateTimeField` automáticos | trazabilidad |
| `iniciada_en` / `cerrada_en` | `DateTimeField`, opcionales | los dos límites del trabajo |

---

## 3. Base de datos

Tres restricciones `CHECK`, que valen **aunque nadie pase por un formulario**: una
importación masiva, un script o una consulta SQL directa se topan con las mismas
reglas.

### 3.1 `encuesta_estado_valido`

```sql
CHECK (estado IN ('PENDIENTE','BORRADOR','COMPLETADA','OBSERVADA',
                  'VALIDADA','NO_UBICADA','RECHAZADA'))
```

Misma técnica que `operativo_estado_valido` (HU-05) y `rol_codigo_valido` (HU-01).

### 3.2 `encuesta_inicio_coherente`

> `iniciada_en` está vacía **si y solo si** la encuesta sigue `PENDIENTE`.

Una encuesta empezada sin fecha de inicio haría imposible ordenar por antigüedad,
que es justo lo que permite detectar un borrador olvidado.

### 3.3 `encuesta_cierre_coherente`

> `cerrada_en` está vacía **si y solo si** la encuesta sigue siendo trabajo del
> encuestador (`PENDIENTE`, `BORRADOR` u `OBSERVADA`).

Es la más importante de las tres. **Impide que una ficha devuelta por el supervisor
conserve su fecha de cierre** y siga contando como terminada en el avance del
operativo. Sin ella, el porcentaje que ve el encuestador —y el que verá el reporte
de la historia de reportes— mentiría hacia arriba sin que ningún error avisara.

Es la misma lección que `asignacion_baja_coherente` en la HU-06, aplicada a un caso
peor: allí eran dos columnas y una transición; aquí son tres columnas y siete
estados, es decir, siete oportunidades de olvidarse.

### 3.4 Los dos índices

| Índice | Consulta que acelera |
|---|---|
| `idx_encuesta_censista` (`censista`, `estado`) | «mis encuestas», muchas veces al día desde un teléfono |
| `idx_encuesta_zona` (`zona`, `estado`) | «¿cómo va esta zona?», para supervisión y reportes |

---

## 4. El ciclo de vida

### 4.1 Los siete estados

| Estado | Qué significa para el encuestador | ¿Trabajo suyo? |
|---|---|---|
| `PENDIENTE` | tengo que ir; no la he tocado | sí |
| `BORRADOR` | la empecé y quedó a medias | sí |
| `OBSERVADA` | el supervisor me la devolvió con reparos | sí, y lo más urgente |
| `COMPLETADA` | la terminé y la envié | no, está en revisión |
| `VALIDADA` | el supervisor la aprobó | no |
| `NO_UBICADA` | la dirección no existe o está deshabitada | no |
| `RECHAZADA` | la familia no quiso participar | no |

**Los dos últimos no son fracasos, son resultados.** Una encuesta que no se pudo
levantar tiene que poder cerrarse dejando constancia del motivo. Si el único final
posible fuera `COMPLETADA`, esas puertas quedarían pendientes para siempre y el
avance mentiría hacia abajo: nadie podría distinguir «faltan 40 por visitar» de
«40 no se pueden levantar y ya se sabe».

`OBSERVADA` y `VALIDADA` las escribe el **supervisor**, y las transiciones que las
producen pertenecen a la historia de validación de fichas (permiso
`fichas.validar`, sembrado por la HU-04). Se definen ya porque el encuestador
**necesita verlas**: «me devolvieron una ficha» es exactamente el tipo de cosa que
esta historia existe para que no se pierda por teléfono.

### 4.2 La partición abierto / cerrado

Siete estados, pero para el encuestador solo hay una pregunta: **¿esto es trabajo
mío o ya no?** Esa partición se escribe una sola vez, en `fichas/models.py`:

```python
ESTADOS_ABIERTOS = (PENDIENTE, BORRADOR, OBSERVADA)
ESTADOS_CERRADOS = (COMPLETADA, VALIDADA, NO_UBICADA, RECHAZADA)
```

La usan el modelo (restricciones y propiedades), la vista (contadores y filtros),
el panel del censista y las pruebas. Repartirla por el código en listas escritas a
mano garantizaría que un octavo estado quedara fuera de alguna de ellas.

Es **exhaustiva y excluyente**, y hay dos pruebas que lo comprueban para que siga
siéndolo:

```python
def test_los_dos_grupos_cubren_todos_los_estados(self):
    self.assertEqual(set(ESTADOS_ABIERTOS) | set(ESTADOS_CERRADOS),
                     set(EstadoEncuesta.values))
```

### 4.3 `cambiar_estado()`: por qué existe

Es **el único camino correcto para mover el estado**, y existe por lo mismo que
`AsignacionSector.desactivar()` en la HU-06: hay columnas que tienen que moverse
juntas, y si cada vista lo hiciera a mano alguna olvidaría una.

Las dos reglas que aplica son exactamente las que comprueban las restricciones:

- Al salir de `PENDIENTE` marca `iniciada_en`, si no estaba. **Incluso hacia
  `NO_UBICADA`**: registrar que una vivienda no se pudo ubicar implica haber ido a
  buscarla, así que hubo una visita y tiene fecha.
- Pone `cerrada_en` al pasar a un estado cerrado y la **borra** al volver a uno
  abierto. Ese borrado es el caso que justifica el método por sí solo.

**No valida qué transiciones son legales** (de `PENDIENTE` a `VALIDADA`, por
ejemplo), y es deliberado: quién puede mover qué es una decisión de permisos y se
resuelve en las vistas de cada historia, que son las que saben quién está pidiendo
el cambio. El modelo se ocupa de que la fila quede coherente, que es lo que nadie
más puede garantizar.

---

## 5. El orden de la jornada

### 5.1 La pantalla no se ordena por fecha ni alfabéticamente

Se ordena por **urgencia**, porque el propósito de la historia —«para organizar mi
trabajo»— es responder qué hago primero:

| Orden | Estado | Por qué va ahí |
|---|---|---|
| 1 | `OBSERVADA` | hay trabajo rehecho y **alguien esperando**; es lo único que bloquea a otra persona |
| 2 | `BORRADOR` | terminar lo empezado cuesta menos que empezar algo nuevo, y una visita ya gastada que no se cierra se pierde |
| 3 | `PENDIENTE` | el trabajo normal del día |
| 4 | `COMPLETADA` | enviada; se muestra para saber qué se hizo |
| 5 | el resto | cerradas |

Dentro del mismo estado manda el **orden del recorrido** (sector, zona, dirección),
que es como se camina una calle.

### 5.2 Por qué se ordena en SQL y no en Python

Porque el listado está **paginado**. Ordenar en memoria solo ordenaría la página
que ya trajo la base de datos, y la primera página dejaría de ser «lo más urgente»
para pasar a ser «las 20 primeras por casualidad, ordenadas entre sí». Se resuelve
con un `CASE` de SQL construido con `Case/When` del ORM:

```python
ORDEN_POR_URGENCIA = Case(
    When(estado=EstadoEncuesta.OBSERVADA, then=Value(0)),
    When(estado=EstadoEncuesta.BORRADOR, then=Value(1)),
    ...
)
```

Hay una prueba dedicada a esto: crea 24 encuestas y una observada con la dirección
alfabéticamente última, y comprueba que esa última es la primera de la página 1.

### 5.3 Los filtros

`FiltroMisEncuestasForm` es un `Form` y no un `ModelForm`: no crea ni modifica
nada, solo **limpia lo que llega por la URL**, que la escribe cualquiera. Sin él,
`?estado=BORRAD0R` (con un cero) llegaría tal cual al ORM.

| Filtro | Detalle |
|---|---|
| `q` | busca en dirección y referencia |
| `estado` | los siete estados **más dos grupos**: «las que requieren tu trabajo» y «las ya cerradas» |
| `sector` | solo los sectores donde **esa persona** tiene encuestas |
| `historicas` | casilla para incluir los operativos ya cerrados |

Los dos grupos del desplegable no son un adorno: son la pregunta que el
encuestador se hace de verdad, y sin ellos tendría que filtrar tres veces y sumar
de memoria. **No se enumeran en el formulario**: se leen de `ESTADOS_ABIERTOS` y
`ESTADOS_CERRADOS`.

El desplegable de sector se construye con los datos de la persona, igual que
`FiltroAsignacionesForm` en la HU-06 ofrecía solo los censistas desplegados: una
opción que siempre devuelve una lista vacía es una opción que estorba. Tiene además
una consecuencia agradable: **la lista de sectores ajenos no se puede leer desde
este formulario**.

Por defecto se ocultan las encuestas de operativos **cerrados**, porque un
operativo cerrado no es trabajo, es historia. Es la misma separación que hace «Mis
sectores», resuelta con un filtro en vez de con dos listas porque este listado está
paginado.

---

## 6. Vistas

### 6.1 `MisEncuestasView` — `/encuestas/`

`ListView` protegida con `PermisoRequeridoMixin` y `fichas.ver_propias`. Aporta:

- el listado paginado de 20 en 20, ordenado por urgencia;
- los **contadores** del encabezado y la barra de avance;
- el **avance por zona**, que responde «¿a qué zona voy hoy?».

**Los contadores se calculan sobre el trabajo vivo, no sobre la página ni sobre el
filtro.** Un contador que cambia al filtrar no responde «¿cuánto me queda?»,
responde «¿cuánto me queda de lo que estoy mirando?», que ya se ve en la lista. Es
el mismo criterio con que el panel de la HU-06 mantiene sus contadores globales al
pasar de página.

Son **ocho recuentos y una sola consulta**, con el argumento `filter` de `Count`,
que PostgreSQL resuelve con `FILTER (WHERE ...)` en la misma pasada:

```python
consulta.aggregate(
    total=Count("id"),
    por_trabajar=Count("id", filter=Q(estado__in=ESTADOS_ABIERTOS)),
    ...
)
```

### 6.2 `EncuestaDetailView` — `/encuestas/<pk>/`

`DetailView` que admite `fichas.ver_propias` **o** `fichas.ver_todas`
(`exigir_todos` queda en `False`). El permiso decide si puede usar el módulo; **qué
encuesta puede abrir se decide fila por fila** restringiendo el queryset.

Muestra dónde queda la vivienda, cómo reconocerla, las indicaciones, en qué va, y
—si las hay— las otras encuestas en la misma dirección.

Es de **solo lectura**: en esta historia no hay nada que guardar. Existe ya porque
es el sitio natural donde las historias siguientes del sprint colgarán sus
acciones, y porque el encuestador necesita ver la referencia y las indicaciones
antes de salir.

---

## 7. URLs

```
/encuestas/            mis encuestas y su estado
/encuestas/<pk>/       la ficha de una encuesta
```

**Por qué el listado propio es la raíz y no `/encuestas/mis-encuestas/`.** La HU-06
puso «mis sectores» en una subruta porque en `/operativos/` ya vivía el listado
general del administrador: la pantalla propia era la excepción dentro de un módulo
de gestión. Aquí es al revés: el módulo de encuestas nace para el encuestador y su
listado propio es la pantalla principal. Cuando la historia de supervisión agregue
el listado de **todas** las encuestas del operativo, esa irá en su propia subruta,
porque será la excepción.

---

## 8. Templates e interfaz

| Plantilla | Qué es |
|---|---|
| `fichas/mis_encuestas.html` | la pantalla principal |
| `fichas/encuesta_detalle.html` | la ficha de una encuesta |
| `fichas/_estado_encuesta.html` | fragmento con la etiqueta de color del estado |

### 8.1 El orden de la página responde a las preguntas de la mañana

1. **¿Cuánto me queda?** → contadores y barra de avance
2. **¿Hay algo urgente?** → aviso de fichas devueltas, en rojo y con enlace directo
3. **¿A qué zona voy hoy?** → pastillas con lo que queda por zona
4. **¿Qué puerta toco?** → la tabla, ordenada por urgencia

Está pensada para leerse **en terreno, en un teléfono con una mano**: la tabla se
desplaza dentro de su contenedor, los contadores caben de a dos por fila y ninguna
acción importante queda al final.

### 8.2 El color se decidió en el modelo, no en la plantilla

`_estado_operativo.html` (HU-05) resolvió la repetición con un fragmento pero dejó
el condicional en el HTML. Aquí el condicional está en `Encuesta.color_estado`, y
el cambio tiene motivo: **son siete estados y no tres**. Un `if/elif` de siete
ramas en una plantilla es ilegible, no se puede probar con una prueba unitaria y
obliga a escribir el nombre de cada estado como texto suelto. En el modelo es un
diccionario, y hay una prueba que comprueba que los siete tienen color.

El color no es decoración, comunica urgencia: rojo = te la devolvieron; naranjo =
la dejaste a medias; gris = sin visitar; azul = en revisión; verde = validada;
negro = cerrada sin datos.

### 8.3 Lo que se reutilizó y lo que se retocó

- `operativos/_paginacion.html` se **reutiliza tal cual** desde otro módulo, en vez
  de copiarlo. Se le agregó una variable opcional `genero` para concordar el
  participio con sustantivos femeninos («12 encuestas encontradas»); quienes ya lo
  incluían no pasan nada y siguen leyendo igual.
- `base.html` gana el enlace «Mis encuestas», mostrado **por permiso**
  (`fichas.ver_propias`), al contrario que «Mis sectores», que se muestra por un
  hecho. La explicación está en la sección 9.
- `dashboards/censista.html` **estrena datos reales**: sus dos contadores eran
  marcadores de posición (`—`) desde la HU-01, igual que le pasó al panel del
  supervisor hasta la HU-06.

---

## 9. Seguridad y control de acceso

### 9.1 Cuarta historia seguida sin agregar permisos

| Permiso | Quién lo tenía ya | Para qué se usa aquí |
|---|---|---|
| `fichas.ver_propias` | Censista y Supervisor (HU-04) | entrar al módulo y ver lo propio |
| `fichas.ver_todas` | Supervisor (HU-04) | abrir la ficha de otra persona |

El reparto inicial de la HU-04 ya modeló esta historia dos historias antes de que
existiera la pantalla. **Esta historia no le concede nada nuevo a nadie.**

### 9.2 Esta pantalla exige permiso y «Mis sectores» no. ¿Contradicción?

No, y la diferencia ya estaba escrita en el proyecto. `MisSectoresView` (HU-06)
argumentó por qué no exigía permiso, y en esa misma explicación anticipó el caso
contrario:

> «Se evaluó agregar un permiso `operativos.ver_propios` por simetría con
> `fichas.ver_propias`, que sí existe. La diferencia es que aquel gobierna una
> FUNCIONALIDAD (el módulo de fichas, que un rol puede no tener en absoluto),
> mientras que esto es la pantalla que le dice a una persona cuál es su trabajo.»

Esta es justamente esa funcionalidad. Un rol puede no tener nada que ver con el
levantamiento de información —un coordinador, un digitador, un perfil de consulta
para la municipalidad— y para esos roles el módulo de fichas no debe existir. Ver
el territorio asignado, en cambio, no se le puede quitar a nadie sin inutilizarle
la cuenta.

Dicho corto: **`operativos.ver_propios` no existe porque no habría ningún motivo
operativo para revocarlo; `fichas.ver_propias` existe porque sí lo hay.**

### 9.3 El filtro por usuario no es parametrizable

En el listado no hay ningún `<pk>` en la URL ni ningún campo del formulario que
apunte a otra persona. **No existe forma de pedir «las encuestas de fulano»**, así
que no hace falta comprobar que no se esté haciendo. Es la misma construcción de
`MisSectoresView`: el control de acceso más fiable no es el que comprueba bien la
petición, es el que hace que la petición peligrosa no se pueda ni formular.

Nótese que un supervisor con `fichas.ver_todas` que entre aquí verá **sus**
encuestas —probablemente ninguna—, no las de todos. Esta pantalla es «lo mío» por
definición; el listado general del operativo será otra pantalla. Confundirlas haría
que el mismo botón mostrara cosas distintas según quién lo pulsa.

### 9.4 La ficha ajena responde 404, no 403

Un encuestador que pida la encuesta de otra persona recibe un **404**. No es un
descuido: **un 403 confirma que esa ficha existe**. Con identificadores que se
pueden probar en secuencia (`/encuestas/1/`, `/2/`, `/3/`), esa diferencia permite
averiguar cuántas encuestas tiene el operativo y en qué rango de identificadores
están, sin ver ni una.

Se implementa **restringiendo el queryset** y no comprobando después de
`get_object()`, que es la diferencia entre que la regla se aplique siempre y que se
aplique mientras nadie olvide llamarla. Si mañana esta vista gana un método `POST`,
seguirá operando solo sobre filas que el usuario puede ver.

### 9.5 Ocultar el enlace no es seguridad

El menú esconde «Mis encuestas» a quien no tiene el permiso, y eso es **comodidad**:
evita ofrecer una pantalla que va a responder «no tienes permiso». La seguridad
real está en la vista, porque la URL siempre se puede escribir a mano. Hay pruebas
de las dos cosas por separado.

---

## 10. Rendimiento

| Riesgo | Cómo se evita |
|---|---|
| Una consulta por fila para pintar la zona, el sector, la comuna y el operativo | `select_related` de los cuatro niveles: 80 consultas menos por página |
| Ocho `.count()` para los contadores | un solo `aggregate()` con `Count(filter=...)` |
| Un recuento por zona para el avance | un solo `values().annotate()`, agrupado por PostgreSQL |
| Un recuento por permiso en el menú | `tiene_algun_permiso()` con `__in`, de la HU-04 |

Las pruebas no fijan un número exacto de consultas —sería frágil— sino que
comprueban que **el coste no crece** con la cantidad de datos, que es el mismo
enfoque de la HU-05 y la HU-06:

```python
def test_el_numero_de_consultas_no_crece_con_las_encuestas(self):
    self.poblar(3);  con_tres  = self.contar_consultas()
    self.poblar(6);  con_nueve = self.contar_consultas()
    self.assertEqual(con_tres, con_nueve)
```

---

## 11. Migraciones y datos de demostración

### 11.1 La migración

`fichas/0001_initial.py` crea la tabla con sus tres restricciones y sus dos
índices. **No hay datos que migrar**: la tabla nace vacía.

```bash
python manage.py migrate
```

### 11.2 El comando de demostración

La HU-07 es una historia de **consulta**: muestra encuestas y no las crea. La
pantalla de registro llega con la historia siguiente del sprint. Sin datos, la
demostración de esta historia sería una pantalla vacía explicando que todavía no
hay nada, que es justo lo único que no hace falta demostrar.

```bash
python manage.py crear_usuarios_demo      # si no se ha hecho antes
python manage.py crear_encuestas_demo
```

Crea un operativo en curso, una comuna, un sector con tres zonas, la asignación del
sector al censista de demostración (reutilizando la HU-06) y **28 encuestas
repartidas en los siete estados**, con dos hogares a propósito en la misma
dirección. Los siete estados importan: una demostración con todo pendiente no
muestra que la pantalla ordena por urgencia, ni que avisa de las fichas devueltas,
ni que la barra de avance se mueve.

Se puede volver a ejecutar sin duplicar nada, y acepta `--censista correo@` y
`--limpiar`.

---

## 12. Archivos creados y modificados

### Creados

```
backend/fichas/__init__.py
backend/fichas/apps.py
backend/fichas/models.py                                   modelo Encuesta
backend/fichas/forms.py                                    filtros de la pantalla
backend/fichas/views.py                                    las dos vistas
backend/fichas/urls.py
backend/fichas/admin.py
backend/fichas/tests.py                                    135 pruebas
backend/fichas/migrations/0001_initial.py
backend/fichas/management/commands/crear_encuestas_demo.py
backend/templates/fichas/mis_encuestas.html
backend/templates/fichas/encuesta_detalle.html
backend/templates/fichas/_estado_encuesta.html
backend/docs/HU-07_encuestas_asignadas.md                  este documento
```

### Modificados

```
backend/config/settings.py                     app "fichas" en INSTALLED_APPS
backend/config/urls.py                         /encuestas/
backend/dashboards/views.py                    contadores reales del panel del censista
backend/templates/base.html                    enlace «Mis encuestas»
backend/templates/dashboards/censista.html     contadores y próximas encuestas
backend/templates/operativos/_paginacion.html  variable opcional «genero»
backend/README.md                              estado, rutas y pruebas
README.md                                      recuento de pruebas
```

---

## 13. Pruebas

```bash
python manage.py test fichas          # 135 pruebas de esta historia
python manage.py test                 # 681 en total
```

| Bloque | Qué comprueba |
|---|---|
| `EncuestaModeloTest` | valores por defecto, atajos territoriales, `PROTECT` |
| `EstadosTest` | la partición es exhaustiva y excluyente; los siete tienen color |
| `CambiarEstadoTest` | las dos fechas se mueven con el estado, incluido el borrado al observar |
| `RestriccionesBaseDatosTest` | las tres restricciones rechazan filas incoherentes |
| `ValidacionModeloTest` | el mismo error, pero legible y en el campo correcto |
| `AccesoTest` | permiso, permiso desactivado, rol desactivado, cuenta sin rol |
| `MisEncuestasTest` | solo lo propio, operativos cerrados, paginación |
| `OrdenPorUrgenciaTest` | el orden completo y que se aplica **antes** de paginar |
| `FiltrosTest` | los cuatro filtros, su combinación y las URL manipuladas |
| `ResumenTest` | los ocho contadores y que no cambian al filtrar ni al paginar |
| `AvancePorZonaTest` | el agrupado y su orden |
| `ConsultasTest` | el coste no crece con las encuestas ni con las zonas |
| `DetalleTest` | 404 para la ajena, aviso al supervisor, direcciones repetidas |
| `PanelCensistaTest` | los contadores dejaron de ser `—` |
| `MenuTest` | el enlace aparece y desaparece con el permiso |
| `ComandoDemoTest` | siembra los siete estados y es idempotente |
| `IntegracionTest` | recorrido completo: HU-06 reparte → HU-07 muestra |

---

## 14. Explicación para la defensa

**En una frase:** la HU-06 le dijo al encuestador *dónde* trabaja; la HU-07 le dice
*qué* tiene que hacer y *por dónde empezar*.

**Las tres decisiones que conviene poder defender:**

1. **La encuesta cuelga de la zona.** Porque la zona ya era la unidad de trabajo
   abarcable de la HU-05, y porque así la estimación de viviendas se puede
   contrastar con las encuestas reales.
2. **El estado va amarrado a dos fechas por restricciones de la base de datos.**
   Sin eso, una ficha devuelta por el supervisor podría conservar su fecha de
   cierre y seguir contando como terminada: el avance del operativo mentiría sin
   que ningún error avisara.
3. **La pantalla se ordena por urgencia y en SQL.** Porque la historia pide
   organizar el trabajo, no listarlo; y porque ordenar en Python sobre un listado
   paginado solo ordena la página, no la jornada.

**Lo que demuestra el diseño del proyecto:** cuatro historias seguidas sin agregar
un solo permiso. El catálogo que la HU-04 sembró incluía `fichas.ver_propias` y
`fichas.ver_todas` cuando no existía ninguna pantalla de fichas, y esta historia se
autorizó sola. Un permiso sin pantalla no autorizaba nada; con pantalla, autoriza
exactamente lo que su descripción decía.

---

## 15. Posibles preguntas del profesor

**¿Por qué la app se llama `fichas` y el modelo `Encuesta`?**
Porque nombran cosas distintas: la encuesta es el trabajo de terreno y la ficha es
el registro que queda. El nombre de la app lo fijó el módulo de permisos de la
HU-04, que ya se llamaba FICHAS; renombrarlo obligaría a tocar una migración
aplicada y a que el código pidiera permisos de un módulo con otro nombre.

**¿Por qué siete estados y no tres?**
Porque tres no distinguen los casos que cambian lo que el encuestador hace hoy: una
ficha devuelta no es lo mismo que una pendiente, y una vivienda deshabitada no es
lo mismo que una por visitar. Aun así, para el 90 % de las decisiones solo importan
dos grupos, y por eso existen `ESTADOS_ABIERTOS` y `ESTADOS_CERRADOS`.

**¿Por qué no impedir dos encuestas en la misma dirección?**
Porque una misma dirección aloja más de un hogar con toda normalidad, y la
restricción dejaría fuera del censo justo a las familias más difíciles de contar.
El duplicado por error es un problema de calidad de datos y se resuelve avisando en
la pantalla, no bloqueando en la base.

**¿Por qué un 404 y no un 403 al pedir la ficha de otro?**
Porque un 403 confirma que la ficha existe, y con identificadores en secuencia eso
permite contar el padrón del operativo sin ver ninguna ficha.

**¿Por qué esta pantalla exige permiso si «Mis sectores» no lo exigía?**
Porque el módulo de fichas es una funcionalidad que un rol puede no tener en
absoluto, mientras que ver el propio territorio asignado es información mínima de
la cuenta. La propia HU-06 dejó anticipada esa distinción por escrito.

**¿Qué pasa cuando el operativo se cierra?**
Las encuestas dejan de aparecer en el listado por defecto —no son trabajo, son
historia— pero siguen siendo accesibles marcando «incluir operativos cerrados», y
sus fichas se pueden abrir por enlace directo. Nada se borra.

**¿Quién crea las encuestas?**
En esta historia, nadie desde la interfaz: es una historia de consulta. Las crea la
historia siguiente del sprint, cuando el encuestador registra una vivienda nueva.
Mientras tanto están el admin y el comando `crear_encuestas_demo`.

**¿Cómo se conecta esto con las historias que faltan del sprint?**
El registro de la vivienda y del grupo familiar cuelga de esta tabla; los borradores
son el estado `BORRADOR`, que ya existe y ya se muestra; el GPS y las fotografías
son columnas y una tabla más sobre la misma encuesta. Ninguna de esas historias
tiene que inventar un ciclo de vida ni una pantalla de listado.

---

## 16. Conclusión técnica

La HU-07 agrega **una tabla, dos pantallas y ningún permiso**. Su valor técnico no
está en el tamaño sino en tres cosas:

1. **Cierra el recorrido del trabajo de terreno.** Territorio (HU-05) → reparto
   (HU-06) → tarea concreta (HU-07). Cada historia se apoyó en la anterior sin
   reescribirla.
2. **Define el ciclo de vida que va a usar todo el sprint**, y lo protege con
   restricciones de base de datos en vez de con disciplina del programador.
3. **Convierte información en decisión.** No muestra una lista: muestra qué hacer
   primero, dónde queda lo que falta y qué está bloqueado esperando a otra persona.

La deuda consciente que deja es una sola y está documentada: **las encuestas no se
pueden crear desde la interfaz**. Es la historia siguiente del sprint, y hasta
entonces el comando de demostración y el admin cubren el hueco.
