# HU-06 · Asignación de sectores a los encuestadores

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor, quiero asignar sectores geográficos a los encuestadores para distribuir el trabajo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **124 pruebas automáticas** propias (546 en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no reimplementa nada**. Reutiliza el permiso
> `operativos.asignar_sector` **ya sembrado** por la HU-04, el modelo `Sector` de la
> HU-05, `PermisoRequeridoMixin`, la bitácora `RegistroAuditoria` de la HU-03 y el
> fragmento `_campo.html`. Es además **la primera historia cuyo protagonista no es
> el administrador**, sino el supervisor.

---

## Índice

1. [Explicación inicial: ¿por qué asignar no es lo mismo que planificar?](#1-explicación-inicial)
2. [El modelo de datos](#2-el-modelo-de-datos)
3. [Base de datos: las dos restricciones que importan](#3-base-de-datos)
4. [El formulario de conjunto](#4-el-formulario-de-conjunto)
5. [Vistas](#5-vistas)
6. [URLs](#6-urls)
7. [Templates e interfaz](#7-templates-e-interfaz)
8. [Seguridad y control de acceso](#8-seguridad-y-control-de-acceso)
9. [Auditoría](#9-auditoría)
10. [Migraciones](#10-migraciones)
11. [Rendimiento](#11-rendimiento)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 El problema que resuelve

Un censo no fracasa por falta de formularios: **fracasa cuando dos censistas
visitan la misma cuadra y nadie visita la de al lado**. La HU-05 le dio a OPSO el
mapa; esta historia reparte el mapa entre personas.

Sin ella, el reparto se hace por teléfono o en una reunión, y eso tiene tres
consecuencias concretas:

| Sin registro del reparto | Con registro del reparto |
|---|---|
| «Creo que Los Boldos lo lleva Marta» | Está escrito y con fecha |
| Nadie sabe qué sector quedó sin cubrir | El sistema los cuenta y los muestra en rojo |
| No se puede saber si el trabajo está bien repartido | Se ve la carga de cada persona |
| Una ficha no explica por qué la levantó esa persona | La asignación histórica lo explica |

### 1.2 ¿Por qué «asignar» es un permiso distinto de «gestionar»?

Porque son **dos trabajos distintos y los hace gente distinta**:

- El **administrador dibuja** el territorio (`operativos.gestionar`): decide que la
  comuna se parte en cinco sectores y cada sector en zonas.
- El **supervisor reparte** ese territorio (`operativos.asignar_sector`): decide
  quién cubre cada sector.

Con un solo permiso, dejar que un supervisor reparta el trabajo obligaría a dejarlo
también **redibujar el mapa**, que no es su función. Y en efecto, el reparto inicial
de la HU-04 le da al supervisor `asignar_sector` pero **no** `gestionar`: puede
repartir el terreno y no puede alterar su división. Hay pruebas de las dos cosas.

### 1.3 La segunda mitad de la historia: que el censista lo vea

Repartir el trabajo solo sirve si la persona a la que se le reparte **puede verlo**.
Si el supervisor asigna sectores y luego tiene que avisar por teléfono, se ha
sustituido un procedimiento informal por otro procedimiento informal más una base de
datos.

Por eso la historia incluye la pantalla **«Mis sectores»** y el panel del censista:
el censista entra, ve su territorio, sus zonas y las indicaciones que le dejó su
supervisor. Es la mitad de la historia que la formulación no menciona pero sin la
cual «distribuir el trabajo» no ocurre.

---

## 2. El modelo de datos

### 2.1 Una tabla propia, no un `ManyToManyField`

```
Sector ──< AsignacionSector >── Usuario
```

Podría escribirse como `Sector.censistas = ManyToManyField(Usuario)` y Django
crearía la tabla intermedia solo. Se descartó porque una asignación tiene **datos
propios** que no caben en una tabla intermedia automática:

| Campo | Para qué |
|---|---|
| `asignado_por` | Quién repartió el trabajo |
| `asignado_en` | Cuándo |
| `activa` | Si sigue vigente |
| `desasignado_en` | Cuándo se retiró |
| `observaciones` | Instrucciones para esa persona en ese sector |

### 2.2 La comparación con la HU-04, que decidió lo contrario

Este punto conviene tenerlo claro porque es una **aparente contradicción** con una
decisión anterior, y no lo es.

En la HU-04 se razonó que `Rol.permisos` **no** necesitaba un modelo intermedio
explícito, porque `RegistroAuditoria` ya respondía «quién concedió qué y cuándo», y
una tabla intermedia solo guarda el estado actual.

Aquí la conclusión es la contraria, y la diferencia es concreta: **el reparto del
trabajo no es solo un hecho auditable, es un dato que se consulta a diario**. El
censista abre su panel y necesita ver sus sectores; el supervisor necesita ver quién
cubre qué y cuánta carga tiene cada uno. Eso no se puede resolver leyendo la
bitácora: una bitácora se lee para investigar el pasado, no para trabajar hoy.

| | `Rol.permisos` (HU-04) | `AsignacionSector` (HU-06) |
|---|---|---|
| ¿Se consulta a diario? | No, solo al configurar | **Sí**, es la pantalla de trabajo |
| ¿Tiene datos propios? | No | Sí (fechas, quién, observaciones) |
| ¿Necesita historial? | No, la bitácora basta | **Sí**, explica las fichas levantadas |
| Resultado | M2M simple | **Tabla propia** |

### 2.3 No se borra, se desactiva

Al retirar a alguien de un sector la fila **no se elimina**: se marca `activa=False`
y se anota `desasignado_en`. Es la misma decisión que la HU-03 con las cuentas y la
HU-05 con el territorio, pero aquí la razón es más fuerte todavía: **las fichas que
ese censista levantó en ese sector se explican por esta asignación**. Borrarla
dejaría huérfano el «por qué» de un dato del censo.

La consecuencia es que la tabla acumula el historial completo del reparto: *«en
marzo Los Boldos lo cubrió Marta; desde abril, Juan»*. Eso responde preguntas reales
de supervisión sin leer la bitácora.

### 2.4 `desactivar()` es un método del modelo

```python
def desactivar(self):
    self.activa = False
    self.desasignado_en = timezone.now()
    self.save(update_fields=["activa", "desasignado_en"])
```

Se escribe aquí y no en la vista para que las **dos columnas que describen la baja se
actualicen siempre juntas**. Si cada vista lo hiciera a mano, alguna pondría
`activa=False` y olvidaría la fecha, y el `CheckConstraint` rechazaría el guardado
—o peor, en un motor sin esa restricción, dejaría un historial mentiroso.

### 2.5 Cardinalidad: varios a varios, a propósito

- Un **sector** puede tener **varias** personas (un equipo se reparte un sector
  grande).
- Una **persona** puede tener **varios** sectores.

Es lo habitual en terreno. La alternativa —un responsable único por sector— sería
más simple pero obligaría a inventar sectores artificiales para partir el trabajo de
un sector grande, y eso ensuciaría el mapa que la HU-05 construyó.

---

## 3. Base de datos

### 3.1 La tabla

```
┌──────────────────────────────────────────┐
│ operativos_asignacion_sector             │
├──────────────────────────────────────────┤
│ id                 PK                    │
│ sector_id          FK → sector (CASCADE) │
│ censista_id        FK → usuario (PROTECT)│
│ asignado_por_id    FK → usuario (SET_NULL)│
│ observaciones                            │
│ activa                                   │
│ asignado_en                              │
│ desasignado_en     NULL                  │
├──────────────────────────────────────────┤
│ UNIQUE (sector, censista) WHERE activa   │
│ CHECK  coherencia activa ↔ desasignado_en│
│ INDEX  (censista, activa)                │
│ INDEX  (sector, activa)                  │
└──────────────────────────────────────────┘
```

### 3.2 La unicidad es PARCIAL, y es la decisión más fina de la historia

Una restricción `unique(sector, censista)` sería **incorrecta**: impediría volver a
asignar a alguien que ya estuvo antes, porque la fila histórica seguiría ahí. Y
quitarla del todo permitiría duplicar una asignación vigente.

La restricción correcta es **«único entre las activas»**, que en PostgreSQL es un
índice único parcial. Django lo expresa con `condition`:

```python
models.UniqueConstraint(
    fields=["sector", "censista"],
    condition=models.Q(activa=True),
    name="asignacion_activa_unica",
)
```

Hay una prueba para cada lado: `test_no_se_puede_asignar_dos_veces_a_la_misma_persona`
y `test_si_se_puede_reasignar_a_alguien_que_ya_estuvo`.

### 3.3 El `CheckConstraint` de coherencia

```python
models.CheckConstraint(
    condition=(
        models.Q(activa=True,  desasignado_en__isnull=True)
        | models.Q(activa=False, desasignado_en__isnull=False)
    ),
    name="asignacion_baja_coherente",
)
```

Dos columnas describen el mismo hecho, así que la base de datos exige que no se
contradigan: una asignación activa no puede tener fecha de baja, y una inactiva
tiene que tenerla. Sin esto, un `save()` descuidado dejaría filas que se contradicen
consigo mismas y **el historial dejaría de ser fiable justo cuando alguien lo
necesita**.

### 3.4 El comportamiento al borrar

| Relación | Comportamiento | Por qué |
|---|---|---|
| `sector` | `CASCADE` | Una asignación no significa nada sin su sector |
| `censista` | `PROTECT` | Borrarlo dejaría el reparto sin explicación |
| `asignado_por` | `SET_NULL` | Si se elimina la cuenta del supervisor, el reparto debe sobrevivir |

`PROTECT` en `censista` y `SET_NULL` en `asignado_por` no es una incoherencia: sin el
censista la fila **no tiene sentido** (¿asignado a quién?), mientras que sin el
supervisor solo se pierde un dato de contexto.

---

## 4. El formulario de conjunto

### 4.1 Casillas, no «agregar una persona»

La pregunta que resuelve el supervisor no es «¿a quién agrego?» sino **«¿quiénes
cubren este sector?»**. Con casillas de verificación esa pregunta se responde de un
vistazo y se corrige en un clic: se marca a quien entra, se desmarca a quien sale, y
una **reasignación** —que es las dos cosas a la vez— es **una sola operación**.

Es el mismo enfoque que `PermisosRolForm` en la HU-04, y comparte su consecuencia:
**guardar es calcular la diferencia**, no insertar sin más.

### 4.2 Los tres movimientos de `guardar()`

```
entra y no estaba nunca  ->  se crea una fila nueva
entra y estuvo antes     ->  se REACTIVA su fila histórica
sale                     ->  se desactiva su fila (se conserva)
```

El caso del medio es el que justifica el índice único parcial: reactivar en vez de
crear **evita acumular una fila por cada ida y vuelta** y mantiene un solo registro
por persona y sector, con su fecha original.

Dos detalles que hay pruebas para fijar:

- A quien **ya estaba** no se le cambia la fecha ni se le pisan sus observaciones.
  Guardar otro cambio no debe reiniciar la antigüedad de los demás.
- Las observaciones del formulario se aplican **solo a las asignaciones nuevas** de
  ese guardado.

### 4.3 Quién aparece en la lista

Solo cuentas con **rol Censista** y **habilitadas**. Las dos condiciones importan y
son distintas:

- El **rol**, porque asignar terreno a un supervisor confundiría la separación de
  funciones de la HU-03: quien valida el trabajo no debe ser quien lo levanta, o el
  control cruzado desaparece.
- El **estado**, porque una cuenta deshabilitada no puede iniciar sesión, así que
  asignarle un sector sería mandar a trabajar a alguien que no puede entrar al
  sistema. **El sector parecería cubierto y no lo estaría**, que es justo el error
  que esta historia existe para evitar.

### 4.4 El caso borde que sin cuidado rompe la pantalla

Si a un censista se le asignó un sector y **después se deshabilitó su cuenta**, no
aparecería en la lista, saldría desmarcado, y al guardar **cualquier otro cambio
quedaría desasignado** sin que el supervisor lo pidiera ni lo viera.

La solución es incluir en el queryset a los ya asignados además de los disponibles:

```python
Q(rol__codigo=RolCodigo.CENSISTA, is_active=True)
| Q(asignaciones_sector__sector=self.sector, asignaciones_sector__activa=True)
```

Así el problema se hace **visible** —aparece marcado y la pantalla lo señala con un
aviso— y la decisión de retirarlo queda en manos de quien mira la pantalla. Prueba:
`test_un_censista_deshabilitado_que_ya_tenia_el_sector_si_aparece`.

---

## 5. Vistas

| Vista | URL | Permiso |
|---|---|---|
| `PanelAsignacionesView` | `/operativos/<pk>/asignaciones/` | `operativos.ver` |
| `AsignarSectorView` | `/operativos/sectores/<pk>/asignar/` | `operativos.asignar_sector` |
| `RetirarAsignacionView` | `/operativos/asignaciones/<pk>/retirar/` | `operativos.asignar_sector` |
| `MisSectoresView` | `/operativos/mis-sectores/` | **ninguno** (ver 8.3) |

### 5.1 El panel solo exige `operativos.ver`

Consultar el reparto **no es modificarlo**. Un administrador que quiera revisar cómo
quedó distribuido el trabajo entra sin necesitar el permiso de asignar, y un
supervisor al que se le revocara `asignar_sector` seguiría pudiendo mirar. Hay una
prueba que lo fija: `test_consultar_el_panel_no_exige_el_permiso_de_asignar`.

### 5.2 ¿Por qué existe «retirar» si ya hay un formulario de conjunto?

Porque son **dos gestos distintos**: rearmar el equipo de un sector es una decisión
de planificación, y sacar a una persona concreta —se enfermó, renunció, se va a otro
sector— es una corrección puntual. Obligar a pasar por la pantalla completa para eso
**invita a desmarcar la casilla equivocada**.

### 5.3 GET muestra, POST ejecuta

Todas las operaciones que modifican van en dos pasos, por lo mismo que en el resto
del proyecto: si retirar se pudiera hacer con un GET, un `<img src="...">` incrustado
en cualquier página lo ejecutaría con la sesión del supervisor (ataque **CSRF**). Hay
pruebas de token CSRF para las dos vistas que escriben.

---

## 6. URLs

```
/operativos/mis-sectores/                pantalla del CENSISTA
/operativos/asignaciones/<pk>/retirar/
/operativos/sectores/<pk>/asignar/
/operativos/<pk>/asignaciones/           panel de reparto
```

Dos notas:

1. **`mis-sectores/` va antes de `<int:pk>/`**, como todas las rutas fijas del
   módulo: Django recorre la lista en orden y se queda con la primera coincidencia.
2. **`mis-sectores/` no lleva ningún identificador**, y eso es parte de su
   seguridad: no hay nada que manipular para pedir los sectores de otra persona.

---

## 7. Templates e interfaz

| Plantilla | Pantalla |
|---|---|
| `asignaciones_panel.html` | Panel de reparto: cobertura, equipo y carga |
| `sector_asignar.html` | Las casillas + el historial del sector |
| `asignacion_retirar.html` | Confirmación de la baja |
| `mis_sectores.html` | Lo que ve el censista |

### 7.1 El orden del panel no es casual

1. **¿Qué sectores no tiene nadie?** — el contador rojo y las filas resaltadas. Va
   primero porque es lo único que puede **arruinar el operativo**: territorio que
   nadie va a visitar.
2. **¿Quién cubre cada uno?** — la columna del equipo.
3. **¿Está bien repartida la carga?** — la tabla de equilibrio, al final.

La tercera es la que convierte «asignar» en **DISTRIBUIR**, que es lo que pide la
historia. Sin ver las viviendas por persona, repartir cinco sectores entre dos es
una decisión a ciegas: podrían quedar 400 viviendas para una y 60 para la otra sin
que nadie lo note hasta que sea tarde.

### 7.2 «Mis sectores» está pensada para el teléfono

Se lee **en terreno**: cada sector es una tarjeta con su comuna, sus zonas y las
observaciones del supervisor, sin tablas anchas que obliguen a desplazarse en
horizontal.

Cuando no hay nada asignado **se explica el motivo** y no solo que la lista está
vacía: alguien que entra a trabajar y no ve nada necesita saber si falla el sistema
o si todavía no le asignaron territorio.

### 7.3 El enlace del menú se decide por un HECHO, no por un permiso

```django
{% if user.asignaciones_sector.exists %}
```

«Mis sectores» aparece si la persona **tiene territorio a cargo**. No se filtra por
permiso porque el censista no tiene ninguno de operativos, y no se filtra por rol
porque un supervisor con sectores asignados también debería verlo. Si no tiene
nada, el enlace solo llevaría a una pantalla vacía.

---

## 8. Seguridad y control de acceso

### 8.1 Tercera historia seguida sin agregar permisos

`operativos.asignar_sector` lo sembró la migración `0005` de la HU-04 con esta
descripción:

> «Asignar censistas a un sector — **Distribuir el trabajo de terreno entre el
> personal disponible.**»

Y el reparto inicial ya se lo daba al rol Supervisor. Es decir: **el supervisor puede
usar esta historia sin que nadie le conceda nada**, porque la HU-04 modeló su trabajo
antes de que existieran las pantallas. Pruebas:
`test_la_historia_no_agrego_permisos_al_catalogo` y
`test_el_supervisor_reparte_sin_que_nadie_le_conceda_nada`.

### 8.2 Reglas de negocio que no se pueden saltar por URL

| Regla | Dónde se comprueba |
|---|---|
| Un operativo cerrado no admite cambios en el reparto | `Sector.puede_recibir_asignaciones()`, en GET **y** POST |
| Un sector desactivado no recibe personal | Ídem |
| No se puede asignar a alguien fuera de la lista | `AsignarSectorForm` (rechaza el POST completo) |

Las tres se comprueban en el **POST**, no solo ocultando el botón. Hay pruebas que
envían el POST a mano para verificarlo, y otra que confirma que el rechazo **no deja
rastro en la bitácora**.

Cuando la solicitud incluye a alguien no disponible **se rechaza el POST completo** y
no se aplica la parte válida: un reparto a medias dejaría sectores en un estado que
nadie decidió. Es el mismo criterio que la matriz de la HU-04.

### 8.3 La única vista del módulo sin permiso, y por qué

`MisSectoresView` no exige ningún permiso. Es una **decisión, no un olvido**.

El sistema de permisos de OPSO gobierna dos cosas: el acceso a los **módulos** y el
acceso a los datos de **otras personas**. Ver el trabajo que a uno mismo le asignaron
no es ninguna de las dos: es la información mínima sin la cual la cuenta no sirve
para nada. Un censista que no puede ver dónde le toca trabajar **no puede trabajar**,
así que un permiso revocable no expresaría una decisión operativa, solo la
posibilidad de inutilizar una cuenta por error.

Es el mismo razonamiento con que la HU-04 dejó la matriz de permisos protegida por
rol: **hay accesos que no deben poder desconfigurarse**.

> Se evaluó agregar `operativos.ver_propios` por simetría con `fichas.ver_propias`,
> que sí existe. La diferencia es que aquel gobierna una **funcionalidad** (el módulo
> de fichas, que un rol puede no tener en absoluto), mientras que esto es la pantalla
> que le dice a una persona cuál es su trabajo.

**Lo que sí protege la vista:** el filtro por `request.user` no es parametrizable. No
hay ningún `<pk>` en la URL ni ningún filtro que el usuario pueda enviar, así que no
existe forma de pedir «los sectores de otra persona». Prueba:
`test_no_ve_los_sectores_de_otra_persona`.

---

## 9. Auditoría

### 9.1 Una sola acción para asignar y retirar

`CAMBIAR_ASIGNACIONES` — «Cambió las asignaciones del sector».

Es una sola acción por la misma razón que `CAMBIAR_PERMISOS` en la HU-04: el detalle
dice qué entró y qué salió, y así una **reasignación** —que es las dos cosas a la
vez— queda en **una fila** y no en dos que habría que correlacionar por su hora. Hay
una prueba que lo fija: `test_una_reasignacion_queda_en_UNA_sola_fila`.

No se agregó ningún `TipoObjetoAuditoria`: el reparto recae sobre un **sector**, que
ya estaba en el catálogo desde la HU-05.

### 9.2 La generalización de `describir_cambio_permisos`

«Cambiaron los permisos de un rol» y «cambiaron los censistas de un sector» son la
misma operación en el fondo: se envía el conjunto completo y hay que averiguar la
diferencia. Solo se distinguen en tres cosas: cómo se identifica cada elemento, cómo
se lee, y con qué palabras se narra el movimiento.

Se extrajo `describir_cambio_de_conjunto(antes, despues, clave, etiqueta,
verbo_entra, verbo_sale)`, y las dos funciones concretas delegan en ella.

> **Se extrajo al agregar el segundo caso, no al escribir el primero.** Antes de la
> HU-06 no había nada que compartir, y generalizar con un solo caso de uso lleva a
> inventar parámetros que nadie necesita. Hay una prueba que confirma que la HU-04 no
> cambió de comportamiento: `test_la_funcion_de_la_hu04_sigue_funcionando_igual`.

### 9.3 Qué se guarda en el detalle

```
asignados: Marta Soto (marta@opso.cl); desasignados: Juan Vera (juan@opso.cl)
```

Se guarda el **nombre y el correo**. El nombre porque la bitácora la lee una persona
y «Marta Soto» se entiende sola; el correo porque es el identificador único de la
cuenta y en un operativo grande **puede haber dos personas con el mismo nombre**. Con
los dos datos la fila es legible y además inequívoca. Prueba:
`test_usa_el_correo_para_desambiguar_homonimos`.

El orden alfabético es deliberado: hace el texto comparable entre filas y estable
entre ejecuciones, así que dos cambios idénticos se leen idénticos.

### 9.4 Qué no se audita

Guardar sin cambiar nada no escribe en la bitácora. Tampoco cuando la operación se
rechaza, ni cuando se retira a alguien que ya estaba retirado (recargar la página no
es un hecho nuevo). Hay una prueba para cada caso, y otra que verifica que
`transaction.atomic` impide que quede un reparto guardado sin su fila de auditoría.

---

## 10. Migraciones

| Migración | Qué hace |
|---|---|
| `operativos/0003_asignaciones` | La tabla con sus 2 restricciones y 2 índices |
| `usuarios/0007_accion_asignaciones` | Agrega `CAMBIAR_ASIGNACIONES` al catálogo |

Ninguna de las dos toca datos:

- `0003` crea una tabla que **nace vacía**. El reparto lo hace el supervisor desde la
  aplicación, no una migración.
- `0007` es una `AlterField` sobre las `choices` de un `CharField`, que son
  validación de **Django**, no una restricción de PostgreSQL: ampliar la lista no
  reescribe la tabla ni invalida los valores ya guardados. La columna ya medía 30
  caracteres desde la HU-05 y `CAMBIAR_ASIGNACIONES` mide 20.

---

## 11. Rendimiento

### 11.1 El panel: `Prefetch` filtrado

```python
Prefetch(
    "asignaciones",
    queryset=AsignacionSector.objects.filter(activa=True).select_related("censista"),
    to_attr="equipo",
)
```

Se usa `Prefetch` y no `prefetch_related` a secas **porque hay que filtrar**: sin el
filtro se traerían también las asignaciones históricas y la plantilla mostraría gente
que ya no cubre el sector. `to_attr="equipo"` deja el resultado en un atributo que la
plantilla recorre sin consultar.

La carga de trabajo se resuelve con `annotate(Sum(...))` para no llamar a
`Sector.viviendas_estimadas()` en la plantilla, que lanzaría una consulta por fila.

### 11.2 La tabla de equilibrio: una consulta agregada

`carga_por_censista()` resuelve «cuántos sectores y cuántas viviendas tiene cada
persona» con **una** consulta sobre `Usuario` anotada con `Count` y `Sum`, en vez de
recorrer las asignaciones en Python. Es lo que permite mostrar la tabla sin que su
coste crezca con el número de censistas.

### 11.3 La ficha del operativo, y una lección aprendida

Al añadir «quién cubre este sector» al árbol territorial de la HU-05, la primera
versión llamaba a `sector.asignaciones_activas()` desde la plantilla. **La prueba de
N+1 de la HU-05 lo detectó de inmediato**: el número de consultas dejaba de ser
constante.

La corrección fue añadir el `Prefetch` a `OperativoDetailView` y usar `sector.equipo`
en la plantilla. Es un ejemplo concreto de una prueba de rendimiento **evitando la
introducción de un problema**, no solo documentándolo.

### 11.4 Cómo se prueba

`PanelConsultasTest` mide con 2 sectores, mide con 6 y exige que el número sea **el
mismo**. No fija un número exacto porque sería frágil; lo que garantiza es que el
coste **no dependa de la cantidad de datos**.

---

## 12. Archivos creados y modificados

### 12.1 Nuevos

| Archivo | Función |
|---|---|
| `operativos/forms_asignaciones.py` | Formulario de conjunto + filtros |
| `operativos/views_asignaciones.py` | 4 vistas + la puerta de permiso |
| `operativos/tests_asignaciones.py` | 124 pruebas |
| `operativos/migrations/0003_asignaciones.py` | La tabla |
| `usuarios/migrations/0007_accion_asignaciones.py` | La acción nueva |
| `templates/operativos/asignaciones_panel.html` | Panel de reparto |
| `templates/operativos/sector_asignar.html` | Las casillas |
| `templates/operativos/asignacion_retirar.html` | Confirmación |
| `templates/operativos/mis_sectores.html` | Pantalla del censista |

### 12.2 Modificados

| Archivo | Cambio |
|---|---|
| `operativos/models.py` | `AsignacionSector` + consultas en `Sector` y `Operativo` |
| `operativos/views.py` | `Prefetch` del equipo en la ficha del operativo |
| `operativos/urls.py` | 4 rutas |
| `operativos/admin.py` | `AsignacionSectorAdmin` + inline en el sector |
| `usuarios/models.py` | Acción `CAMBIAR_ASIGNACIONES` |
| `usuarios/auditoria.py` | `describir_cambio_de_conjunto` + `describir_cambio_asignaciones` |
| `dashboards/views.py` | Contadores del supervisor y sectores del censista |
| `templates/base.html` | Enlace «Mis sectores» |
| `templates/dashboards/supervisor.html` | Tarjeta de reparto (contadores que estaban en «—») |
| `templates/dashboards/censista.html` | Su territorio a cargo |
| `templates/operativos/operativo_detail.html` | Quién cubre cada sector + enlace al reparto |

### 12.3 No se modificaron

`usuarios/mixins.py`, `usuarios/views_gestion.py`, `usuarios/views_permisos.py`,
`operativos/forms.py`, y **ninguna migración anterior**. El catálogo de permisos
tampoco.

---

## 13. Pruebas

### 13.1 Las 124 pruebas por área

| Área | Pruebas | Qué cubre |
|---|---|---|
| Modelo `AsignacionSector` | 13 | Unicidad parcial, coherencia, `CASCADE`/`PROTECT` |
| Consultas del modelo | 12 | Vigentes vs. históricas, carga, contadores sin duplicar |
| Reglas del sector | 4 | Operativo cerrado, sector desactivado, motivos |
| Control de acceso | 9 | Los dos permisos, los tres roles, anónimo |
| Asignar | 13 | Alta, baja, reactivación, fechas, observaciones, CSRF |
| Quién puede ser asignado | 6 | Rol, estado, el caso borde del deshabilitado |
| Estado inicial del formulario | 3 | Que un reenvío no pise lo marcado |
| Auditoría | 9 | Una fila por reasignación, atomicidad, detalle |
| `describir_cambio_asignaciones` | 7 | Entradas, salidas, orden, homónimos, HU-04 intacta |
| Retirar | 8 | Baja lógica, avisos, idempotencia, CSRF |
| Reparto cerrado | 8 | Las rutas bloqueadas por GET y por POST |
| Panel | 15 | Contadores, filtros, anotaciones sin inflar |
| Consultas (N+1) | 1 | El coste no crece con los datos |
| Mis sectores | 9 | Solo lo propio, sin permiso, cerrados aparte |
| Integración | 12 | Paneles, menú, ficha, HU-03/04/05 intactas |

### 13.2 Ejecución

```bash
cd backend
set DB_ENGINE=sqlite3 && ..\.venv\Scripts\python.exe manage.py test operativos.tests_asignaciones
```

```
Ran 124 tests in 4.3s
OK
```

Y el proyecto completo: **546 pruebas, OK**.

### 13.3 Las pruebas se verificaron contra regresiones reales

No basta con que pasen: hay que saber que **fallan cuando deben**. Se comprobó
introduciendo dos fallos a propósito y confirmando que la suite los detecta:

| Fallo introducido | Resultado |
|---|---|
| Degradar la puerta de reparto a `operativos.ver` | **2 pruebas fallan** |
| Quitar la regla del sector desactivado | **4 pruebas fallan** |

Ambos cambios se revirtieron. La prueba de N+1 de la HU-05 también demostró su valor
durante el desarrollo (ver 11.3).

### 13.4 Guion para la defensa

1. Entrar como **supervisor** → el panel muestra los sectores sin asignar en rojo.
2. *Asignar sectores* → marcar a Marta en «Los Boldos», escribir una observación.
3. Volver al panel: el contador de «sin nadie a cargo» baja; aparece la carga.
4. Entrar como **Marta** → «Mis sectores»: su territorio, sus zonas y la indicación.
5. Como supervisor, marcar también a Juan → el sector lo cubren dos personas.
6. Retirar a Marta con la «×» → la pantalla avisa que Juan sigue cubriéndolo.
7. Retirar a Juan → **avisa de que el sector quedará sin personal**.
8. **Auditoría** (como administrador) → una fila por cada cambio, con el detalle.
9. Cerrar el operativo → los botones de reparto desaparecen.
10. Escribir a mano `/operativos/sectores/1/asignar/` → redirige con el aviso.
11. Volver a asignar a Marta tras reabrir → se **reactiva** su fila, no se duplica.

---

## 14. Explicación para la defensa

### 14.1 El resumen en un minuto

Esta historia reparte el mapa que construyó la HU-05. Su aporte técnico no es el
CRUD, sino tres decisiones:

1. **Una tabla propia con historial**, porque el reparto se consulta a diario y
   porque explica las fichas que cada persona levantó.
2. **Unicidad parcial** (`WHERE activa`), que es lo que permite reasignar a alguien
   que ya estuvo sin duplicar su asignación vigente.
3. **Casillas en vez de «agregar»**, que convierte una reasignación en una sola
   operación y en una sola fila de bitácora.

Y aporta algo que no es técnico: es la primera historia con **dos protagonistas**. El
supervisor reparte y el censista recibe; sin la segunda mitad, la primera no sirve.

### 14.2 Lo que demuestra sobre el diseño anterior

Tercera historia consecutiva **sin agregar un permiso al catálogo**. El permiso que
usa se sembró en la HU-04 con una descripción que anticipaba exactamente esta
funcionalidad. Ese es el indicador de que el modelo de autorización estaba bien
planteado: las historias nuevas se apoyan en él en vez de forzarlo.

---

## 15. Posibles preguntas del profesor

**¿Por qué una tabla propia y no un `ManyToManyField`, si en la HU-04 usó un M2M
simple para los permisos?**
Porque las dos situaciones se parecen solo en la forma. Los permisos de un rol se
configuran una vez y se consultan por código; el reparto del trabajo se **consulta a
diario en una pantalla** y necesita datos propios (quién asignó, cuándo,
observaciones) e historial. La HU-04 pudo delegar el «quién y cuándo» a la bitácora
porque nadie lee esa información para trabajar; aquí sí se lee.

**¿Por qué el índice único es parcial?**
Porque un `unique(sector, censista)` normal impediría volver a asignar a alguien que
ya estuvo, ya que su fila histórica seguiría en la tabla. Y sin ninguna restricción se
podría duplicar una asignación vigente. «Único entre las activas» es exactamente la
regla del negocio, y PostgreSQL la implementa con un índice parcial.

**¿Qué pasa si retiro a alguien y luego se lo vuelvo a asignar?**
Se **reactiva su fila histórica** en vez de crear una nueva. Así no se acumula una
fila por cada ida y vuelta y se conserva un solo registro por persona y sector.

**¿Por qué un censista puede entrar a «Mis sectores» sin permiso?**
Porque el sistema de permisos gobierna el acceso a módulos y a datos de otras
personas, y esto no es ninguna de las dos: es la pantalla que le dice a alguien cuál
es su trabajo. Un permiso revocable ahí no expresaría una decisión operativa, solo la
posibilidad de inutilizar una cuenta. Lo que sí protege la vista es que filtra por
`request.user` y **no acepta ningún parámetro**: no hay forma de pedir los sectores
de otra persona.

**¿Puede el supervisor crear sectores?**
No. Tiene `operativos.asignar_sector` pero no `operativos.gestionar`: **reparte el
territorio, no lo dibuja**. Hay una prueba que lo verifica. Si un operativo lo
necesitara, el administrador puede concederle el permiso desde la matriz sin tocar
código.

**¿Qué pasa si deshabilito la cuenta de un censista que tiene sectores?**
Su asignación no se toca —sigue siendo la explicación de las fichas que levantó—,
pero la interfaz lo señala con un aviso en el panel y en la lista de casillas,
porque un sector cubierto por alguien que no puede iniciar sesión **parece cubierto y
no lo está**. La decisión de retirarlo queda en el supervisor.

**¿Se puede repartir el trabajo de un operativo terminado?**
No. `Sector.puede_recibir_asignaciones()` lo impide, y se comprueba en el GET y en el
POST, no ocultando el botón. El panel **sí** se puede consultar: el reparto histórico
es información legítima, solo no se puede modificar.

**¿Cómo garantiza que no queda territorio sin cubrir?**
No lo impide —puede que todavía no haya a quién asignarle—, pero lo hace **imposible
de ignorar**: el contador aparece en rojo en el panel y en el panel del supervisor, las
filas afectadas se resaltan, hay un filtro «solo los que no tienen a nadie», y al
retirar a la última persona la pantalla advierte explícitamente que el sector quedará
sin personal.

**¿Por qué generalizó `describir_cambio_permisos` en vez de escribir una función
nueva?**
Porque las dos operaciones son la misma: comparar dos conjuntos y narrar la
diferencia. Duplicarla habría significado que una corrección se hiciera en un sitio y
se olvidara en el otro. Se generalizó **al aparecer el segundo caso**, no antes:
generalizar con un solo caso de uso lleva a inventar parámetros que nadie necesita.
Hay una prueba que confirma que la HU-04 no cambió de comportamiento.

---

## 16. Conclusión técnica

La HU-06 completa el ciclo que la HU-05 abrió: un territorio dibujado que ahora tiene
responsables, con el registro de quién cubre qué, desde cuándo y con qué
instrucciones. Su valor no está en la operación de asignar —que es sencilla— sino en
las propiedades que el modelo garantiza alrededor de ella: que una asignación no se
pueda duplicar mientras esté vigente, que se pueda repetir en el tiempo sin perder el
rastro anterior, que las dos columnas que describen una baja no puedan contradecirse,
y que retirar a alguien nunca borre la información que explica el trabajo que hizo. En
un sistema de registro social eso último no es una comodidad: la trazabilidad entre
un dato del censo y la persona que lo levantó es parte de su validez.

En el plano de la ingeniería, la historia confirma por tercera vez que el modelo de
autorización de la HU-04 estaba bien planteado —el permiso que usa se sembró entonces
con la descripción exacta de esta funcionalidad— y aporta dos ejemplos de disciplina
que conviene señalar. El primero es la generalización de `describir_cambio_permisos`,
hecha al aparecer el segundo caso de uso y no antes, con una prueba que fija que el
comportamiento anterior no cambió. El segundo es que la prueba de rendimiento de la
HU-05 **impidió** introducir un problema N+1 en la ficha del operativo: una prueba que
no solo documenta una propiedad, sino que la defiende cuando el código crece.

Las 124 pruebas propias, integradas en las 546 del proyecto, se verificaron además
contra regresiones deliberadas para confirmar que fallan cuando deben.
