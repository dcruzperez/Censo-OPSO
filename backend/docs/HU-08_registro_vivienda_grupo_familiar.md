# HU-08 · Registro de una vivienda y su grupo familiar

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero registrar una nueva vivienda y su grupo familiar para almacenar la información del censo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **121 pruebas automáticas** propias (**804** en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no agrega ni un permiso**. Reutiliza `fichas.crear` y
> `fichas.editar`, **ya sembrados** por la HU-04, el reparto de sectores de la
> HU-06 —convertido aquí en una regla de seguridad—, el validador de RUT de la
> HU-01, `PermisoRequeridoMixin` y el fragmento `_campo.html` de la HU-03.
> Es la primera historia del proyecto que **revisa el modelo de la anterior**, y la
> primera con una **migración que mueve datos** entre tablas.

---

## Índice

1. [Explicación inicial: de la puerta al dato](#1-explicación-inicial)
2. [Las tres tablas y por qué no son una](#2-las-tres-tablas)
3. [La revisión de la HU-07](#3-la-revisión-de-la-hu-07)
4. [Los campos del censo](#4-los-campos-del-censo)
5. [La migración que mueve datos](#5-la-migración-que-mueve-datos)
6. [La regla de negocio central: dónde puedo registrar](#6-dónde-puedo-registrar)
7. [Formularios](#7-formularios)
8. [Vistas y URLs](#8-vistas-y-urls)
9. [Templates e interfaz](#9-templates-e-interfaz)
10. [Seguridad, permisos y datos personales](#10-seguridad-permisos-y-datos-personales)
11. [Archivos creados y modificados](#11-archivos-creados-y-modificados)
12. [Pruebas](#12-pruebas)
13. [Explicación para la defensa](#13-explicación-para-la-defensa)
14. [Posibles preguntas del profesor](#14-posibles-preguntas-del-profesor)
15. [Conclusión técnica](#15-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 Qué faltaba

La HU-07 le dijo al encuestador **qué puertas tocar**. Esta historia es lo que
pasa **cuando la puerta se abre**: dar de alta la vivienda que se encontró y los
datos de la familia que vive en ella. Es la primera historia del proyecto que
escribe información del censo; todas las anteriores administraban el sistema o
repartían el trabajo.

Hasta aquí OPSO podía decir «te tocan 37 viviendas» y no podía guardar ni una sola
respuesta. Después de esta historia, el sistema **almacena información del censo**,
que es literalmente lo que la historia pide.

### 1.2 Dos cosas, no una

El título de la historia nombra **dos** entidades, y no es casualidad de redacción:

- La **vivienda** es el inmueble: dónde está, de qué está hecha, qué servicios
  tiene.
- El **grupo familiar** es el hogar que vive en ella: quién es jefe de hogar,
  cuántos son, cuánto ingresan.

Y no van una a una. En terreno, **una vivienda puede alojar más de un hogar** con
toda normalidad: una casa donde vive la madre y en la pieza del fondo la hija con
su familia. Ese hecho es el que obliga a modelarlas por separado y el que explica
casi todas las decisiones de esta historia.

---

## 2. Las tres tablas

```
Region ──< Comuna                       GEOGRAFÍA        (HU-05)
Operativo ──< Sector ──< Zona           ORGANIZACIÓN     (HU-05)
                │
                ├──< AsignacionSector   REPARTO          (HU-06)
                │
                └──< Vivienda ──< Encuesta ──1:1── GrupoFamiliar
                        HU-08       HU-07              HU-08
```

| Tabla | Qué es | Cada cuánto cambia |
|---|---|---|
| `Vivienda` | el objeto **físico** | casi nunca: una casa de albañilería sigue siéndolo |
| `Encuesta` | el **trabajo** y su estado | en cada operativo hay una nueva |
| `GrupoFamiliar` | el **dato levantado** | cada vez que se levanta; la familia puede cambiar |

Se podría guardar todo en `Encuesta`. Sería una tabla de treinta columnas que
mezcla tres cosas que cambian por motivos distintos y en momentos distintos, y esa
es la definición de una tabla mal cortada.

### 2.1 Por qué `GrupoFamiliar` es uno a uno y no columnas de `Encuesta`

Dos razones, y la segunda es la que de verdad decide:

**a) Mezclaría gestión y contenido.** `Encuesta` gobierna el trabajo (quién,
estado, fechas). Con las cuatro historias que faltan del sprint, meterle el
contenido del censo la convertiría en una tabla que hace de todo.

**b) Perdería una información que hoy es gratis.** Que la fila **exista** significa
«aquí ya se levantó algo», y que no exista significa «esto no se ha tocado». Con
columnas nulas dentro de `Encuesta` habría que preguntar «¿está vacío el nombre del
jefe de hogar?» para deducir lo mismo, y esa deducción se escribiría distinta en
cada pantalla. Por eso `Encuesta.tiene_grupo_familiar` es una comprobación de
existencia y no de contenido.

### 2.2 CASCADE aquí, PROTECT allá: no es una incoherencia

OPSO desactiva en vez de borrar casi en todas partes (cuentas en la HU-03, comunas
y sectores en la HU-05, asignaciones en la HU-06). Aquí hay dos `CASCADE`, y cada
uno tiene su motivo:

| Relación | on_delete | Por qué |
|---|---|---|
| `Encuesta.vivienda` | CASCADE | una encuesta es el levantamiento **de** esa casa; sin la casa no significa nada |
| `GrupoFamiliar.encuesta` | CASCADE | no es «el hogar de la casa 1425», es «lo que respondió **esta** encuesta» |
| `Encuesta.censista` | PROTECT | borrar una cuenta no puede llevarse el trabajo del censo (HU-03) |
| `Vivienda.zona` | PROTECT | borrar la zona dejaría viviendas sin ubicación (HU-05) |

---

## 3. La revisión de la HU-07

Esta es la parte de la historia que más conviene poder explicar en la defensa,
porque es una **decisión anterior que se revisa**, no un error que se corrige.

La HU-07 escribió, en su decisión de diseño 4:

> «Sería tentador exigir que no se repita una dirección dentro de una zona, y sería
> un error. En terreno una misma dirección aloja más de un hogar con toda
> normalidad. […] La contrapartida —dos encuestas duplicadas por error— es un
> problema de calidad de datos, no de integridad, y se resuelve donde corresponde:
> la pantalla avisa cuando ya hay otra encuesta en la misma dirección.»

**El argumento sigue siendo correcto; el modelo que lo acompañaba era el
provisional.** Con la HU-07, «dos hogares en la misma casa» eran dos filas de
`Encuesta` con la dirección repetida. En cuanto la HU-08 agrega el tipo de
vivienda, la materialidad y los servicios básicos, esa repetición dejaría de ser
inocente: **las dos filas tendrían cada una su copia del inmueble, y podrían
contradecirse**. Una diría «casa» y la otra «departamento» de la misma dirección, y
ningún error avisaría.

Con `Vivienda` como tabla propia, el caso se modela como lo que es: **una vivienda
y dos encuestas colgando de ella**. La dirección deja de repetirse porque deja de
estar en la tabla que se repite.

> Es el mismo movimiento que hizo `RegistroAuditoria` entre la HU-04 y la HU-05:
> allí se había escrito «solo hay dos tipos de objeto auditables y no se prevén
> muchos más», la HU-05 agregó cuatro de golpe, y la decisión se revisó en vez de
> arrastrarse. **Una decisión se revisa cuando su premisa cambia, y la revisión se
> escribe.**

### 3.1 Lo que la revisión mejoró, medido

| Pregunta | Con el modelo de la HU-07 | Con el de la HU-08 |
|---|---|---|
| ¿Otro hogar en esta casa? | comparar cadenas de texto | seguir una clave foránea |
| ¿La casa del fondo y la de adelante? | indistinguibles de dos hogares | dos viviendas distintas |
| ¿Dónde está la materialidad? | repetida por hogar | una sola vez |
| ¿Puede haber contradicción? | sí, y en silencio | imposible por construcción |

Hay una prueba dedicada a la diferencia, y su nombre lo dice:
`test_otra_vivienda_con_la_misma_direccion_no_es_otro_hogar`.

### 3.2 Y sigue sin haber unicidad por dirección

Ahora por un motivo distinto: resuelto el caso de los dos hogares, queda el sitio
con **dos viviendas** en la misma dirección —la casa del fondo y la de adelante—,
que en terreno es frecuentísimo y no tiene numeración propia.

Lo que hace el sistema es **avisar**, no bloquear: al registrar en una dirección
donde ya hay otra vivienda, el formulario se detiene, muestra la que existe con un
enlace y pide confirmar. **Bloquear haría perder un dato real; avisar cuesta un
clic.**

---

## 4. Los campos del censo

### 4.1 La vivienda: seis características

| Campo | Opciones |
|---|---|
| `tipo` | casa, departamento, pieza en conventillo, mediagua, rancho, precaria, otra |
| `tenencia` | propia pagada, propia pagándose, arrendada, cedida, ocupación irregular, otra |
| `materialidad_muros` | hormigón, albañilería, tabique forrado, tabique sin forro, adobe, precario |
| `origen_agua` | red pública, pozo, camión aljibe, superficial, otro |
| `sistema_sanitario` | alcantarillado, fosa, letrina, cajón sobre pozo negro, no tiene |
| `tiene_electricidad` | sí / no |

**Las opciones no se inventaron:** siguen la clasificación con que el Instituto
Nacional de Estadísticas describe las viviendas en el censo chileno. Usar el
vocabulario oficial no es estilo, es lo que permite **comparar los resultados de
OPSO con las cifras nacionales**. Una categoría propia («casa chica», «casa
grande») produciría datos que no se pueden cruzar con nada.

**Solo se pregunta por los muros**, y no también por el techo y el piso como hace
el censo completo. El formulario lo llena una persona de pie en la puerta: cada
pregunta cuesta tiempo y cansa a quien responde, y los muros son el indicador que
mejor resume la calidad constructiva. Si un operativo necesitara el detalle, son
dos columnas más; empezar por las tres habría sido pedir datos «por si acaso».

### 4.2 Obligatorias en el formulario, opcionales en la columna

Las seis admiten vacío en la base de datos y **el formulario las exige todas**. La
asimetría es deliberada:

- El **formulario** las exige porque un censo con la mitad de las viviendas «sin
  dato» no permite calcular nada, y quien está en la puerta puede responderlas
  mirando.
- La **columna** admite el vacío porque **ya existen filas sin esa información**:
  la HU-07 creó el padrón por visitar cuando la vivienda todavía no se había
  descrito. La única alternativa a dejar el dato vacío sería inventarlo, y eso es
  fabricar datos del censo (ver la sección 5).

El sistema lo hace visible en vez de esconderlo: `Vivienda.datos_completos`
responde si está descrita, la ficha muestra **«Sin describir»** y ofrece el enlace
para completarla al llegar.

> Detalle que costó una prueba: `tiene_electricidad` es un booleano **nulo**
> («no sabemos» y «no tiene luz» son cosas distintas), y Django lo traduce a un
> `NullBooleanField`, cuyo `validate()` **no hace nada**. Marcarlo como `required`
> no basta y el formulario aceptaría el vacío en silencio. Se comprueba a mano en
> `clean_tiene_electricidad`, y hay una prueba que lo vigila.

### 4.3 El grupo familiar

| Campo | Obligatorio | Nota |
|---|---|---|
| `jefe_hogar_nombre` | sí | mínimo tres caracteres: una inicial no es un nombre |
| `jefe_hogar_rut` | **no** | se valida con dígito verificador si se entrega |
| `telefono_contacto` | no | para coordinar la segunda visita |
| `integrantes_declarados` | sí | ≥ 1, garantizado por `CheckConstraint` |
| `ingreso_mensual` | no | se rechaza por encima de 100 millones |
| `observaciones` | no | |

**Por qué el RUT no se exige.** Es el único identificador fuerte del formulario y
da la tentación de obligarlo. No se hace, por una razón de terreno y otra legal:

- En terreno mucha gente no lo recuerda y no siempre va a buscar el carnet a la
  primera visita. Exigirlo convertiría una encuesta completa en una encuesta que no
  se puede guardar.
- El RUT es un **dato personal**, y condicionar el registro a entregarlo es recoger
  más de lo necesario para el fin declarado (Ley N° 19.628 y Ley N° 21.719).

Cuando **sí** se entrega, se valida con `validar_rut` de la HU-01 —el mismo con
dígito verificador que protege las cuentas— y se normaliza con `limpiar_rut`, para
que «12.345.678-5» y «12345678-5» sean el mismo dato y no dos. **Un RUT mal escrito
es peor que ninguno: parece un identificador y no identifica a nadie.**

**El tope del ingreso** no es un juicio sobre la familia ni un límite legal: es el
umbral a partir del cual lo más probable es que sobre un dígito. En un teléfono, un
cero de más no se nota en pantalla y sí desplaza el promedio de una zona entera.

### 4.4 `integrantes_declarados` existe aunque venga la HU-09

La historia siguiente registra a las personas una por una, así que este número se
podría contar. Se guarda igual, por lo mismo que la HU-05 guarda
`viviendas_estimadas` en la zona teniendo después las viviendas reales: **son dos
datos distintos y su diferencia es información.**

«La señora dijo que viven seis y hay tres personas registradas» significa que la
encuesta está incompleta, y eso solo se detecta si se guardó lo que la señora dijo.

---

## 5. La migración que mueve datos

`fichas/0002_vivienda_y_grupo_familiar.py` es la primera migración del proyecto que
**traslada filas de una tabla a otra**, y por eso está escrita a mano: el generador
automático sabe crear columnas, pero al encontrarse una clave foránea obligatoria
nueva pregunta por un valor por defecto, y aquí no hay ninguno correcto.

### 5.1 El orden

```
1. Crea fichas_vivienda y fichas_grupo_familiar
2. Agrega Encuesta.vivienda como NULA      ← única forma en una tabla con filas
3. RunPython: crea la vivienda de cada encuesta y la apunta
4. Vuelve la clave foránea OBLIGATORIA     ← recién ahora
5. Quita de fichas_encuesta zona, direccion y referencia
```

Invertir 3 y 4 dejaría la migración a medias en cualquier base que ya tenga
encuestas, que es justamente el caso que existe para resolver.

### 5.2 Las viviendas migradas quedan SIN DESCRIBIR, y es lo correcto

Las encuestas de la HU-07 tienen dirección y zona; nadie levantó todavía el tipo ni
la materialidad. La migración podría rellenarlos con «lo más común» y dejar la base
sin vacíos, y sería lo peor que podría hacer:

> **Un dato inventado es peor que un dato ausente**, porque nadie puede
> distinguirlo después y acabaría sumado en un informe.

### 5.3 Se puede deshacer, y eso obliga a ordenar con cuidado

`migrate fichas 0001` revierte la historia completa. Conseguirlo tiene un truco que
conviene poder explicar: Django deshace las operaciones **en orden inverso**, así
que al revertir lo primero que ocurre es que **reaparecen vacías** las tres
columnas borradas. Si se declararan obligatorias, la base rechazaría ahí mismo la
vuelta atrás.

Por eso las columnas se vuelven **nulas antes de borrarlas**, aunque en el sentido
de ida eso no sirva para nada. En el de vuelta es lo que hace posible la secuencia
correcta:

```
reaparecen nulas → revertir() las rellena → vuelven a ser obligatorias
```

**Verificado sobre la base de desarrollo real**, con 18 encuestas: se aplicó, se
revirtió (18 filas con dirección y zona restauradas) y se volvió a aplicar sin
perder una sola.

---

## 6. Dónde puedo registrar

Es **la regla de negocio central de la historia**, y está escrita una sola vez, en
`fichas/forms.py::zonas_disponibles()`. La usan el formulario (para armar el
desplegable) y las vistas (para comprobar el POST). Si cada uno la escribiera por
su cuenta, bastaría con que una copia se quedara atrás para abrir un agujero.

Un encuestador puede registrar en una zona **si y solo si** se cumplen las cuatro:

| Condición | De dónde viene |
|---|---|
| la zona es de un sector **asignado** a esa persona, con la asignación **vigente** | HU-06 |
| el operativo **no está cerrado** | HU-05 |
| el sector está **activo** | HU-05 |
| la zona está **activa** | HU-05 |

Esto **convierte el reparto del supervisor en una regla de seguridad** y no solo en
una lista informativa: retirar a alguien de un sector (HU-06) le quita, en el acto,
la capacidad de registrar ahí. Hay una prueba que lo comprueba
(`test_una_asignacion_retirada_deja_de_dar_acceso`).

Y se aplica donde importa: **si la opción no está en el formulario, enviarla a mano
no la hace válida**. Es la misma técnica con la que la HU-06 hizo imposible asignar
a alguien fuera de la lista de disponibles.

---

## 7. Formularios

`ViviendaForm` y `GrupoFamiliarForm` son **ModelForm**, al contrario que los de la
HU-04 y la HU-06, que eran `Form` a mano. No es un cambio de gusto: aquellos
editaban un **conjunto** (los permisos de un rol, el equipo de un sector) y un
ModelForm no aportaba nada; estos editan **un objeto y uno solo**, y entonces el
ModelForm regala la validación de cada campo, los mensajes de error y la coherencia
con las restricciones del modelo.

### 7.1 El aviso de duplicado, sin JavaScript

Se implementa con una casilla que **solo aparece cuando hay conflicto**:

1. Primer envío → el formulario falla y explica qué encontró, con enlace a la
   vivienda existente.
2. Segundo envío con la casilla marcada → guarda.

No hace falta JavaScript ni una pantalla intermedia. Y la casilla no se dibuja
cuando no hay conflicto, porque **una casilla que pide confirmar algo que no ha
pasado enseña a marcar sin leer**.

---

## 8. Vistas y URLs

| URL | Vista | Permiso |
|---|---|---|
| `/encuestas/viviendas/nueva/` | registrar vivienda | `fichas.crear` o `fichas.editar` |
| `/encuestas/viviendas/<pk>/` | ficha de la vivienda y sus hogares | `ver_propias` o `ver_todas` |
| `/encuestas/viviendas/<pk>/editar/` | corregir o completar | `crear` o `editar` |
| `/encuestas/<pk>/hogar/` | registrar o editar el grupo familiar | `crear` o `editar` |
| `/encuestas/viviendas/<pk>/hogar/nuevo/` | agregar un segundo hogar (**solo POST**) | `crear` o `editar` |

### 8.1 Una vivienda nueva nace siempre con una encuesta

Guardar la vivienda crea además la encuesta de quien la registró, en estado
`BORRADOR`, en la **misma transacción**. No hay pantalla para hacer solo una.

Es deliberado: **nadie registra una vivienda en terreno «por si acaso»**. Se
registra porque se está ahí, tocando esa puerta, y por lo tanto el trabajo empezó.

- Dejar la vivienda **sin encuesta** produciría casas que no le aparecen a nadie en
  «Mis encuestas» y que nadie va a levantar.
- Dejar la encuesta en **PENDIENTE** diría «sin visitar», y la visita es justamente
  lo que acaba de pasar.

### 8.2 Guardar el hogar deja la encuesta en BORRADOR, no en COMPLETADA

Al hogar todavía le faltan sus integrantes uno por uno (HU-09). Darla por
completada aquí haría que el supervisor recibiera para validar fichas a las que les
falta la mitad. La transición a `COMPLETADA` es de la historia de borradores, que
es la que define cuándo una encuesta está terminada.

### 8.3 «Agregar otro hogar» es POST y no un enlace

Porque **crea una fila**. Si un GET pudiera hacerlo, bastaría con que alguien
incrustara la dirección en un `<img src="...">` para llenar la base de encuestas
vacías con la sesión de quien mirara la página. Es la misma razón por la que
retirar una asignación en la HU-06 son dos pasos. Hay una prueba que comprueba que
un GET responde **405**.

---

## 9. Templates e interfaz

| Plantilla | Qué es |
|---|---|
| `fichas/vivienda_form.html` | alta y edición (la misma, con `es_alta`) |
| `fichas/hogar_form.html` | el grupo familiar |
| `fichas/vivienda_detalle.html` | la casa y sus hogares |
| `fichas/sin_territorio.html` | «no tienes dónde registrar» |

**Una sola plantilla para alta y edición**, porque los campos son idénticos y
mantener dos archivos garantiza que un campo nuevo aparezca en uno y falte en el
otro.

**El formulario se agrupa en tres bloques y el orden no es casual**: es el orden en
que se responde estando de pie en la puerta.

1. **Dónde está** — zona, dirección, referencia → se sabe antes de tocar
2. **Cómo es** — tipo, materialidad → se ve desde la calle
3. **Qué tiene** — tenencia, agua, sanitario, luz → hay que preguntarlo

**«No hay dónde registrar» se decide antes de dibujar el formulario**, y no dejando
el desplegable de zonas vacío: un formulario que no se puede completar es peor que
no ofrecerlo, porque la persona rellena nueve campos y descubre el problema al
enviar.

---

## 10. Seguridad, permisos y datos personales

### 10.1 Quinta historia seguida sin agregar permisos

| Permiso | Censista | Supervisor |
|---|---|---|
| `fichas.ver_propias` | ✅ | ✅ |
| `fichas.ver_todas` | — | ✅ |
| `fichas.crear` | ✅ | **—** |
| `fichas.editar` | ✅ | **—** |
| `fichas.validar` | — | ✅ |

Ese reparto lo sembró la HU-04. La consecuencia es la mejor demostración del diseño
del proyecto: **la separación entre quien levanta la información y quien la valida
—principio que estableció la HU-03— la aplica hoy el catálogo de permisos sin que
ninguna vista tenga que comprobarla a mano.** Un supervisor que abra
`/encuestas/viviendas/nueva/` es rechazado porque no tiene `fichas.crear`, no
porque exista un `if` que lo nombre.

### 10.2 Escribir exige más que leer

Ver la ficha de otra persona es **supervisión** y está permitido con
`fichas.ver_todas`. **Escribir** en ella sería levantar información en su nombre, y
el dato quedaría atribuido a quien no estuvo en la puerta. La ficha del censo tiene
que poder responder quién la levantó, y esa respuesta es `encuesta.censista`.

Por eso `RegistrarHogarView` restringe el queryset a `censista=request.user` **sin
excepción**, ni siquiera para el supervisor. Hay prueba.

### 10.3 Lo que se comprueba en el servidor, siempre dos veces

| Regla | GET | POST |
|---|---|---|
| territorio asignado | ✅ | ✅ |
| operativo abierto, sector y zona activos | ✅ | ✅ |
| encuesta no cerrada | ✅ | ✅ |
| encuesta propia | ✅ | ✅ |

Ocultar un botón no es una validación: la URL del POST se puede enviar a mano. Es
la lección que la HU-03 documentó y la HU-06 repitió, y aquí hay pruebas de POST
directo para cada caso.

### 10.4 Datos personales de terceros

Es la primera historia que guarda datos de **personas que no son usuarias del
sistema**: familias que no eligieron estar en la base. Eso se refleja en tres
decisiones concretas:

- el RUT es opcional (sección 4.3);
- el formulario **avisa en pantalla** de que son datos personales y de quién los
  verá, porque quien está en la puerta no lee una política de privacidad: lee lo
  que el encuestador le dice;
- los nombres del comando de demostración son **inventados y se nota que lo son**.

---

## 11. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0002_vivienda_y_grupo_familiar.py   traspaso de datos
backend/templates/fichas/vivienda_form.html
backend/templates/fichas/hogar_form.html
backend/templates/fichas/vivienda_detalle.html
backend/templates/fichas/sin_territorio.html
backend/docs/HU-08_registro_vivienda_grupo_familiar.md        este documento
```

### Modificados

```
backend/fichas/models.py        + Vivienda, + GrupoFamiliar, Encuesta reapuntada
backend/fichas/forms.py         + ViviendaForm, + GrupoFamiliarForm, + zonas_disponibles
backend/fichas/views.py         + 5 vistas; las de la HU-07 adaptadas
backend/fichas/urls.py          + 4 rutas
backend/fichas/admin.py         + Vivienda y GrupoFamiliar, inlines
backend/fichas/tests.py         + 121 pruebas; las 137 de la HU-07 adaptadas
backend/fichas/management/commands/crear_encuestas_demo.py    siembra viviendas y hogares
backend/dashboards/views.py     consultas reapuntadas a vivienda
backend/templates/fichas/mis_encuestas.html      + botón de registrar
backend/templates/fichas/encuesta_detalle.html   + hogar y características
backend/docs/HU-07_encuestas_asignadas.md        nota de revisión
backend/README.md · README.md
```

---

## 12. Pruebas

```bash
python manage.py test fichas          # 258 (137 de la HU-07 + 121 de esta)
python manage.py test                 # 804 en total
```

| Bloque | Qué comprueba |
|---|---|
| `ViviendaModeloTest` | descrita / sin describir, hogares, CASCADE, valores inventados |
| `PuedeRegistrarseTrabajoTest` | operativo cerrado, sector y zona desactivados, con su motivo |
| `PuedeRegistrarseEncuestaTest` | los siete estados; observada sí, cerradas no |
| `GrupoFamiliarModeloTest` | uno a uno, cero personas, RUT normalizado, ingreso por persona |
| `ZonasDisponiblesTest` | las cuatro condiciones, y que retirar la asignación corta el acceso |
| `ViviendaFormTest` | zonas ajenas, las seis obligatorias, el aviso de duplicado |
| `GrupoFamiliarFormTest` | RUT con dígito verificador, ingreso desmesurado, campos opcionales |
| `RegistrarViviendaTest` | crea vivienda + encuesta, sin territorio, supervisor rechazado |
| `EditarViviendaTest` | completar el padrón heredado, 404 fuera del territorio |
| `RegistrarHogarTest` | guarda, deja en BORRADOR, ajena 404, cerrada bloqueada por POST |
| `AgregarHogarTest` | segundo hogar sin duplicar la casa, GET responde 405 |
| `ViviendaDetalleTest` | dos hogares, sin describir, supervisor sin botón |
| `FichaConHogarTest` | lo que la pantalla de la HU-07 gana |
| `IntegracionHU08Test` | recorrido completo: HU-06 reparte → registra casa → hogar → segundo hogar |

---

## 13. Explicación para la defensa

**En una frase:** la HU-07 dijo qué puertas tocar; la HU-08 guarda lo que hay
detrás, y para hacerlo bien tuvo que **revisar el modelo de la HU-07**.

**Las tres cosas que conviene poder defender:**

1. **Tres tablas y no una.** Vivienda (física, estable), Encuesta (trabajo,
   efímero) y GrupoFamiliar (dato levantado). La prueba de que el corte es correcto
   es que una casa con dos familias se describe **una sola vez**.
2. **La revisión de la decisión 4 de la HU-07.** No se corrige un error: se revisa
   una decisión cuya premisa cambió al aparecer las características de la vivienda.
   Está escrito en el código, en la migración y aquí.
3. **La migración no inventa datos.** Las viviendas heredadas quedan «sin
   describir» y el sistema lo muestra. Un dato inventado es peor que uno ausente.

**Lo que demuestra el diseño del proyecto:** cinco historias seguidas sin agregar
un permiso, y una separación de funciones —quien levanta no valida— que hoy la
aplica el catálogo de la HU-04 sin que ninguna vista la nombre.

---

## 14. Posibles preguntas del profesor

**¿Por qué no guardaste todo en la tabla de encuestas?**
Porque son tres cosas que cambian por motivos y en momentos distintos, y porque una
casa con dos familias tendría dos copias de la materialidad, que podrían
contradecirse sin que nada avisara.

**¿No es un error haber tenido que cambiar el modelo de la historia anterior?**
El modelo de la HU-07 era correcto para su alcance: no había características de la
vivienda que duplicar. La HU-07 dejó anotado por escrito su punto débil y la HU-08
lo resuelve en cuanto aparece la información que lo justifica. Es la misma revisión
que hubo entre la HU-04 y la HU-05 con la bitácora.

**¿Por qué las características admiten vacío si el formulario las exige?**
Porque existen filas anteriores sin ellas y la única alternativa habría sido
inventarlas. Prefiero una base que distingue «no lo sé» de «es una casa» a una base
sin huecos y con datos falsos.

**¿Por qué el RUT no es obligatorio?**
Por terreno y por ley: mucha gente no lo recuerda, y condicionar el registro a
entregar un dato personal no imprescindible es recoger más de lo necesario
(Ley N° 21.719). Cuando se entrega, se valida con dígito verificador.

**¿Qué impide que un encuestador registre viviendas en un sector que no es suyo?**
`zonas_disponibles()`: el desplegable solo ofrece las zonas de sus sectores
asignados y vigentes, y las vistas vuelven a comprobarlo en el POST. Retirarle la
asignación le corta el acceso en el acto.

**¿Y que un supervisor registre fichas?**
No tiene `fichas.crear` ni `fichas.editar` en el reparto de la HU-04. La separación
de funciones la aplica la matriz de permisos, no un `if`.

**¿Por qué guardar el hogar no completa la encuesta?**
Porque faltan los integrantes uno por uno, que es la historia siguiente. Darla por
completada mandaría al supervisor fichas a medias.

**¿Se puede deshacer la migración?**
Sí, y está probado sobre la base real: aplicar, revertir y volver a aplicar sin
perder ninguna de las 18 encuestas existentes.

---

## 15. Conclusión técnica

La HU-08 agrega **dos tablas, cinco pantallas y ningún permiso**, y es la primera
del proyecto en la que OPSO **almacena información del censo**.

Su valor técnico está en tres cosas:

1. **Corta bien el dominio.** Vivienda / Encuesta / GrupoFamiliar es la separación
   que hace que una casa con dos familias se describa una vez, y la que deja
   preparado el resto del sprint: los integrantes cuelgan del hogar, el GPS y las
   fotografías de la vivienda.
2. **Revisa una decisión anterior en vez de arrastrarla**, y deja escrito por qué,
   con una migración reversible que no inventa un solo dato.
3. **Convierte el reparto del supervisor en una regla de seguridad.** Lo que la
   HU-06 modeló como organización del trabajo es hoy lo que decide dónde se puede
   escribir.

La deuda consciente que deja es la del sprint, y está documentada: el hogar todavía
no tiene a sus **integrantes** uno por uno, no hay **guardado parcial explícito** ni
transición a COMPLETADA, y faltan el **GPS** y las **fotografías**. Las cuatro
cuelgan de estas tablas sin cambiarlas.
