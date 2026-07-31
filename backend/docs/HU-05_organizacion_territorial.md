# HU-05 · Comunas, sectores y zonas

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como administrador, quiero administrar comunas, sectores y zonas para organizar el operativo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **141 pruebas automáticas** propias (422 en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no reimplementa nada** de las anteriores. Reutiliza el
> `PermisoRequeridoMixin` de la HU-04, los permisos `operativos.ver` y
> `operativos.gestionar` **ya sembrados** por esa misma historia, la bitácora
> `RegistroAuditoria` de la HU-03 y su función `describir_cambios()`, y el
> fragmento de plantilla `_campo.html`. Lo nuevo es el **modelo territorial** y su
> interfaz de administración.

---

## Índice

1. [Explicación inicial: ¿por qué hace falta modelar el territorio?](#1-explicación-inicial)
2. [El modelo de datos y sus dos mitades](#2-el-modelo-de-datos)
3. [Base de datos PostgreSQL y diagrama entidad-relación](#3-base-de-datos-postgresql)
4. [El ciclo de vida del operativo](#4-el-ciclo-de-vida-del-operativo)
5. [Formularios y validaciones](#5-formularios-y-validaciones)
6. [Vistas](#6-vistas)
7. [URLs](#7-urls)
8. [Templates e interfaz](#8-templates-e-interfaz)
9. [Seguridad y control de acceso](#9-seguridad-y-control-de-acceso)
10. [Auditoría: la revisión de una decisión anterior](#10-auditoría)
11. [Migraciones](#11-migraciones)
12. [Rendimiento: el problema N+1](#12-rendimiento)
13. [Archivos creados y modificados](#13-archivos-creados-y-modificados)
14. [Pruebas](#14-pruebas)
15. [Explicación para la defensa](#15-explicación-para-la-defensa)
16. [Posibles preguntas del profesor](#16-posibles-preguntas-del-profesor)
17. [Conclusión técnica](#17-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 ¿Por qué hace falta modelar el territorio?

Porque **un operativo social es, antes que nada, un problema de reparto de
terreno**. Un censo no fracasa por falta de formularios: fracasa cuando dos
censistas visitan la misma cuadra y nadie visita la de al lado.

Hasta la HU-04, OPSO sabía *quién* podía hacer *qué*. No sabía **dónde**. Sin
esa dimensión no se puede responder ninguna de las preguntas que realmente se
hace un coordinador:

| Pregunta | Sin modelo territorial | Con modelo territorial |
|---|---|---|
| ¿A quién le toca esta cuadra? | Se decide en terreno, verbalmente | Está registrado en una zona |
| ¿Cuánto falta? | «Ya vamos avanzando» | 3 de 5 zonas del sector |
| ¿Está bien repartido el trabajo? | No se puede saber | Se ve: un sector con 9 zonas junto a otro con 1 |
| ¿Dónde se levantó esta ficha? | En una comuna, aproximadamente | Zona → sector → comuna → región |

### 1.2 ¿Por qué tres niveles y no uno?

Porque cada nivel responde una pregunta distinta, y colapsarlos haría perder
información que se necesita.

- **La comuna** es la unidad **administrativa y de reporte**. Es lo que un
  municipio o el Estado va a pedir: «¿cuántas familias levantaron en Concepción?».
- **El sector** es la unidad de **asignación**: lo que se le encarga a una persona
  o a un equipo. Coincide con cómo la gente nombra su territorio («Los Boldos»),
  no con una división oficial.
- **La zona** es la unidad de **jornada**. Un sector de 400 viviendas no es una
  tarea, es un objetivo de varios días; la zona lo parte en pedazos abarcables
  («manzanas 1 a 8»).

Ese tercer nivel es el que permite medir el avance con grano fino. «Vamos 3 de 5
zonas» es información útil; «vamos 0 de 1 sector» no dice nada durante tres días.

Se llega hasta ahí y no más: un cuarto nivel (la manzana, la vivienda) ya es el
objeto de la **ficha de familia**, no de la organización del operativo.

### 1.3 ¿Por qué las comunas se administran y las regiones no?

Es la misma pregunta que la HU-04 resolvió con los roles, aplicada a los datos
geográficos, y la respuesta depende de **quién es la autoridad** sobre el dato.

| | Región | Comuna |
|---|---|---|
| ¿Quién la define? | La ley chilena | OPSO decide dónde trabaja |
| ¿Cuántas hay? | 16, fijas | 346 en Chile, OPSO usa un puñado |
| ¿Se pueden crear? | **No.** Se siembran por migración | **Sí.** CRUD completo |
| ¿Para qué sirven? | Agrupar y ordenar | Ubicar el trabajo real |

Ofrecer un botón «crear región» invitaría a inventar una, y eso solo puede
ensuciar los datos. Si el Estado creara una región nueva, se agrega con una
**migración de datos**, que es la forma correcta de versionar un cambio legal:
queda en Git, con fecha y autor.

Al revés, sembrar las 346 comunas obligaría al administrador a buscar entre 346
opciones las 4 que le interesan, y a los reportes a mostrar 342 comunas sin una
sola ficha. Dar de alta solo las que se usan mantiene la lista corta y
significativa: *estas son las comunas de OPSO*.

---

## 2. El modelo de datos

### 2.1 La jerarquía se parte en dos mitades

Esta es **la decisión central de la historia**:

```
    Region ──< Comuna                  GEOGRAFÍA: existe con o sin OPSO
                  │
    Operativo ──< Sector ──< Zona      ORGANIZACIÓN: existe porque hay un operativo
```

Arriba está la **geografía de Chile**. La Región del Biobío y la comuna de
Concepción existen independientemente de que se haga un censo. Son datos estables,
y por eso se guardan una vez y se reutilizan en todos los operativos.

Abajo está la **organización del trabajo**. «Los Boldos» no es una entidad
geográfica oficial: es un pedazo de Concepción que *este* operativo decidió tratar
como una unidad.

### 2.2 ¿Por qué el sector cuelga del operativo y no solo de la comuna?

Es la pregunta más probable de la defensa, y tiene una respuesta concreta.

La división del terreno es una **decisión de planificación**, y las decisiones de
planificación cambian entre un operativo y el siguiente. En el censo de 2026 puede
convenir tratar «Los Boldos» como un solo sector; en 2027, con más censistas,
partirlo en tres.

Si el sector fuera geografía permanente (`Comuna ──< Sector`), redividir la comuna
en 2027 **reescribiría el pasado**: las fichas levantadas en 2026 apuntarían a una
división que en 2026 no existía, y el histórico quedaría mintiendo sobre dónde
trabajó cada censista.

Colgándolo del operativo, cada uno conserva su propia foto del territorio y los
datos históricos siguen siendo verdad. La consecuencia práctica y comprobable es
que **dos operativos pueden tener un sector «Los Boldos»** sin conflicto, y hay una
prueba que lo verifica (`test_dos_operativos_si_pueden_tener_un_sector_con_el_mismo_nombre`).

### 2.3 ¿Por qué `Sector` tiene DOS claves foráneas?

```python
operativo = models.ForeignKey(Operativo, on_delete=models.CASCADE, ...)
comuna    = models.ForeignKey(Comuna,    on_delete=models.PROTECT, ...)
```

Ninguna es redundante y conviene poder explicarlo:

- No se puede deducir la comuna del operativo, porque **un operativo abarca varias
  comunas**.
- No se puede deducir el operativo de la comuna, porque **una comuna aparece en
  varios operativos**.

El sector es precisamente **el cruce de ambas cosas**.

### 2.4 CASCADE y PROTECT en la misma tabla: no es una inconsistencia

| Relación | Comportamiento | Por qué |
|---|---|---|
| `Sector.operativo` | `CASCADE` | Un sector no significa nada sin su operativo: es una división **de** ese operativo. Si el operativo se borra, sus sectores se van con él. |
| `Sector.comuna` | `PROTECT` | La comuna es **geografía compartida**. Borrarla mientras tenga sectores los dejaría sin ubicación, así que PostgreSQL lo impide. |
| `Zona.sector` | `CASCADE` | Misma lógica que el operativo: una zona es una subdivisión de un sector concreto. |
| `Comuna.region` | `PROTECT` | Borrar una región dejaría comunas sin ubicación. |
| `Operativo.creado_por` | `SET_NULL` | Si se elimina la cuenta del administrador, el operativo debe sobrevivir. Mismo criterio que la bitácora de la HU-03. |

En vez de borrar, la interfaz **desactiva** (borrado lógico), que es la misma
decisión que la HU-03 tomó con las cuentas de usuario y por la misma razón: los
datos del censo cuelgan de estas filas.

### 2.5 Region: ¿por qué una tabla y no `TextChoices`?

El proyecto usa las dos formas, y el criterio para elegir es **quién consulta el
valor**:

| | Se modela como | Ejemplo |
|---|---|---|
| El **código** lo compara con un `if` | `TextChoices` | `RolCodigo`, `EstadoOperativo` |
| Es un **dato** que el usuario elige | Tabla | `Rol`, `Region`, `Comuna` |

Ninguna regla de negocio de OPSO depende de que una región sea la del Biobío: la
región es un dato que se elige en un desplegable. En cambio `EstadoOperativo` sí se
compara en el código (`if operativo.esta_cerrado`), y un valor que el código
compara debe ser una constante, no una fila que alguien pueda renombrar y romper el
`if`.

El texto libre queda descartado por un motivo práctico: «Biobío», «Bío-Bío»,
«BIOBIO» y «VIII Región» serían cuatro regiones distintas, y agrupar las comunas
—que es justo lo que hace útil el listado— dejaría de funcionar en cuanto dos
personas la escribieran diferente. La clave foránea lo hace imposible.

---

## 3. Base de datos PostgreSQL

### 3.1 Tablas creadas

| Tabla | Contenido | Filas típicas |
|---|---|---|
| `operativos_region` | Las 16 regiones de Chile | 16, fijas |
| `operativos_comuna` | Comunas donde OPSO opera | Unas pocas |
| `operativos_operativo` | Despliegues con sus fechas | Una por año |
| `operativos_sector` | División de una comuna en un operativo | Decenas |
| `operativos_zona` | División de un sector | Cientos |

### 3.2 Diagrama entidad-relación

```
┌──────────────────────┐
│ operativos_region    │   16 filas sembradas por migración
├──────────────────────┤
│ id            PK     │
│ codigo        UNIQUE │  código INE: "08"
│ nombre        UNIQUE │
│ orden                │  norte → sur
└──────────┬───────────┘
           │ 1
           │
           │ N          PROTECT
┌──────────┴───────────┐
│ operativos_comuna    │
├──────────────────────┤
│ id            PK     │
│ region_id     FK     │
│ nombre               │
│ activa               │  borrado lógico
│ creado_en            │
│ actualizado_en       │
│ UNIQUE (region, nombre)
└──────────┬───────────┘
           │ 1
           │                         ┌──────────────────────────┐
           │                         │ operativos_operativo     │
           │                         ├──────────────────────────┤
           │                         │ id                PK     │
           │                         │ nombre            UNIQUE │
           │                         │ descripcion              │
           │                         │ fecha_inicio             │
           │                         │ fecha_termino            │
           │                         │ estado                   │
           │                         │ creado_por_id     FK ────┼──> usuarios_usuario
           │                         │ CHECK termino >= inicio  │      (SET_NULL)
           │                         │ CHECK estado válido      │
           │                         └───────────┬──────────────┘
           │ N                                   │ 1
           │ PROTECT                             │ N   CASCADE
        ┌──┴─────────────────────────────────────┴──┐
        │ operativos_sector                         │
        ├───────────────────────────────────────────┤
        │ id                PK                      │
        │ operativo_id      FK  (CASCADE)           │
        │ comuna_id         FK  (PROTECT)           │
        │ nombre                                    │
        │ descripcion                               │
        │ activo                                    │
        │ UNIQUE (operativo, comuna, nombre)        │
        └───────────────────┬───────────────────────┘
                            │ 1
                            │ N   CASCADE
              ┌─────────────┴─────────────┐
              │ operativos_zona           │
              ├───────────────────────────┤
              │ id                PK      │
              │ sector_id         FK      │
              │ nombre                    │
              │ descripcion               │
              │ viviendas_estimadas  NULL │
              │ activa                    │
              │ UNIQUE (sector, nombre)   │
              └───────────────────────────┘
```

### 3.3 Restricciones que garantiza PostgreSQL

Estas valen **incluso si alguien inserta con SQL directo** o escribe un script de
carga masiva que no pase por los formularios. Es la diferencia entre una regla y
una sugerencia.

| Restricción | Qué impide |
|---|---|
| `operativo_fechas_coherentes` | Un operativo que termine antes de empezar |
| `operativo_estado_valido` | Un estado que no sea uno de los tres |
| `comuna_unica_por_region` | Dos comunas homónimas en la misma región |
| `sector_unico_por_operativo_y_comuna` | Repetir un sector dentro del mismo operativo |
| `zona_unica_por_sector` | Repetir una zona dentro del mismo sector |

**Detalle fino sobre `comuna_unica_por_region`:** no es `unique=True` sobre el
nombre. En Chile hay nombres de comuna repetidos en regiones distintas, así que la
restricción correcta es el **par** `(región, nombre)`. Hay una prueba para cada
lado de la regla: el duplicado se rechaza dentro de la región y se acepta entre
regiones.

### 3.4 Índices creados

| Índice | Consulta que acelera |
|---|---|
| `idx_comuna_activa` | «Comunas activas», que es lo que pide cada desplegable |
| `idx_sector_operativo` | «Sectores de este operativo», la ficha del operativo |
| `idx_zona_sector` | «Zonas de este sector», el árbol territorial |

---

## 4. El ciclo de vida del operativo

### 4.1 Los tres estados

```
      ┌──────────────────┐
      │  PLANIFICACIÓN   │  se arma el territorio, nadie en terreno
      └────┬────────┬────┘
           │        │
           ▼        │
      ┌─────────┐   │
   ┌──│ EN CURSO│   │       hay censistas trabajando
   │  └────┬────┘   │
   │       │        │
   │       ▼        ▼
   │  ┌──────────────────┐
   └──│     CERRADO      │  histórico: el territorio queda CONGELADO
      └──────────────────┘
```

Las transiciones válidas viven en **un solo lugar**,
`CambiarEstadoOperativoForm.TRANSICIONES`:

| Desde | Se puede pasar a | Por qué |
|---|---|---|
| En planificación | En curso, Cerrado | Empieza el terreno, o se cancela |
| En curso | Cerrado, En planificación | Termina, o se inició por error y se posterga |
| Cerrado | En curso | Se puede **reabrir**, pero no volver a planificar algo donde ya se trabajó |

### 4.2 ¿Por qué un formulario y no tres botones?

Porque con tres botones la regla viviría en **dos sitios**: la plantilla decidiría
qué botón mostrar y la vista qué aceptar. Es exactamente así como se produce la
incoherencia de que la interfaz oculte una opción que la vista sí acepta, o al
revés. Un formulario que calcula las opciones válidas concentra la regla en un
lugar y la plantilla solo dibuja.

### 4.3 El estado cerrado congela el territorio

Es la **regla de negocio más importante** de esta historia. Un operativo cerrado no
admite cambios en su división territorial, porque hacerlo falsearía la información
con la que efectivamente se trabajó.

La implementa `OperativoAbiertoMixin`, y hay un detalle de diseño que conviene
poder explicar: **el orden de herencia importa**.

```python
class SectorCreateView(GestionTerritorialMixin, OperativoAbiertoMixin, CreateView):
```

`dispatch()` se encadena siguiendo el orden de resolución de métodos. Con este
orden, el de `GestionTerritorialMixin` corre primero, comprueba el permiso, y solo
entonces llama al de `OperativoAbiertoMixin`. **Al revés**, un usuario sin permiso
averiguaría si un operativo existe y en qué estado está por la diferencia entre
los mensajes de error. Es una fuga de información pequeña, pero gratuita de evitar,
y hay una prueba que lo verifica
(`test_sin_permiso_se_avisa_del_permiso_y_no_del_estado`).

Nótese que **editar los datos** de un operativo cerrado sí está permitido:
corregir una fecha mal escrita o completar la descripción es legítimo y no altera
el territorio.

---

## 5. Formularios y validaciones

### 5.1 Las tres capas de validación, y por qué no son redundancia

| Capa | Dónde | Qué protege | Vale para |
|---|---|---|---|
| 1. Restricciones | `Meta.constraints` | Los **datos** | Todo, incluido SQL directo |
| 2. `Model.clean()` | El modelo | Las **reglas** | Formularios, `/admin/`, comandos, pruebas |
| 3. `Form.clean()` | Los formularios | La **experiencia de uso** | Solo la interfaz web |

La tercera capa parece duplicar la segunda, y hay una razón concreta para
tenerla. `Operativo.clean()` ya comprueba la coherencia de las fechas, pero cuando
la validación vive solo en el modelo, **Django coloca el error como error general
del formulario** y la plantilla lo muestra arriba, lejos del campo.
Comprobándolo también en el formulario, el mensaje sale debajo de «fecha de
término», que es donde el administrador está mirando. Hay una prueba para eso:
`test_el_error_de_fechas_va_en_el_campo_y_no_arriba`.

### 5.2 Validaciones implementadas

| Validación | Dónde | Por qué |
|---|---|---|
| Fechas coherentes | Modelo + formulario | Ver arriba |
| Comuna no duplicada en la región | Formulario + BD | Sin la capa del formulario, el duplicado daría un `IntegrityError` → error 500, no un mensaje |
| Sector no duplicado en `(operativo, comuna)` | Formulario + BD | Ídem |
| Zona no duplicada en el sector | Formulario + BD | Ídem |
| Nombres sin espacios sobrantes | `clean_nombre()` | «Concepción » y «Concepción» serían dos comunas para PostgreSQL |
| Viviendas estimadas ≠ 0 | `clean_viviendas_estimadas()` | Ver 5.3 |
| Transición de estado válida | `clean_estado()` | Segunda comprobación contra una petición manipulada |

### 5.3 Un detalle que conviene poder explicar: por qué se rechaza el 0

`PositiveIntegerField` ya impide los negativos, pero **acepta el 0**. Una zona con
cero viviendas estimadas no es un dato, es un error de tipeo: si no se sabe cuántas
hay, el campo se deja **vacío** (es opcional), que es distinto de afirmar que no hay
ninguna. El mensaje lo dice explícitamente en vez de rechazar sin explicar.

### 5.4 El caso borde de la comuna desactivada

Este es el tipo de detalle que solo aparece al usar el sistema, y está resuelto y
probado.

Los desplegables de comuna ofrecen **solo las activas**. Pero si un sector se creó
en una comuna que después se desactivó, al editarle el nombre el desplegable no
incluiría su propia comuna, el campo quedaría inválido y **sería imposible guardar
el sector**.

La solución es incluir la comuna actual además de las activas:

```python
disponibles = Q(activa=True)
if self.instance.pk and self.instance.comuna_id:
    disponibles |= Q(pk=self.instance.comuna_id)
```

Prueba: `test_al_editar_se_ofrece_su_propia_comuna_aunque_este_desactivada`.

### 5.5 El operativo y el sector no son campos del formulario

En `SectorForm` el operativo viene de la URL; en `ZonaForm`, el sector. Es una
decisión de **seguridad y usabilidad a la vez**:

- **Seguridad:** un campo oculto con el identificador se puede manipular, y crearía
  sectores en un operativo que el administrador no estaba mirando. Tomándolo de la
  URL, la vista lo carga con `get_object_or_404` y comprueba su estado antes de
  aceptar nada.
- **Usabilidad:** quien está dentro de un operativo ya eligió el operativo. Un
  desplegable para volver a elegirlo es un paso de más y una oportunidad de
  equivocarse.

---

## 6. Vistas

### 6.1 Las 13 vistas y su permiso

| Vista | URL | Permiso |
|---|---|---|
| `OperativoListView` | `/operativos/` | `operativos.ver` |
| `OperativoDetailView` | `/operativos/<pk>/` | `operativos.ver` |
| `ComunaListView` | `/operativos/comunas/` | `operativos.ver` |
| `OperativoCreateView` | `/operativos/nuevo/` | `operativos.gestionar` |
| `OperativoUpdateView` | `/operativos/<pk>/editar/` | `operativos.gestionar` |
| `OperativoCambiarEstadoView` | `/operativos/<pk>/estado/` | `operativos.gestionar` |
| `ComunaCreateView` | `/operativos/comunas/nueva/` | `operativos.gestionar` |
| `ComunaUpdateView` | `.../comunas/<pk>/editar/` | `operativos.gestionar` |
| `ComunaCambiarEstadoView` | `.../comunas/<pk>/(des)activar/` | `operativos.gestionar` |
| `SectorCreateView` | `/operativos/<pk>/sectores/nuevo/` | `operativos.gestionar` |
| `SectorUpdateView` | `.../sectores/<pk>/editar/` | `operativos.gestionar` |
| `SectorCambiarEstadoView` | `.../sectores/<pk>/(des)activar/` | `operativos.gestionar` |
| `ZonaCreateView` / `ZonaUpdateView` / `ZonaCambiarEstadoView` | `.../zonas/...` | `operativos.gestionar` |

### 6.2 Los mixins propios de la app

| Mixin | Responsabilidad |
|---|---|
| `ConsultaTerritorialMixin` | Puerta de las pantallas que leen (`operativos.ver`) |
| `GestionTerritorialMixin` | Puerta de las pantallas que modifican (`operativos.gestionar`) |
| `OperativoAbiertoMixin` | Regla **por objeto**: un operativo cerrado no admite cambios |
| `ObjetoCacheadoMixin` | `get_object()` cuesta una sola consulta por petición |

`ObjetoCacheadoMixin` existe por una razón concreta: `OperativoAbiertoMixin`
necesita el objeto en `dispatch()` para saber a qué operativo pertenece, y después
`UpdateView` vuelve a pedirlo para el formulario. Sin la caché, cada edición
costaría **dos consultas idénticas**. Se resuelve con `cached_property`, que guarda
el resultado en la instancia de la vista; Django crea una instancia nueva por
petición, así que no hay riesgo de que un objeto se filtre entre usuarios.

### 6.3 Una clase para dos operaciones opuestas

`ComunaCambiarEstadoView`, `SectorCambiarEstadoView` y `ZonaCambiarEstadoView`
atienden **activar y desactivar** con la misma clase. El atributo `activar` se fija
en `urls.py`:

```python
path("comunas/<int:pk>/desactivar/",
     views.ComunaCambiarEstadoView.as_view(activar=False), name="comuna_desactivar"),
path("comunas/<int:pk>/activar/",
     views.ComunaCambiarEstadoView.as_view(activar=True), name="comuna_activar"),
```

Así la validación y la auditoría no se escriben dos veces. Es el mismo patrón que
`CambiarEstadoUsuarioView` en la HU-03.

### 6.4 GET muestra, POST ejecuta

Todas las operaciones que modifican datos van en dos pasos, por la misma razón que
la HU-03 documentó: **las peticiones GET deben ser seguras e idempotentes** (regla
de HTTP). Si se pudiera cerrar un operativo con un GET, bastaría con insertar
`<img src=".../estado/">` en cualquier página para que el navegador de un
administrador con sesión abierta lo ejecutara sin que lo notara: es un ataque
**CSRF**. Con POST y token es imposible, y hay pruebas que lo verifican.

---

## 7. URLs

### 7.1 La estructura

```
/operativos/                          listado
/operativos/nuevo/                    alta
/operativos/comunas/                  catálogo de comunas
/operativos/comunas/nueva/
/operativos/comunas/5/editar/
/operativos/5/                        ficha con su territorio
/operativos/5/editar/
/operativos/5/estado/
/operativos/5/sectores/nuevo/         crear sector EN el operativo 5
/operativos/sectores/9/editar/
/operativos/sectores/9/zonas/nueva/   crear zona EN el sector 9
/operativos/zonas/12/editar/
```

### 7.2 Dos decisiones de diseño

**1. CREAR va anidado; EDITAR no.** Para crear un sector hace falta saber en qué
operativo, y ese dato viaja en la dirección. Para editar el sector 9 no hace falta
repetir el operativo, porque el propio sector ya sabe a cuál pertenece. Anidarlo
igualmente (`/operativos/5/sectores/9/editar/`) permitiría que alguien escribiera
un operativo que no corresponde y obligaría a validar la coherencia en cada vista:
**menos datos en la URL es menos que verificar**.

**2. Las rutas fijas van antes de las que llevan `<int:pk>`.** Django recorre la
lista en orden y se queda con la primera que coincide. El conversor `int` nunca
haría coincidir la palabra «comunas», así que hoy funcionaría igual, pero el orden
explícito deja claro cuál manda si mañana el conversor cambiara a `<str>`.

---

## 8. Templates e interfaz

### 8.1 Archivos creados

| Plantilla | Pantalla |
|---|---|
| `operativo_list.html` | Listado con buscador, filtro y paginación |
| `operativo_detail.html` | **Ficha con el árbol territorial completo** |
| `operativo_form.html` | Alta y edición |
| `operativo_estado.html` | Confirmación del cambio de estado |
| `comuna_list.html` | Catálogo de comunas |
| `comuna_form.html` | Alta y edición |
| `comuna_confirmar_estado.html` | Confirmación de activar/desactivar |
| `sector_form.html`, `sector_confirmar_estado.html` | Sectores |
| `zona_form.html`, `zona_confirmar_estado.html` | Zonas |
| `_paginacion.html`, `_estado_operativo.html` | Fragmentos reutilizables |

### 8.2 ¿Por qué el árbol en una sola página?

Porque la pregunta que se hace quien planifica no es «¿qué zonas tiene el sector
9?» sino **«¿está bien repartido el trabajo?»**. Y esa se responde *viendo* la forma
del reparto: un sector con nueve zonas junto a otro con una salta a la vista de
inmediato. Con una pantalla por nivel habría que abrir cinco pestañas y recordar lo
que decía cada una.

Es el mismo razonamiento con que la HU-04 eligió una **matriz** de permisos en vez
de una pantalla por rol: hacer visible de un vistazo lo que se está comparando.

### 8.3 El agrupado se hace en la vista, no en la plantilla

El lenguaje de plantillas de Django **no agrupa**, y forzarlo llevaría a inventar
filtros propios. `OperativoDetailView.agrupar_por_comuna()` prepara la estructura y
la plantilla queda en dos bucles anidados:

```python
[{"comuna": <Comuna>, "sectores": [<Sector>, ...]}, ...]
```

Es la misma decisión que la matriz de la HU-04 documentó.

### 8.4 Los fragmentos reutilizados

`_campo.html` **se reutiliza de la HU-03** en vez de escribir uno propio: resuelve
la etiqueta, el asterisco de obligatorio, el texto de ayuda y los errores junto al
campo, que es exactamente lo que hace falta aquí. Copiarlo habría duplicado 30
líneas para no cambiar nada.

`_paginacion.html` y `_estado_operativo.html` son nuevos y siguen el mismo criterio:
la barra de paginación son 35 líneas con la lógica de la ventana de páginas, y
repetirla en dos listados garantizaría que una corrección se hiciera en uno y se
olvidara en el otro.

### 8.5 El filtro de plantilla `tiene_permiso`

El enlace «Operativos» del menú **no va dentro del bloque por rol**: se muestra
según el permiso. Pero el lenguaje de plantillas de Django no permite llamar a un
método con argumentos:

```django
{% if user.tiene_permiso("operativos.ver") %}   ✗ error de sintaxis
```

La salida prevista por Django para ese caso es un **filtro**, y eso es
`usuarios/templatetags/permisos.py`:

```django
{% load permisos %}
{% if user|tiene_algun_permiso:"operativos.ver,operativos.gestionar" %}
```

**Por qué un filtro y no las alternativas:**

- *Una bandera en el contexto de cada vista*: `base.html` no pertenece a ninguna
  vista, la heredan **todas**. Cada vista del proyecto tendría que recordar pasarla,
  y la primera que se olvidara dejaría el menú incompleto sin que nadie lo notara.
- *Un context processor*: se ejecutaría en cada petición, incluidas las que no
  dibujan el menú, consultando permisos que quizá nadie va a mirar.

El filtro **delega** en `Usuario.tiene_permiso()` y no reimplementa ninguna regla:
un filtro que decidiera por su cuenta podría contradecir a la vista, y el usuario
vería un enlace que al pulsarlo lo rechaza.

> **Esto no es seguridad.** Ocultar un enlace es comodidad: evita ofrecer una
> pantalla que va a responder «no tienes permiso». La seguridad real está en las
> vistas, porque la URL siempre se puede escribir a mano.

---

## 9. Seguridad y control de acceso

### 9.1 Las tres capas

| Capa | Mecanismo | Qué comprueba |
|---|---|---|
| 1 | `LoginRequiredMiddleware` | Que haya sesión |
| 2 | `PermisoRequeridoMixin` | El permiso que la vista declara |
| 3 | `OperativoAbiertoMixin` | Que **este** operativo admita cambios |

La capa 3 es la que impide la «modificación por URL»: no basta con poder gestionar
territorio, el operativo concreto también tiene que admitirlo. **Ningún permiso de
la matriz puede saltarse esa comprobación.**

### 9.2 Cero permisos nuevos: la HU-04 cobrándose sola

Este es el punto más fuerte que la historia aporta a la defensa.

La HU-05 **no agregó ni una fila** al catálogo de permisos. Los que usa
—`operativos.ver` y `operativos.gestionar`— los sembró la migración
`0005_permisos_iniciales` de la HU-04, con esta descripción:

> «Definir el operativo, sus fechas y **la división territorial**.»

Es decir: la autorización de esta historia estaba **modelada antes de que
existieran las pantallas**. Y el reparto inicial ya le daba `operativos.ver` al rol
Supervisor, así que el supervisor puede consultar el territorio **sin conceder
nada**. Hay pruebas para las dos cosas:

- `test_la_historia_no_agrego_permisos_al_catalogo`
- `test_el_supervisor_consulta_porque_la_hu04_le_dio_operativos_ver`

### 9.3 ¿Por qué la lectura y la escritura se separan en dos permisos?

Porque son dos necesidades distintas. Un supervisor necesita **consultar** en qué
zonas está dividido su sector para repartir el trabajo; no necesita poder
**redibujar** el territorio. Con un solo permiso, delegar la consulta obligaría a
entregar también la capacidad de rehacer la planificación completa.

Consecuencia demostrable en la defensa: conceder `operativos.gestionar` al
Supervisor desde la matriz le abre la planificación completa **sin tocar ni
desplegar código** (`test_conceder_gestionar_abre_la_planificacion_sin_tocar_codigo`).

### 9.4 Reglas de negocio que no se pueden saltar por URL

| Regla | Dónde se comprueba |
|---|---|
| Un operativo cerrado no admite cambios de territorio | `OperativoAbiertoMixin.dispatch()` |
| Una comuna con sectores en operativos sin cerrar no se desactiva | `ComunaCambiarEstadoView.post()` |
| Solo se puede pasar a un estado alcanzable | `CambiarEstadoOperativoForm.clean_estado()` |

Las tres se comprueban en el **POST**, no solo ocultando el botón en la plantilla.
Ocultar un botón no es una validación: es la misma lección que la HU-03 documentó
con «no autodeshabilitarse», y hay pruebas que escriben la URL a mano para
verificarlo.

---

## 10. Auditoría

### 10.1 Se revisa una decisión de la HU-04, y se explica por qué

La HU-04 escribió en `RegistroAuditoria` esta justificación para usar dos claves
foráneas explícitas (`usuario_afectado`, `rol_afectado`) en vez de una referencia
genérica:

> «Solo hay dos tipos de objeto auditables y **no se prevén muchos más**.»

La HU-05 agrega cuatro de golpe (operativo, comuna, sector, zona), así que **la
premisa dejó de ser cierta**. La decisión se revisa en vez de arrastrarse, y eso es
parte del trabajo de ingeniería: una decisión correcta con la información de
entonces puede dejar de serlo.

**Por qué no se siguió el camino anterior:** significaría **ocho columnas nuevas**
(cuatro claves foráneas más cuatro copias de texto) para una tabla que ya tiene
cuatro dedicadas a lo mismo, y otras dos por cada entidad que traigan las historias
de fichas y reportes. Una bitácora con veinte columnas casi siempre nulas es
ilegible, y las consultas tendrían que unir seis tablas para responder «¿qué pasó
aquí?».

### 10.2 La solución: tres columnas para cuatro entidades

```python
objeto_tipo    = CharField(choices=TipoObjetoAuditoria.choices, blank=True)
objeto_id      = PositiveIntegerField(null=True)      # sin clave foránea
objeto_nombre  = CharField(max_length=250)            # copia fija legible
```

**¿No se pierde la integridad referencial?** Sí, y aquí es aceptable por una razón
concreta que **no valía para las cuentas**: el territorio **nunca se borra
físicamente**. Comuna, sector y zona se desactivan (misma decisión que las cuentas
en la HU-03), así que la fila apuntada sigue existiendo y el identificador no queda
huérfano. Y si algún día se borrara, `objeto_nombre` conserva la información
legible, que es el mismo seguro que ya protege a `usuario_afectado_email`.

Lo que se pierde —que PostgreSQL valide la referencia— se compensa donde importa:
**el valor probatorio de una bitácora está en el texto que una persona puede leer**,
no en poder navegar la clave foránea.

### 10.3 Las cinco acciones nuevas

| Acción | Cuándo |
|---|---|
| `CREAR_TERRITORIO` | Se da de alta un operativo, comuna, sector o zona |
| `EDITAR_TERRITORIO` | Se modifican sus datos |
| `ACTIVAR_TERRITORIO` | Se reactiva |
| `DESACTIVAR_TERRITORIO` | Se desactiva (borrado lógico) |
| `CAMBIAR_ESTADO_OPERATIVO` | El operativo cambia de estado |

Son **genéricas a propósito**: cuál de las cuatro entidades se tocó lo dice
`objeto_tipo`, así que no hacen falta cuatro juegos de acciones (`CREAR_COMUNA`,
`CREAR_SECTOR`, …) que multiplicarían el catálogo sin agregar información.

La columna `accion` pasó de 20 a 30 caracteres porque `CAMBIAR_ESTADO_OPERATIVO`
mide 24. Se amplió la columna en vez de abreviar el código: **un código legible en
la base de datos vale más que cuatro bytes**.

### 10.4 El nombre que se guarda lleva el camino completo

`_describir_objeto_territorial()` usa `nombre_completo` cuando el modelo lo define:

| Entidad | Se guarda |
|---|---|
| Operativo | `Censo Social 2026` |
| Comuna | `Concepción (Región del Biobío)` |
| Sector | `Los Boldos · Concepción` |
| Zona | `Zona 1 · Los Boldos · Concepción` |

Importa porque **«Zona 1» a secas no identifica nada**: casi todos los sectores
tienen una «Zona 1». Un año después, leyendo la bitácora, el camino completo es la
diferencia entre una fila útil y una inútil.

La conversión se aísla en una función para que se escriba **una vez**: si cada vista
armara la terna, alguna guardaría `str(sector)` en vez de `sector.nombre_completo`
y la bitácora dejaría de ser comparable entre filas. El tipo se **deduce** del
nombre de la clase, y si no está en el catálogo se levanta `ValueError` en vez de
escribir una fila con el tipo vacío, que quedaría fuera de cualquier filtro por
tipo sin que nadie lo note.

### 10.5 Qué NO se audita

Guardar un formulario **sin cambiar nada** no escribe en la bitácora. Es la misma
regla que aplica la matriz de la HU-04: no es un hecho auditable, y una bitácora
llena de filas «no cambió nada» esconde las que importan. Tampoco se escribe cuando
la operación se rechaza, ni cuando se desactiva algo que ya estaba desactivado
(recargar la página no es un hecho nuevo). Hay una prueba para cada caso.

---

## 11. Migraciones

### 11.1 Las migraciones de esta historia

| Migración | Qué hace |
|---|---|
| `operativos/0001_initial` | Las cinco tablas con sus restricciones e índices |
| `operativos/0002_regiones_iniciales` | Siembra las 16 regiones de Chile |
| `usuarios/0006_auditoria_territorial` | Tres columnas nuevas en la bitácora + `accion` a 30 |

### 11.2 La migración de datos: por qué las regiones se siembran

Mismo criterio que `0002_roles_iniciales` y `0005_permisos_iniciales`: los datos que
el sistema necesita para funcionar son **parte del código**, no algo que alguien
tenga que escribir a mano en pgAdmin.

| Ventaja | En concreto |
|---|---|
| Reproducibilidad | Cualquiera que clone el repositorio y migre obtiene las mismas 16 filas |
| Versionado | Si cambia el nombre oficial de una región, el cambio queda en Git con fecha y autor |
| Pruebas | La base de prueba se crea aplicando migraciones: las regiones están en cada test sin fixtures |

### 11.3 Tres detalles que conviene poder explicar

**1. `apps.get_model()` y no `from .models import Region`.** Es la regla de oro de
las migraciones de datos: hay que trabajar con el modelo **tal como era en ese punto
de la historia**. Si se importara la clase real, el día que el modelo gane un campo
obligatorio esta migración empezaría a fallar al reconstruir la base desde cero.

**2. `update_or_create` y no `create`.** Hace la migración **idempotente**: si
alguien ya había insertado una región a mano, se actualiza en vez de estallar con un
error de clave duplicada.

**3. La migración inversa es prudente.** Borra solo las regiones **sin comunas**. Una
migración que no se puede revertir bloquea el desarrollo, pero revertir a ciegas
sería peor: si hay comunas colgando, borrar la región fallaría por `PROTECT` o
arrastraría datos reales.

### 11.4 `usuarios/0006` no toca ningún dato

Las tres columnas admiten vacío y nulo, así que las filas de auditoría que ya
existen quedan con `objeto_tipo=""` y `objeto_id=NULL`, **que es exactamente la
verdad**: no afectaron a ningún objeto territorial. `objetivo` las sigue resolviendo
por `usuario_afectado_email` o `rol_afectado_nombre`, igual que antes.

Ampliar `accion` de 20 a 30 tampoco toca datos: en PostgreSQL agrandar un
`varchar(n)` es un cambio **solo de catálogo**, no reescribe la tabla.

La migración es reversible y no destructiva: se puede aplicar sobre una base en
producción con la bitácora llena sin perder una sola fila. Hay una prueba que lo
verifica (`test_los_registros_no_territoriales_siguen_siendo_legibles`).

### 11.5 Comandos

```bash
cd backend
..\.venv\Scripts\python.exe manage.py migrate
```

---

## 12. Rendimiento

### 12.1 El problema N+1, y cómo se evita en cada pantalla

Dibujar un árbol de tres niveles es el caso donde el problema N+1 aparece con más
facilidad: una consulta por cada sector, más una por cada zona.

| Pantalla | Técnica | Sin ella |
|---|---|---|
| Ficha del operativo | `prefetch_related` con `Prefetch` anidado | Una consulta por sector + una por zona |
| Listado de operativos | `annotate(Count(...))` | Dos consultas por fila (10 filas → 21 consultas) |
| Listado de comunas | `annotate(Count(...))` | Una consulta por fila |
| Ambos listados | `select_related` | Una consulta por fila para la clave foránea |

### 12.2 `distinct=True` no es opcional

```python
n_sectores=Count("sectores", distinct=True),
n_zonas=Count("sectores__zonas", distinct=True),
```

Al unir sectores y zonas en la misma consulta, **cada sector se repite una vez por
zona**, y sin `distinct` el conteo de sectores saldría multiplicado. Es el error
clásico de combinar dos `Count` sobre relaciones anidadas, y hay una prueba que lo
fija: `test_el_conteo_de_sectores_no_se_infla_con_las_zonas`.

### 12.3 Un detalle de Django que costó un bug real

`annotate()` genera un `GROUP BY`, y **Django descarta el `Meta.ordering` en las
consultas con `GROUP BY`**. El resultado es un queryset sin orden, y un queryset sin
orden paginado devuelve resultados inconsistentes (PostgreSQL no garantiza el mismo
orden entre dos consultas). Django lo advierte con
`UnorderedObjectListWarning`.

La corrección es repetir el orden explícitamente aunque el modelo ya lo declare:

```python
.order_by("-fecha_inicio", "nombre")
```

### 12.4 Cómo se prueba que el coste es constante

La prueba no fija un número exacto de consultas. Un número fijo con
`assertNumQueries` sería frágil: cambiaría si Django ajustara cómo carga la sesión o
el usuario, y fallaría sin que nada de esta historia estuviera mal.

Lo que hay que garantizar es otra cosa: que el coste **no dependa del tamaño del
territorio**. La prueba mide con 2 sectores, mide con 6, y compara:

```python
self.poblar(2);           con_dos   = self.contar_consultas()
self.poblar(4, desde=2);  con_seis  = self.contar_consultas()
self.assertEqual(con_dos, con_seis)
```

**Verificado:** al quitar el `prefetch_related` de la vista, el conteo pasa de 16 a
32 consultas y la prueba falla. Es decir, la prueba realmente protege lo que dice
proteger.

---

## 13. Archivos creados y modificados

### 13.1 Archivos nuevos

| Archivo | Función |
|---|---|
| `operativos/models.py` | Los cinco modelos territoriales |
| `operativos/forms.py` | 7 formularios con sus validaciones |
| `operativos/views.py` | 13 vistas + 4 mixins |
| `operativos/urls.py` | 17 rutas |
| `operativos/admin.py` | Registro en `/admin/` |
| `operativos/tests.py` | 141 pruebas |
| `operativos/migrations/0001_initial.py` | Esquema |
| `operativos/migrations/0002_regiones_iniciales.py` | Siembra de regiones |
| `usuarios/migrations/0006_auditoria_territorial.py` | Bitácora territorial |
| `usuarios/templatetags/permisos.py` | Filtros `tiene_permiso` y `tiene_algun_permiso` |
| `templates/operativos/*.html` | 12 plantillas |

### 13.2 Archivos modificados

| Archivo | Cambio |
|---|---|
| `usuarios/models.py` | `TipoObjetoAuditoria`, 5 acciones nuevas, 3 columnas, `etiqueta_objeto`, `es_territorial` |
| `usuarios/auditoria.py` | `registrar_accion()` acepta objetos territoriales |
| `config/settings.py` | La app `operativos` en `INSTALLED_APPS` |
| `config/urls.py` | `path("operativos/", include(...))` |
| `templates/base.html` | Enlace «Operativos» según permiso |
| `templates/dashboards/administrador.html` | Tarjeta de operativos y territorio |
| `templates/usuarios/gestion/auditoria_list.html` | Muestra el objeto territorial |

### 13.3 Archivos que NO se modificaron (y es un buen indicador)

`usuarios/mixins.py`, `usuarios/decorators.py`, `usuarios/views_gestion.py`,
`usuarios/views_permisos.py`, `usuarios/forms_permisos.py`, y las migraciones
`0001`–`0005`.

Que el control de acceso de una historia nueva no haya requerido tocar el mixin de
permisos ni el catálogo es la señal de que el diseño de la HU-04 estaba bien
planteado.

---

## 14. Pruebas

### 14.1 Las 141 pruebas por área

| Área | Pruebas | Qué cubre |
|---|---|---|
| Siembra de regiones | 7 | Las 16 filas, el orden geográfico, el cero a la izquierda |
| Modelo `Comuna` | 10 | Unicidad por región, `PROTECT`, regla de desactivación |
| Modelo `Operativo` | 14 | Estados, fechas, `CheckConstraint`, `duracion_dias`, `vigente` |
| Modelos `Sector` / `Zona` | 12 | Unicidad, `CASCADE`, `PROTECT`, `nombre_completo` |
| Control de acceso | 9 | Los dos permisos, los tres roles, anónimo, delegación |
| CRUD de comunas | 12 | Alta, edición, duplicados, auditoría |
| Desactivar comuna | 8 | Borrado lógico, regla de negocio, CSRF, idempotencia |
| CRUD de operativos | 11 | Alta, fechas incoherentes, `creado_por` |
| Cambio de estado | 9 | Transiciones válidas e inválidas, motivo, CSRF |
| Sectores y zonas | 14 | Operativo/sector desde la URL, comuna desactivada, el 0 |
| Operativo cerrado | 6 | Las 6 rutas bloqueadas, por GET y por POST, orden de mixins |
| Ficha del operativo | 7 | Agrupado, contadores, operativo vacío |
| Consultas (N+1) | 1 | El coste no crece con el territorio |
| Listados | 8 | Búsqueda, filtros, `distinct`, filtro inválido |
| Integración | 12 | Bitácora, panel, menú, HU-03 y HU-04 intactas |
| Filtro de plantilla | 7 | Permisos, anónimo, delegación en el modelo |

### 14.2 Ejecución

```bash
cd backend
set DB_ENGINE=sqlite3 && ..\.venv\Scripts\python.exe manage.py test operativos
```

```
Ran 141 tests in 3.7s
OK
```

Y el proyecto completo:

```
Ran 422 tests in 16.3s
OK
```

### 14.3 Una nota sobre SQLite y las tildes

`DB_ENGINE=sqlite3` permite ejecutar las pruebas sin levantar PostgreSQL, pero los
dos motores no son idénticos y una prueba lo expone.

La comprobación de duplicados usa `nombre__iexact`. **PostgreSQL** —el motor de
desarrollo y producción— lo resuelve con `UPPER()` y pliega correctamente los
caracteres acentuados, así que «CONCEPCIÓN» se detecta como duplicado de
«Concepción». **SQLite** solo pliega el rango ASCII y no reconocería Ó como la misma
letra que ó.

La prueba usa por eso un nombre sin tildes («TALCAHUANO» vs «Talcahuano»):
comprueba exactamente la misma regla y da el mismo resultado en los dos motores.
Verificar el plegado de tildes ahí no estaría probando el código de OPSO, sino la
tabla de caracteres de SQLite.

### 14.4 Cómo probar a mano (guion para la defensa)

1. Entrar como administrador → **Operativos** en el menú.
2. **Comunas** → *Nueva comuna* → región Biobío, nombre «Concepción». Guardar.
3. Intentar crear «CONCEPCIÓN» en Biobío → aparece el error junto al campo.
4. Crear «Concepción» en la Metropolitana → **se acepta** (homónimas en regiones
   distintas).
5. *Nuevo operativo* → «Censo Social 2026», del 01-03-2026 al 31-03-2026.
6. Poner fecha de término anterior al inicio → error debajo de «fecha de término».
7. En la ficha → *Agregar sector* → «Los Boldos» en Concepción.
8. En el sector → *+ Zona* → «Zona 1», 120 viviendas.
9. Escribir 0 en viviendas → mensaje que pide dejarlo vacío.
10. *Cambiar estado* → «Cerrado». Los botones de territorio **desaparecen**.
11. Escribir a mano `/operativos/1/sectores/nuevo/` → redirige con el aviso de
    operativo cerrado.
12. **Auditoría** → todas las acciones registradas con el camino completo.
13. **Matriz de permisos** → conceder `operativos.gestionar` al Supervisor.
14. Entrar como supervisor → ahora puede planificar. **Sin desplegar código.**

---

## 15. Explicación para la defensa

### 15.1 El resumen en un minuto

Esta historia le da a OPSO la dimensión que le faltaba: **el dónde**. Modela el
territorio en cuatro niveles (región → comuna → sector → zona) y lo hace con una
decisión de diseño que vale la pena defender: **la geografía y la organización del
trabajo son cosas distintas**.

La región y la comuna existen con o sin OPSO, así que se guardan una vez y se
comparten. El sector y la zona existen porque hay un operativo, así que cuelgan de
él. Eso permite que cada operativo divida el mismo territorio como necesite sin
falsear el histórico de los anteriores.

Y lo hizo **sin agregar un solo permiso al sistema**, porque la HU-04 ya había
modelado la autorización de este módulo.

### 15.2 Las cinco decisiones que hay que saber justificar

| Decisión | Justificación en una frase |
|---|---|
| El sector cuelga del operativo | Si fuera geografía permanente, redividir la comuna reescribiría el pasado |
| Las regiones se siembran, las comunas se administran | La autoridad sobre el dato es distinta: la ley vs. OPSO |
| Se desactiva, no se borra | Los datos del censo cuelgan de estas filas |
| Un operativo cerrado congela su territorio | Cambiarlo falsearía la información con la que se trabajó |
| La bitácora usa tres columnas genéricas | La premisa de la HU-04 («no se prevén muchos más tipos») dejó de ser cierta |

### 15.3 Lo que demuestra sobre el diseño anterior

El indicador más fuerte de esta historia no es lo que agregó, sino **lo que no tuvo
que tocar**: ni `mixins.py`, ni el catálogo de permisos, ni ninguna migración
anterior. Un módulo completo de 13 vistas se protegió reutilizando lo que ya
existía.

---

## 16. Posibles preguntas del profesor

**¿Por qué no usó las 346 comunas oficiales de Chile?**
Porque OPSO trabaja en un puñado. Sembrarlas todas obligaría a buscar entre 346
opciones las 4 que interesan, y los reportes mostrarían 342 comunas sin una sola
ficha. La lista corta significa algo: *estas son las comunas de OPSO*. Las 16
regiones sí se siembran, porque son pocas, sirven para agrupar y evitan que
«Biobío» y «Bío-Bío» convivan como dos regiones distintas.

**¿Por qué el sector no cuelga solo de la comuna, que sería más simple?**
Porque sería más simple y **estaría mal**. La división del terreno es una decisión
de planificación que cambia entre operativos. Si «Los Boldos» fuera geografía
permanente, partirlo en tres para el operativo de 2027 cambiaría retroactivamente
la división con la que se levantaron las fichas de 2026. Colgándolo del operativo,
cada uno conserva su propia foto y el histórico sigue siendo verdad.

**¿No es redundante que `Sector` tenga clave foránea al operativo y a la comuna?**
No. Un operativo abarca varias comunas y una comuna aparece en varios operativos:
ninguna se deduce de la otra. El sector es el cruce de ambas.

**¿Por qué `CASCADE` en el operativo y `PROTECT` en la comuna?**
Porque significan cosas distintas. Un sector es una división **de** un operativo: si
el operativo desaparece, sus divisiones no tienen sentido. La comuna, en cambio, es
geografía compartida; borrarla dejaría sectores sin ubicación, así que PostgreSQL lo
impide y la interfaz ofrece desactivar.

**¿Por qué agregó columnas genéricas a la bitácora si la HU-04 argumentó lo
contrario?**
Porque el argumento de la HU-04 se apoyaba en una premisa —«solo hay dos tipos y no
se prevén muchos más»— que esta historia invalida al agregar cuatro. Seguir ese
camino significaría ocho columnas nuevas, y otras dos por cada entidad futura. Se
acepta perder la validación referencial porque aquí no cuesta nada: el territorio
nunca se borra físicamente, se desactiva, así que el identificador no queda
huérfano. Y el valor probatorio de una bitácora está en el texto legible, no en
poder navegar la clave foránea.

**¿Qué pasa si desactivo una comuna que ya tiene sectores?**
No se puede, si esos sectores están en operativos sin cerrar, y el sistema explica
por qué y qué hacer. Si todos sus operativos están cerrados, la comuna ya no se usa
y desactivarla es exactamente lo correcto. La regla se comprueba en el POST, no
ocultando el botón: la URL se puede escribir a mano.

**¿Puedo modificar el territorio de un operativo terminado?**
No, y es deliberado: su división es el registro histórico de cómo se trabajó. Sí se
pueden corregir sus datos (una fecha mal escrita), porque eso no altera el
territorio. Y se puede reabrir, dejando el cambio en la bitácora con su motivo.

**¿Por qué un filtro de plantilla y no una variable de contexto?**
Porque `base.html` la heredan todas las vistas del proyecto, incluidas las de otras
apps. Con una variable de contexto, cada vista tendría que recordar pasarla y la
primera que se olvidara dejaría el menú incompleto sin que nadie lo notara. Un
context processor se ejecutaría en peticiones que no dibujan el menú.

**¿Cómo sabe que no tiene el problema N+1?**
Hay una prueba que mide las consultas con 2 sectores y con 6, y exige que el número
sea **el mismo**. No fija un número exacto porque sería frágil; lo que garantiza es
que el coste no dependa del tamaño del territorio. Comprobé que funciona: al quitar
el `prefetch_related`, el conteo pasa de 16 a 32 y la prueba falla.

**¿Por qué la zona y no llegar hasta la vivienda?**
Porque la vivienda es el objeto de la **ficha de familia**, no de la organización
del operativo. La zona es el último nivel que sigue siendo una unidad de
planificación: el pedazo de sector que una persona recorre en una jornada.

---

## 17. Conclusión técnica

La HU-05 incorpora a OPSO el modelo territorial sobre el que se apoyarán las
historias siguientes. Su aporte central no es el CRUD —que es el mismo patrón de la
HU-03— sino la **decisión de separar la geografía de la organización del trabajo**:
región y comuna como datos compartidos y estables; operativo, sector y zona como
una planificación que pertenece a un despliegue concreto. Esa separación es la que
permite que el sistema crezca en el tiempo sin falsear su propio histórico, una
propiedad que en un sistema de registro social no es un lujo sino un requisito: la
información sobre dónde y cuándo se levantó cada ficha es parte de su validez.

En el plano de la ingeniería, la historia funciona además como **verificación del
diseño anterior**. Un módulo de trece vistas quedó protegido, delegable y auditado
sin modificar el mixin de autorización, sin agregar una fila al catálogo de permisos
y sin tocar ninguna migración previa: la autorización de este módulo estaba
modelada, con su descripción exacta, desde la HU-04. Al mismo tiempo, obligó a
**revisar explícitamente** una decisión de esa historia —la referencia al objeto
auditado— porque la premisa en que se apoyaba dejó de ser cierta. Documentar esa
revisión, con su costo y su compensación, es lo que distingue una arquitectura que
evoluciona de una que acumula deuda.

Las 141 pruebas propias, integradas en las 422 del proyecto, cubren las
restricciones de la base de datos, las reglas de negocio, el control de acceso por
permiso, la protección contra la modificación por URL y el comportamiento del
rendimiento frente al crecimiento de los datos.
