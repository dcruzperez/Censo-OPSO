# HU-09 · Registro de los integrantes del hogar

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero registrar los integrantes del hogar para completar la información familiar.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **97 pruebas automáticas** propias (**901** en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no agrega ni un permiso** y **no toca ninguna tabla existente**.
> Reutiliza `fichas.crear` y `fichas.editar` de la HU-04, el validador de RUT de la
> HU-01, el índice único parcial que estrenó la HU-06 y el fragmento `_campo.html`
> de la HU-03. Es la prueba de que el corte de la HU-08 era el correcto: los
> integrantes entraron colgando de `GrupoFamiliar` sin cambiar una sola columna de
> las otras tres tablas.

---

## Índice

1. [Explicación inicial: el último nivel](#1-explicación-inicial)
2. [El modelo](#2-el-modelo)
3. [Las cuatro restricciones](#3-las-cuatro-restricciones)
4. [Los campos del censo de personas](#4-los-campos-del-censo-de-personas)
5. [La validación que define la historia: la edad](#5-la-validación-por-edad)
6. [Declaradas contra registradas](#6-declaradas-contra-registradas)
7. [El nombre del jefe de hogar, en dos sitios](#7-el-nombre-del-jefe-de-hogar)
8. [Vistas y URLs](#8-vistas-y-urls)
9. [Aquí sí se borra: la excepción del proyecto](#9-aquí-sí-se-borra)
10. [Templates e interfaz](#10-templates-e-interfaz)
11. [Seguridad y datos personales](#11-seguridad-y-datos-personales)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 El final del recorrido

```
Región → Comuna → Operativo → Sector → Zona → Vivienda → Hogar → PERSONA
 HU-05    HU-05     HU-05      HU-05   HU-05    HU-08     HU-08   HU-09
```

La HU-08 dejó el hogar registrado con un dato clave y provisional: «viven seis
personas». Esta historia registra a esas seis, una por una, con su edad, su
escolaridad y su ocupación. Es **el nivel más fino de todo OPSO** y donde el censo
deja de ser un recuento de casas para ser información sobre gente.

### 1.2 Lo que confirma sobre el diseño anterior

La HU-08 separó Vivienda / Encuesta / GrupoFamiliar argumentando que eran tres
cosas que cambian por motivos distintos, y dejó una predicción escrita: «los
integrantes cuelgan del hogar sin cambiar nada».

**Se cumplió.** Esta historia agrega una tabla y cero migraciones de datos, frente
a la HU-08, que tuvo que revisar el modelo de la HU-07. La diferencia no es suerte:
es lo que pasa cuando el corte anterior estaba bien hecho.

---

## 2. El modelo

Una sola tabla nueva, `fichas_integrante`, colgando de `GrupoFamiliar`.

### 2.1 Por qué cuelga del HOGAR y no de la vivienda ni de la encuesta

Podría colgar de cualquiera de las tres, y solo una es correcta:

| Opción | Por qué no |
|---|---|
| de la **vivienda** | en una casa con dos familias, las personas de cada una son de SU hogar; mezclarlas produciría un «hogar» de nueve personas que no existe y arruinaría el ingreso por persona de las dos |
| de la **encuesta** | la encuesta es el TRABAJO (quién la levanta, en qué estado va) y el hogar es el DATO; colgar las personas del trabajo volvería a mezclar lo que la HU-08 separó |
| del **hogar** ✅ | las personas son la composición del hogar, que es exactamente lo que el censo quiere saber |

### 2.2 Se guarda la FECHA DE NACIMIENTO, no la edad

Guardar «34» sería más simple y estaría mal a los pocos meses. **Una edad es un
dato que caduca; una fecha de nacimiento no.** Con la fecha, la edad se calcula
respecto a la que interese —hoy, o el día del operativo— y el histórico del censo
sigue siendo cierto años después.

Es la misma razón por la que `Operativo` guarda fechas y no «duración en días».

El cálculo corrige el caso borde comparando `(mes, día)`:

```python
referencia.year - nacimiento.year - (
    (referencia.month, referencia.day) < (nacimiento.month, nacimiento.day)
)
```

Sin esa corrección, alguien nacido el 30 de diciembre aparecería con un año de más
durante casi todo el año. Es el cálculo que se escribe mal una vez por proyecto,
y por eso está en el modelo y no repartido por las plantillas. Hay una prueba
dedicada: `test_la_edad_no_se_adelanta_antes_del_cumpleanos`.

---

## 3. Las cuatro restricciones

| Restricción | Qué garantiza |
|---|---|
| `integrante_parentesco_valido` | el parentesco es uno del catálogo |
| `integrante_sexo_valido` | el sexo es uno del catálogo |
| **`un_solo_jefe_por_hogar`** | único **entre los que son jefe de hogar** |
| **`rut_unico_en_el_hogar`** | único **entre los que tienen RUT** |

Las dos últimas son **índices únicos parciales**, la técnica que la HU-06 estrenó
con `asignacion_activa_unica`. Merecen explicación porque las dos resuelven el
mismo problema con condiciones distintas: **hacer única una situación concreta de
una columna sin hacer única la columna entera.**

### 3.1 `un_solo_jefe_por_hogar` — la más importante de la historia

```sql
UNIQUE (grupo_familiar_id) WHERE parentesco = 'JEFE_HOGAR'
```

Es la restricción de la que depende **todo el resto del formulario**: el parentesco
de cada persona se declara **respecto al jefe de hogar**. Con dos jefes, la columna
«parentesco» de todas las demás filas dejaría de significar algo — «hija» ¿de
cuál?

Una restricción `UNIQUE(grupo_familiar)` a secas impediría tener dos hijos. La
condición `WHERE parentesco = 'JEFE_HOGAR'` es lo que hace la diferencia.

Y no se deja solo a la base de datos: **el formulario retira la opción del
desplegable** cuando el hogar ya tiene jefe. Toparse con un `IntegrityError` es
peor experiencia que no ver una opción imposible. La excepción es editar al propio
jefe, donde la opción tiene que seguir estando o al guardar cualquier otro cambio
lo dejaría sin parentesco. Hay pruebas de los tres casos.

### 3.2 `rut_unico_en_el_hogar` — por qué también es parcial

```sql
UNIQUE (grupo_familiar_id, rut) WHERE rut <> ''
```

La misma persona no puede estar dos veces en el mismo hogar. Pero el RUT es
opcional (decisión heredada de la HU-08), así que **sin la condición dos personas
sin RUT chocarían entre sí por compartir la cadena vacía**, y el sistema impediría
registrar a una familia que no lleva los carnets encima.

El formulario lo comprueba antes, **sobre el RUT normalizado**: «12.345.678-5» y
«12345678-5» son el mismo, y sin normalizar pasarían como distintos hasta que el
modelo los guardara iguales y la base de datos reventara. Hay una prueba de eso
exactamente (`test_el_rut_repetido_se_detecta_aunque_venga_con_puntos`).

### 3.3 Lo que NO es una restricción, y por qué

Que la fecha de nacimiento no sea futura **no puede** ser un `CheckConstraint`:
dependería de la fecha de hoy y sería falsa mañana. Vive en `Integrante.clean()` y
en el formulario, que es donde puede ser cierta.

---

## 4. Los campos del censo de personas

| Campo | Obligatorio | Nota |
|---|---|---|
| `parentesco` | sí | respecto al jefe de hogar |
| `nombres`, `apellidos` | sí | mínimo dos caracteres cada uno |
| `rut` | no | validado con dígito verificador si se entrega |
| `sexo` | sí | incluye «prefiere no responder» |
| `fecha_nacimiento` | sí | ni futura ni de hace más de 120 años |
| `nivel_educacional` | **desde los 5 años** | |
| `situacion_ocupacional` | **desde los 15 años** | |
| `pueblo_originario` | sí (por defecto «ninguno») | autodeclarado |
| `tiene_discapacidad` | booleano | |
| `observaciones` | no | |

**El parentesco se mide respecto al jefe de hogar** y no entre todos con todos, que
es como lo hace el censo y como se puede preguntar en una puerta. La alternativa
—un grafo de relaciones familiares— daría más información y tardaría media hora por
hogar.

**«Prefiere no responder» es una opción explícita** en sexo y en pueblo originario,
no la ausencia de dato. La diferencia importa: un vacío no distingue a quien no
quiso contestar de la pregunta que el encuestador olvidó hacer, y **solo la primera
es una respuesta que hay que respetar**.

**«Labores del hogar» está separada de «no trabaja»** a propósito: son situaciones
distintas y confundirlas invisibiliza trabajo no remunerado, que en un operativo
social es justamente parte de lo que se quiere ver.

**Los pueblos originarios** son los nueve reconocidos por la Ley Indígena
N° 19.253 más el pueblo chango, incorporado en 2020 por la Ley N° 21.273. Es un
dato **autodeclarado**: vale lo que la persona dice, no lo que el encuestador
deduzca de su apellido.

---

## 5. La validación por edad

Es la validación que define esta historia, y la que justifica que
`nivel_educacional` y `situacion_ocupacional` admitan vacío en la columna:

> **No se le pregunta el nivel educacional a una guagua ni la situación
> ocupacional a un niño de siete años.**

| Edad | Escolaridad | Ocupación |
|---|---|---|
| 0-4 | no se pide | no se pide |
| 5-14 | **obligatoria** | no se pide |
| 15+ | **obligatoria** | **obligatoria** |

Los umbrales no son arbitrarios: 5 años es el ingreso a educación parvularia, y 15
la edad mínima legal para trabajar en Chile con autorización (Código del Trabajo,
art. 13).

**Se resuelve en `clean()` y no en `__init__`** porque la edad no se conoce hasta
que llegan los datos: en `__init__` todavía no hay fecha de nacimiento con la que
decidir. Es una regla que depende de OTRO campo del mismo formulario, y ese es
exactamente el trabajo de `clean()`.

La alternativa —exigirlos siempre— produciría dos errores opuestos y los dos malos:
pedir un dato que no existe para los niños, y aceptar el vacío en adultos si se
dejara opcional para todos.

**Detalle cuidado:** si no hay fecha de nacimiento, `clean()` no exige ninguno de
los dos. El error de la fecha ya se informó y apilarle dos más solo hace la
pantalla más difícil de leer.

---

## 6. Declaradas contra registradas

Aquí es donde `integrantes_declarados` de la HU-08 cobra sentido. Aquella historia
lo guardó argumentando que **«son dos datos distintos y su diferencia es
información»**, y esta es esa diferencia:

| Propiedad | Responde |
|---|---|
| `total_integrantes()` | cuántas personas hay registradas |
| `integrantes_pendientes` | cuántas faltan (nunca negativo) |
| `esta_completo` | ¿ya están todas? |
| `hay_discrepancia` | ¿hay MÁS de las declaradas? |

Tres situaciones, y la pantalla dice algo distinto en cada una:

- **Faltan personas** → barra azul y «faltan 3 por registrar».
- **Completo** → barra verde.
- **Hay más de las declaradas** → aviso ámbar. **No es un error**: en terreno la
  familia dice «somos cuatro» y al enumerar aparece la abuela de la pieza del
  fondo. Pero no puede pasar inadvertido, porque **el número declarado es el que
  divide el ingreso del hogar**, y la pantalla ofrece corregirlo.

`integrantes_pendientes` nunca es negativo, y es una decisión: devolver −2
obligaría a cada plantilla a acordarse de que el número puede serlo. Lo que sobra
no es «un pendiente en negativo», es una discrepancia, y tiene su propia
propiedad.

---

## 7. El nombre del jefe de hogar

El nombre del jefe de hogar vive en **dos sitios** y eso podría parecer una
duplicación descuidada. No lo es:

| Dónde | Qué es |
|---|---|
| `GrupoFamiliar.jefe_hogar_nombre` (HU-08) | la **identificación del hogar**, tomada en el primer contacto: «¿con quién hablo?». Etiqueta el hogar en los listados y sobrevive si la enumeración nunca se hace, que es el caso de un borrador |
| `Integrante` con parentesco `JEFE_HOGAR` (HU-09) | la **persona censada**, con su RUT, edad, escolaridad y ocupación |

Una es una etiqueta y el otro es un registro. El sistema los mantiene coherentes de
dos formas:

1. **Prellenando el formulario.** Si el hogar aún no tiene jefe registrado, la
   primera persona llega con el parentesco en «jefe de hogar» y con el nombre y el
   RUT que se tomaron en la HU-08. Sin el prellenado, el encuestador escribiría el
   nombre otra vez y en la mitad de los casos quedaría distinto —«Rosa Millán» y
   «Rosa Elena Millán Soto»— y el hogar diría dos cosas sobre la misma persona.
2. **Avisando si no coinciden.** `nombre_del_jefe_coincide` compara los dos en
   minúsculas y sin espacios sobrantes; la pantalla muestra un aviso informativo, y
   no bloquea nada, porque puede ser simplemente que al enumerar se anotara el
   nombre completo.

> El nombre se parte en nombres y apellidos **por la mitad**, y se sabe que es una
> heurística: en Chile lo habitual son dos nombres y dos apellidos. Por eso va en
> `initial` —un borrador editable— y la pantalla dice explícitamente «corrige lo
> que haga falta».

---

## 8. Vistas y URLs

| URL | Qué hace |
|---|---|
| `/encuestas/<pk>/integrantes/` | lista, avance y avisos |
| `/encuestas/<pk>/integrantes/nuevo/` | agregar una persona |
| `/encuestas/<pk>/integrantes/<id>/editar/` | corregir sus datos |
| `/encuestas/<pk>/integrantes/<id>/quitar/` | quitarla (GET confirma, POST ejecuta) |

### 8.1 Todas van anidadas bajo su encuesta, incluso las que actúan sobre una persona

Es **lo contrario** de lo que hizo la HU-05, donde «editar» no se anidaba porque el
sector ya sabía a qué operativo pertenecía. El motivo del cambio es concreto: aquí
la encuesta **no es un dato redundante, es la que decide el permiso**.

Con `/integrantes/<id>/editar/` suelto, la vista tendría que remontar la cadena
entera (integrante → hogar → encuesta → censista) para comprobar quién pregunta, y
esa comprobación se puede olvidar. Con la encuesta en la URL, **el filtro por dueño
se aplica antes de buscar a la persona** y no hay forma de llegar a una fila ajena.

### 8.2 Un mixin para las cuatro pantallas

`HogarDeLaEncuestaMixin` centraliza las tres comprobaciones que todas necesitan:
la encuesta es mía, tiene hogar registrado y admite cambios. Repetirlas en cuatro
vistas sería garantizar que a alguna le faltara una, y **la que faltara no daría
ningún error: solo dejaría escribir donde no se debe**.

### 8.3 Sin hogar registrado no hay integrantes

Si se entra a la pantalla de una encuesta que aún no tiene hogar, el sistema
redirige a registrarlo. **Es un orden real, no un capricho**: el parentesco se
declara respecto al jefe de hogar, y el jefe de hogar se identifica al registrar el
hogar. Sin ese paso, la primera pregunta del formulario no tendría respuesta
posible.

### 8.4 «Guardar y agregar otra»

Registrar seis personas seguidas es **la operación real** de esta pantalla. Con un
solo botón, cada una costaría tres toques: guardar, volver a la lista, pulsar
«agregar». El segundo botón devuelve un formulario vacío en el mismo sitio, y
convierte seis personas en seis formularios en vez de dieciocho toques.

---

## 9. Aquí sí se borra

**Es la excepción del proyecto y conviene poder defenderla.** OPSO desactiva en vez
de borrar en todas partes: cuentas (HU-03), comunas y sectores (HU-05),
asignaciones (HU-06). Esta vista borra la fila de verdad.

La regla que explica la diferencia: **se desactiva aquello cuyo pasado significa
algo.** Una asignación retirada explica por qué esa persona levantó esas fichas;
una comuna desactivada explica de dónde salieron los datos de 2026.

Una persona agregada por error a un hogar **no tiene pasado que explicar**. Es un
dato que se está capturando, todavía en borrador, que ningún supervisor ha validado
y que no sostiene ninguna otra fila. Conservarla «inactiva» obligaría a filtrar
«los integrantes que sí cuentan» en cada recuento del censo, y **la primera
consulta que se olvidara del filtro daría un hogar con una persona de más**.

Y hay un motivo más fuerte: son **datos personales de terceros**. Guardar
indefinidamente a una persona que no debía estar en la base, marcada como inactiva,
es exactamente lo que la minimización de datos pide no hacer (Ley N° 21.719).

Dos pasos —confirmar y ejecutar— por lo mismo que retirar una asignación en la
HU-06: si un GET pudiera borrar, un `<img src="...">` incrustado en cualquier
página lo ejecutaría con la sesión de quien la mirara. La pantalla de confirmación
lo dice sin rodeos: **«sus datos se borran, no se archivan»**.

Si se quita al jefe de hogar, el mensaje avisa de que el hogar quedó sin jefe y de
que el parentesco del resto perdió su referencia.

---

## 10. Templates e interfaz

| Plantilla | Qué es |
|---|---|
| `fichas/integrantes.html` | lista, barra de avance y avisos |
| `fichas/integrante_form.html` | alta y edición (la misma) |
| `fichas/integrante_quitar.html` | confirmación de retiro |

El formulario se agrupa en tres bloques, en el orden de la conversación real:

1. **Quién es** — parentesco, nombres, apellidos, RUT
2. **Datos básicos** — sexo, fecha de nacimiento
3. **Situación** — escolaridad, ocupación, pueblo originario, discapacidad

La fecha usa `type="date"`, así que el teléfono abre su propio selector: en terreno
es mucho más rápido y menos propenso a errores que escribir ocho dígitos con una
mano.

La lista pone al **jefe de hogar primero** y después de mayor a menor edad. Ese
orden no se puede pedir desde `Meta.ordering`: ordenar por la columna `parentesco`
daría el orden alfabético de sus códigos, que no significa nada. Se resuelve con un
`CASE` de SQL en `GrupoFamiliar.integrantes_ordenados()`, la misma técnica que
`ORDEN_POR_URGENCIA` en la HU-07.

---

## 11. Seguridad y datos personales

### 11.1 Sexta historia seguida sin agregar permisos

`fichas.crear` y `fichas.editar`, sembrados por la HU-04 y concedidos solo al rol
Censista. Un supervisor no puede registrar personas —ni con `fichas.ver_todas`—
porque no tiene el permiso, no porque una vista lo nombre.

### 11.2 Escribir exige ser el dueño de la encuesta

Ni siquiera `fichas.ver_todas` abre estas pantallas: escribir una persona en la
ficha de otro encuestador dejaría el dato atribuido a quien no estuvo en la
vivienda. Hay pruebas de 404 para encuesta ajena en las cuatro vistas.

### 11.3 Todo se comprueba en el servidor, en GET y en POST

| Regla | Dónde |
|---|---|
| la encuesta es mía | queryset con `censista=request.user` |
| el hogar existe | `comprobar_hogar_registrado()` |
| la encuesta admite cambios | `comprobar_abierta()`, en los dos verbos |
| la persona es de este hogar | `get_object_or_404(..., grupo_familiar=...)` |

### 11.4 Datos de personas que no eligieron estar en la base

Esta historia guarda nombre, RUT, edad, escolaridad, ocupación, discapacidad y
pertenencia a pueblo originario **de personas que no son usuarias del sistema**. Se
refleja en cuatro decisiones:

- el RUT sigue siendo opcional;
- «prefiere no responder» es una respuesta válida en sexo y pueblo originario;
- quitar a una persona **borra** sus datos, no los archiva;
- los nombres del comando de demostración son inventados y se nota que lo son.

---

## 12. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0003_integrantes_del_hogar.py
backend/templates/fichas/integrantes.html
backend/templates/fichas/integrante_form.html
backend/templates/fichas/integrante_quitar.html
backend/docs/HU-09_integrantes_del_hogar.md          este documento
```

### Modificados

```
backend/fichas/models.py     + Integrante y sus 5 catálogos; recuento en GrupoFamiliar
backend/fichas/forms.py      + IntegranteForm
backend/fichas/views.py      + 4 vistas y su mixin
backend/fichas/urls.py       + 4 rutas
backend/fichas/admin.py      + Integrante y su inline en el hogar
backend/fichas/tests.py      + 97 pruebas
backend/fichas/management/commands/crear_encuestas_demo.py   siembra personas
backend/templates/fichas/encuesta_detalle.html               + avance del hogar
backend/README.md · README.md
```

**Ninguna tabla existente cambió.** Es el dato que mejor resume la historia.

---

## 13. Pruebas

```bash
python manage.py test fichas          # 355 (HU-07, HU-08 y HU-09)
python manage.py test                 # 901 en total
```

| Bloque | Qué comprueba |
|---|---|
| `IntegranteModeloTest` | edad y su caso borde, edad a una fecha dada, CASCADE en cadena |
| `IntegranteRestriccionesTest` | dos jefes no, dos hijos sí, RUT repetido, fecha futura |
| `RecuentoDelHogarTest` | pendientes, completo, discrepancia, orden con el jefe primero |
| `NombreDelJefeTest` | coincidencia sin distinguir mayúsculas ni espacios |
| `IntegranteFormTest` | las reglas por edad en los tres tramos, RUT normalizado, jefe oculto |
| `IntegrantesPantallaTest` | avance, avisos, sin hogar redirige, 404 ajena |
| `RegistrarIntegranteTest` | prellenado, «guardar y seguir», encuesta cerrada, supervisor |
| `EditarIntegranteTest` | corrige sin duplicar, 404 para persona de otro hogar |
| `QuitarIntegranteTest` | GET no borra, POST sí, aviso al quitar al jefe |
| `FichaConIntegrantesTest` | lo que gana la ficha de la HU-07 |
| `ConsultasIntegrantesTest` | el coste no crece con el número de personas |
| `IntegracionHU09Test` | recorrido completo, incluido que Juan no puede tocar nada |

---

## 14. Explicación para la defensa

**En una frase:** la HU-08 dijo «viven seis»; la HU-09 registra a las seis, y el
sistema avisa mientras falten.

**Las tres cosas que conviene poder defender:**

1. **El índice único parcial del jefe de hogar.** Es la restricción de la que
   depende todo el formulario: el parentesco de cada persona se mide respecto al
   jefe, así que dos jefes dejarían sin sentido la columna de todos los demás.
   Misma técnica que la HU-06, problema distinto.
2. **La validación por edad.** Escolaridad desde los 5 y ocupación desde los 15,
   decidido con la fecha que se acaba de escribir. Es lo que evita pedir un dato
   que no existe sin tener que dejarlo opcional para todo el mundo.
3. **Que aquí sí se borra.** Es la única excepción del proyecto y tiene dos
   motivos: una persona agregada por error no tiene pasado que explicar, y son
   datos personales de terceros que no deben conservarse «por si acaso».

**Lo que demuestra el diseño del proyecto:** esta historia **no cambió ninguna
tabla existente**. La HU-08 predijo que los integrantes cabrían colgando del hogar,
y cupieron. Cuando el corte anterior está bien hecho, la historia siguiente solo
agrega.

---

## 15. Posibles preguntas del profesor

**¿Por qué los integrantes cuelgan del hogar y no de la vivienda?**
Porque en una casa con dos familias las personas son de su hogar. Colgándolas de la
vivienda saldría un hogar de nueve personas que no existe, y el ingreso por persona
de las dos familias quedaría mal calculado.

**¿Por qué guardas la fecha de nacimiento y no la edad?**
Porque una edad caduca. Con la fecha, la edad se calcula respecto a cualquier
momento y el histórico sigue siendo cierto años después.

**¿Qué impide que un hogar tenga dos jefes?**
Un índice único parcial en PostgreSQL, `WHERE parentesco = 'JEFE_HOGAR'`. Un UNIQUE
normal impediría tener dos hijos. Además el formulario esconde la opción cuando ya
hay uno, para que nadie se tope con un error de base de datos.

**¿Por qué el nombre del jefe está en dos tablas?**
Porque son dos cosas: la etiqueta con que se identificó el hogar en el primer
contacto, y la persona censada con todos sus datos. El sistema prellena la segunda
con la primera y avisa si dejan de coincidir.

**¿Por qué la escolaridad no es obligatoria en la base de datos?**
Porque para un niño de dos años no existe. Es obligatoria en el formulario y solo a
partir de los 5 años, que es cuando la pregunta tiene respuesta.

**¿No contradice el proyecto que aquí se borre?**
No: se desactiva lo que tiene pasado que explicar. Una persona agregada por error a
un borrador no lo tiene, y conservar datos personales de alguien que no debía estar
en el registro es justo lo contrario de lo que exige la minimización de datos.

**¿Qué pasa si la familia declaró cuatro personas y registras seis?**
Se registran las seis y el sistema avisa: no es un error, pero el número declarado
es el que divide el ingreso del hogar, así que ofrece corregirlo.

**¿Un supervisor puede registrar integrantes?**
No. No tiene `fichas.crear`, y aunque lo tuviera, estas vistas solo abren encuestas
propias: el dato tiene que quedar atribuido a quien estuvo en la puerta.

---

## 16. Conclusión técnica

La HU-09 agrega **una tabla, cuatro pantallas, ningún permiso y ninguna migración
de datos**. Cierra el recorrido que empezó en las regiones de la HU-05 y llega
hasta la persona.

Su valor técnico está en tres cosas:

1. **Confirma el diseño de la HU-08.** Ninguna tabla existente cambió. La historia
   anterior había predicho exactamente esto por escrito.
2. **Usa la restricción correcta para cada caso.** Dos índices únicos parciales con
   condiciones distintas, cada uno resolviendo un problema que un UNIQUE normal
   habría empeorado.
3. **Modela reglas del mundo real, no del programa.** Escolaridad desde los 5,
   ocupación desde los 15, parentesco respecto al jefe, «prefiere no responder»
   como respuesta y no como vacío. Todas se pueden explicar sin hablar de código.

Lo que queda del sprint: el **cierre explícito de la encuesta y el guardado de
borradores** (HU-10), la **ubicación GPS** (HU-11) y las **fotografías** (HU-12).
Las tres siguen sin necesitar cambios en el modelo: el GPS y las fotos cuelgan de
`Vivienda`, y el borrador es un estado de `Encuesta` que existe desde la HU-07.
