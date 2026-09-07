# HU-20 · Exportar la base consolidada en Excel y CSV

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como administrador o supervisor, quiero exportar la base consolidada en formatos Excel y CSV para realizar análisis externos.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · openpyxl 3.1.5 · `csv` (librería estándar)
**Estado:** implementada y verificada con **42 pruebas automáticas** propias (**1.423** en total en el proyecto → `python manage.py test` → OK)

> No es la HU-19 con un formato más. La HU-19 exporta **agregados** —conteos, sin un
> solo dato de una familia—; esta historia exporta la **base cruda**, una fila por
> persona con nombre, RUT, teléfono e ingreso del hogar. Son dos capacidades de
> gravedad distinta, y por eso viven detrás de permisos distintos.

> **Ampliación de alcance 1 (posterior a la implementación original):** la historia
> nació "Como administrador" y la 0008 concedía `reportes.exportar_base` solo a ese
> rol. Se amplió a Supervisor con la migración `0009_exportar_base_supervisor` —ver
> §4 y §5— sin renombrar el número de historia ni reescribir la 0008 ya aplicada.

> **Ampliación de alcance 2 (posterior a la anterior):** además de exportar la base
> cruda, ahora hay una pantalla que la RESUME en indicadores y gráficos —sin un solo
> dato personal— para dimensionar campañas de ayuda (padrinazgo, quintal de harina).
> Vive detrás de `reportes.ver`, no de `reportes.exportar_base` —ver §13—.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Decisiones de diseño, conversadas antes de programar](#2-decisiones-de-diseño)
3. [`Integrante.base_consolidada()`: una fila por persona](#3-base_consolidada)
4. [Un permiso nuevo, y por qué no reutilizar `reportes.exportar`](#4-un-permiso-nuevo)
5. [`reportes.exportar_base` se concede solo al Administrador, explícitamente](#5-la-migración)
6. [Excel y CSV comparten el mismo armado](#6-excel-y-csv)
7. [Dónde se ve](#7-dónde-se-ve)
8. [Archivos creados y modificados](#8-archivos)
9. [Pruebas](#9-pruebas)
10. [Verificación manual](#10-verificación-manual)
11. [Explicación para la defensa](#11-explicación-para-la-defensa)
12. [Posibles preguntas del profesor](#12-posibles-preguntas-del-profesor)
13. [Ampliación: panel de indicadores para campañas de ayuda](#13-panel-de-campañas)
14. [Posibles preguntas del profesor (ampliación §13)](#14-posibles-preguntas-del-profesor-ampliación-13)

---

## 1. Explicación inicial

La HU-19 (recién anterior) exporta reportes de resultados: conteos por estado, por
sector, por censista. Esta historia pide algo distinto y lo dice con otra palabra —
**"la base consolidada"**, no "un reporte"—: la información en bruto que se levantó,
lista para que alguien fuera de OPSO la abra en un programa de análisis estadístico y
cruce variables que ningún reporte agregado puede anticipar (¿el nivel educacional se
relaciona con el ingreso del hogar? ¿la tenencia de la vivienda varía por comuna?).

No existía nada que reutilizar para esto —ni siquiera lo que dejó la HU-19—: los
reportes de esa historia trabajan sobre `Encuesta` y agregan; esta trabaja sobre
`Integrante`, la tabla más fina de todo el modelo, y no agrega nada. Antes de escribir
código se conversaron cuatro decisiones que el enunciado no resolvía por sí solo (ver
§2), porque cada una tiene una alternativa razonable y elegir mal habría significado
reescribir el diseño a mitad de camino.

---

## 2. Decisiones de diseño

| Pregunta | Respuesta | Por qué |
|---|---|---|
| **¿Qué representa cada fila?** | Una persona | Es el formato estándar para análisis demográfico: edad, sexo, educación, ocupación por individuo. Una fila por hogar perdería esa dimensión. |
| **¿Se incluyen nombre, RUT y teléfono?** | Sí, completos | A diferencia de la HU-19, aquí se decidió no recortar: es *la* base consolidada, no una versión anonimizada de ella. La consecuencia de esa decisión es el permiso propio de §4. |
| **¿Qué encuestas entran?** | Las que tienen hogar registrado, salvo las `ANULADA` | Un supervisor anuló esas porque decidió que ese dato no debía contar (duplicado, información inválida); una base para análisis externo no debe arrastrar lo que el propio sistema ya descartó. Sí entran las `OBSERVADA` y las `COMPLETADA` sin validar todavía: tienen datos reales, aunque el control de calidad no haya terminado. |
| **¿Desde dónde se descarga?** | Una tarjeta nueva en el panel del administrador, sin filtros | A diferencia de la HU-19 (que exporta "lo que la bandeja está mostrando"), esta historia pidió la base completa. Añadir filtros habría sido resolver un problema que nadie planteó. |

---

## 3. `base_consolidada()`

```python
@classmethod
def base_consolidada(cls):
    calificados = (
        cls.objects.exclude(grupo_familiar__encuesta__estado=EstadoEncuesta.ANULADA)
        .select_related(...)   # vivienda, zona, sector, comuna, región, operativo
        .order_by(...)         # comuna, sector, dirección, hogar, fecha de nacimiento
    )
    return [_fila_base_consolidada(integrante) for integrante in calificados]
```

Vive en `Integrante` (`fichas/models.py`) porque cada fila del resultado **es** un
integrante —"encuestas con hogar registrado" no necesita filtrarse aparte: es la
propia definición de la tabla; basta con excluir las `ANULADA`—.

Devuelve una **lista de diccionarios**, no un queryset. Es la misma separación que ya
usa `Encuesta.resumen_para_reporte()` (HU-19): quien arma el Excel o el CSV
(`fichas/reportes.py`) no necesita saber de Django ni de relaciones, solo iterar filas
planas con las mismas 33 claves. `_fila_base_consolidada()` es una función de módulo y
no un método de `Integrante`, porque lee otros tres modelos además de sí misma
(`GrupoFamiliar`, `Encuesta`, `Vivienda` y su jerarquía territorial) y ponerla como
método sugeriría que le pertenece más a uno que a los otros.

El `select_related` cubre las ocho relaciones de uno-a-uno/uno-a-muchos que la fila
necesita (vivienda, zona, sector, comuna, región, operativo, hogar, encuesta), así que
la exportación completa cuesta **una sola consulta**, no una por persona.

---

## 4. Un permiso nuevo

`reportes.exportar` (HU-19) ya estaba en el catálogo y ya lo tenía el rol Supervisor
completo. Reutilizarlo aquí habría significado que cualquier supervisor —sin que nadie
lo decidiera explícitamente— pudiera descargar nombre, RUT, teléfono e ingreso de cada
familia del operativo, porque ya tenía el permiso para otra cosa completamente
distinta (conteos agregados).

Por eso esta historia agrega `reportes.exportar_base` al catálogo, un permiso
**nuevo y separado**. En su versión original el enunciado decía "Como administrador"
—no "supervisor o administrador", como sí decía la HU-19— y este permiso lo
respetaba: nació sin asignárselo a Supervisor ni a Censista, así que solo el
Administrador podía exportar la base hasta que alguien, explícitamente, decidiera lo
contrario desde la matriz de la HU-04.

**Ese "alguien" terminó siendo el propio alcance de la historia**, revisado después
de la implementación original: se decidió que el Supervisor también necesita la base
consolidada para su propio análisis externo, sin pasar por el Administrador cada vez.
La forma de concederlo respeta exactamente el mecanismo que la 0008 ya dejó abierto
—una fila más en `Rol.permisos`, no un `if` de rol en la vista—: la migración
`0009_exportar_base_supervisor` (§5) hace por el Supervisor lo mismo que la 0008 hizo
por el Administrador. El permiso se mantiene fuera del alcance de Censista.

---

## 5. Las migraciones

```
usuarios/migrations/0008_permiso_exportar_base.py
usuarios/migrations/0009_exportar_base_supervisor.py
```

La 0008 agrega la fila del permiso al catálogo y la concede **explícitamente al rol
ADMINISTRADOR**, con `administrador.permisos.add(permiso)`. Es el mismo criterio que
ya aplicó `0005_permisos_iniciales` para el reparto inicial: `Usuario.tiene_permiso()`
ya le concede todo al administrador de forma implícita sin mirar la tabla, así que el
`.add()` no es necesario para que el administrador pueda exportar —eso ya funcionaría
igual—. Es necesario para que la **matriz de permisos no mienta**: sin la fila en
`Rol.permisos`, la pantalla de la HU-04 mostraría la celda del administrador sin
marcar para esta capacidad, y sí la tiene.

`borrar_permiso()` (la operación inversa de la 0008) borra la fila del `Permiso`:
PostgreSQL limpia en cascada la tabla intermedia `usuarios_rol_permisos`, igual que ya
documentó la HU-04 en `0005_permisos_iniciales`.

La 0009 hace lo mismo que la 0008, pero para el rol SUPERVISOR: un `.add()` aditivo e
idempotente sobre el permiso que la 0008 ya creó. Se escribió como migración nueva y
no como edición de la 0008 porque **una migración ya aplicada en otro entorno no se
reescribe**: el historial de despliegues de este proyecto asume que cada migración
existente es inmutable, y corregir el alcance de una decisión anterior se hace hacia
adelante, con una migración más, igual que ya se hace con cualquier otro cambio de
esquema o de datos. Su reversa (`retirar_a_supervisor`) solo desvincula el permiso del
rol Supervisor —no borra el `Permiso` ni toca al Administrador—, porque esa fila y esa
concesión siguen siendo responsabilidad de la 0008.

A diferencia del Administrador, el Supervisor **no** tiene ningún bypass en
`Usuario.tiene_permiso()`: para él, el `.add()` de la 0009 es lo único que abre la
puerta, no solo lo que evita que la matriz mienta.

**Consecuencia comprobada con una prueba** (`test_el_censista_puede_si_la_matriz_se_lo_concede`):
si el administrador concede `reportes.exportar_base` a un tercer rol desde la matriz,
ese rol puede exportar la base igual, sin ningún cambio de código. No hay ningún
`if usuario.rol == ADMINISTRADOR` ni `in (ADMINISTRADOR, SUPERVISOR)` escondido en la
vista — la puerta es el permiso, no el rol, exactamente como establece la arquitectura
de permisos desde la HU-04.

---

## 6. Excel y CSV

```python
COLUMNAS_BASE_CONSOLIDADA = (
    ("operativo", "Operativo"),
    ...
    ("cerrada_en", "Fecha de cierre"),
)  # 33 columnas

def construir_base_excel(filas) -> Workbook: ...
def construir_base_csv(buffer, filas) -> None: ...
```

Las dos funciones viven en `fichas/reportes.py`, junto a las de la HU-19, y comparten
`COLUMNAS_BASE_CONSOLIDADA` a través de `_tabla_base_consolidada()`: una sola lista
define el orden y las etiquetas de las columnas para los dos formatos, así que agregar
una columna el día de mañana es una entrada más ahí, no un cambio en dos archivos.

A diferencia del reporte de la HU-19, aquí no hay bloques ni resumen: es una tabla
ancha y plana de 33 columnas, el formato que un análisis externo espera poder cargar
directamente en un programa estadístico. El Excel fija el encabezado en negrita y
congelado (`freeze_panes = "A2"`) para que no se pierda al desplazarse por cientos de
filas; el CSV usa el módulo estándar `csv` de Python —no hace falta ninguna librería
para esto—.

**Un detalle que costó una prueba encontrar:** `cerrada_en` es un `datetime` con zona
horaria (`timezone.localtime()`), y Excel no admite datetimes con tzinfo —
`openpyxl` lanza `TypeError` al guardarlo—. La fila lo escribe con
`.replace(tzinfo=None, microsecond=0)` **después** de convertir a hora local: no es un
cambio de hora, es soltar una etiqueta que ya cumplió su función y limpiar el ruido de
los microsegundos, que no aporta nada a un archivo pensado para leerse.

---

## 7. Dónde se ve

Una tarjeta **"Base consolidada"** en `templates/dashboards/administrador.html`, con
dos botones —Excel en verde, CSV en azul (outline)— y una advertencia explícita:
*"Incluye nombre, RUT, teléfono e ingreso del hogar de cada familia: es información
personal, trátala en consecuencia"*. Se retiró de la misma plantilla la viñeta
*"Exportar reportes consolidados del censo"* de "Próximas historias de usuario": esta
historia (junto con la HU-19) es exactamente eso, ya implementado.

La misma tarjeta —idéntico marcado, mismo texto de advertencia— se agregó también a
`templates/dashboards/supervisor.html` cuando se amplió el alcance a ese rol: no hay
una segunda plantilla parcial compartida porque son dos archivos con layouts propios y
la tarjeta es autocontenida; duplicarla ahí es más simple que extraer un include para
un solo bloque de HTML que ya vive detrás del mismo permiso en los dos casos.

La tarjeta se protege con `{% if user|tiene_permiso:"reportes.exportar_base" %}` en
ambas plantillas, el mismo patrón que ya usan los botones de la HU-19 en la bandeja de
revisión. Para el Administrador esa condición es siempre verdadera —su vista ya exige
el rol, que además hace bypass de cualquier permiso—; para el Supervisor depende
enteramente de la fila que dejó la migración 0009, así que si el permiso se le
retirara desde la matriz, la tarjeta desaparecería de su panel sin tocar la plantilla.

---

## 8. Archivos

### Creados (implementación original)

```
usuarios/migrations/0008_permiso_exportar_base.py    agrega y concede el permiso nuevo
backend/docs/HU-20_base_consolidada.md                este documento
```

### Modificados (implementación original)

```
backend/fichas/models.py
    Integrante
    + base_consolidada() (classmethod)
    + _si_no() (función de módulo)
    + _fila_base_consolidada() (función de módulo)

backend/fichas/reportes.py
    + import csv
    + COLUMNAS_BASE_CONSOLIDADA
    + _tabla_base_consolidada()
    + construir_base_excel()
    + construir_base_csv()

backend/fichas/views.py
    + import construir_base_csv, construir_base_excel
    + BaseConsolidadaMixin
    + ExportarBaseExcelView
    + ExportarBaseCSVView

backend/fichas/urls.py
    + base-consolidada.xlsx -> base_consolidada_excel
    + base-consolidada.csv  -> base_consolidada_csv

backend/templates/dashboards/administrador.html
    + {% load permisos %}
    + tarjeta «Base consolidada»
    ~ se retira la viñeta ya satisfecha de «Próximas historias de usuario»

backend/usuarios/tests_permisos.py
    ~ 4 conteos de permisos ajustados: 19→20 en el catálogo, 18→19 en los
      "activos del administrador menos uno", 19→20 en la matriz

backend/fichas/tests.py
    + 18 pruebas, sección rotulada # HU-20 — 77. BASE CONSOLIDADA (EXCEL Y CSV)

backend/README.md
    ~ fila de HU-20: «✅ Implementada», con enlace
```

### Creados (ampliación de alcance a Supervisor)

```
usuarios/migrations/0009_exportar_base_supervisor.py    concede el permiso al Supervisor
```

### Modificados (ampliación de alcance a Supervisor)

```
backend/fichas/views.py
    ~ docstring de BaseConsolidadaMixin: menciona las dos migraciones y los dos roles

backend/templates/dashboards/supervisor.html
    + {% load permisos %}
    + tarjeta «Base consolidada» (mismo marcado que en administrador.html)

backend/fichas/tests.py
    ~ ExportarBaseTest: se reemplaza test_el_supervisor_no_puede_aunque_tenga_reportes_exportar
      y test_el_supervisor_puede_si_la_matriz_se_lo_concede por
      test_el_supervisor_descarga_el_excel, test_el_supervisor_descarga_el_csv,
      test_el_supervisor_pierde_acceso_si_se_retira_solo_ese_permiso y
      test_el_censista_puede_si_la_matriz_se_lo_concede
    + TarjetaBaseConsolidadaTest.test_el_supervisor_ve_la_tarjeta_con_los_enlaces

backend/docs/HU-20_base_consolidada.md
    ~ este documento, actualizado sin cambiar el número de historia
```

Dos migraciones de **datos** (`0008_permiso_exportar_base`, `0009_exportar_base_supervisor`):
no se agregó ningún campo ni tabla nueva en ninguna de las dos.
`makemigrations --check --dry-run` sigue respondiendo "No changes detected".

---

## 9. Pruebas

```bash
cd backend
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.BaseConsolidadaTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ConstruirBaseExcelTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ConstruirBaseCsvTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ExportarBaseTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.TarjetaBaseConsolidadaTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test usuarios.tests_permisos    # conteos ajustados
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test                            # 1.389 en total
```

| Clase | Qué comprueba |
|---|---|
| `BaseConsolidadaTest` | una fila por persona; incluye los datos de vivienda, hogar y persona; excluye las `ANULADA`; una encuesta sin hogar no aporta filas; no depende del estado (`COMPLETADA`, `OBSERVADA`, `VALIDADA` aportan igual) |
| `ConstruirBaseExcelTest` | el encabezado coincide con `COLUMNAS_BASE_CONSOLIDADA`; sin filas queda solo el encabezado |
| `ConstruirBaseCsvTest` | mismo encabezado, leído de vuelta con `csv.reader` |
| `ExportarBaseTest` | administrador y supervisor descargan ambos formatos por defecto (migraciones 0008 y 0009) con `Content-Type`/`Content-Disposition` correctos; el supervisor pierde el acceso si se le retira solo `reportes.exportar_base` —sigue teniendo `reportes.exportar` de la HU-19, así que son permisos distintos aunque hoy compartan dueño—; un tercer rol (censista) puede si la matriz se lo concede explícitamente, demostrando que la puerta sigue siendo el permiso y no una lista de roles fija; censista (por defecto) y anónimo no pueden; el contenido coincide con `base_consolidada()`; las anuladas quedan fuera también desde la vista |
| `TarjetaBaseConsolidadaTest` | el administrador y el supervisor ven la tarjeta con los dos enlaces, cada uno en su propio panel |

---

## 10. Verificación manual

Con `manage.py shell` sobre PostgreSQL, tras aplicar la migración y con los datos de
`crear_encuestas_demo`:

```python
from usuarios.models import Permiso, Rol, RolCodigo
Rol.objects.get(codigo=RolCodigo.ADMINISTRADOR).permisos.filter(
    codigo="reportes.exportar_base"
).exists()   # True
Rol.objects.get(codigo=RolCodigo.SUPERVISOR).permisos.filter(
    codigo="reportes.exportar_base"
).exists()   # True (desde la 0009; era False antes de ampliar el alcance)
Permiso.objects.count()   # 20 — sigue siendo un permiso nuevo, no dos

from fichas.models import Integrante
len(Integrante.base_consolidada())   # 41, sobre los datos de demostración
```

| Paso | Resultado |
|---|---|
| `construir_base_excel(filas)` + `.save()`, reabierto con `openpyxl.load_workbook` | 42 filas (encabezado + 41 personas), 33 columnas, encabezado en negrita y congelado |
| `construir_base_csv(buffer, filas)` | CSV de 42 líneas, acentos y «ñ» correctos en UTF-8 |
| `GET /encuestas/base-consolidada.xlsx` como administrador | 200, `Content-Type` de Excel |
| Mismo endpoint, como supervisor | 200 (desde la 0009; antes de ampliar el alcance, sin concesión de la matriz, era 302) |
| Mismo endpoint, como censista (sin concesión de la matriz) | 302 |

**Nota fuera del alcance de esta historia:** la verificación mostró que el único
registro de `Comuna` de los datos de demostración ("Concepción") está enlazado a la
región "Arica y Parinacota" en vez de "Biobío" — un dato de la semilla de demostración,
no del código de esta HU. `base_consolidada()` refleja fielmente lo que hay en la base;
no se corrigió porque tocar los datos de demostración no es parte de lo que pidió esta
historia.

---

## 11. Explicación para la defensa

**En una frase:** esta historia exporta la base cruda del censo —una fila por
persona, con sus datos personales— detrás de un permiso nuevo y separado del que ya
usa la HU-19 para exportar agregados; nació exclusiva del Administrador y se amplió
después al Supervisor con una segunda migración aditiva, sin tocar la primera ni
convertir la puerta en un `if` de rol.

**Lo que conviene poder defender:**

1. **Un permiso nuevo, no una reutilización.** `reportes.exportar` (HU-19) y
   `reportes.exportar_base` (esta historia) protegen cosas distintas a propósito:
   conteos sin PII, y datos personales completos. El enunciado original lo marcaba
   —"Como administrador", no "supervisor o administrador"— y el permiso lo respetó sin
   necesidad de un `if` de rol en el código.
2. **Las migraciones conceden el permiso al rol, no lo hardcodean en la vista.** El
   administrador puede exportar por herencia del rol (vía la 0008) y también por el
   bypass de `Usuario.tiene_permiso()`; el supervisor puede exportar por herencia del
   rol (vía la 0009), sin ningún bypass —para él, esa fila es la única puerta—.
   Cualquier otro rol puede recibir la misma capacidad desde la matriz de la HU-04, sin
   desplegar código nuevo. Hay una prueba que lo demuestra concediéndoselo al Censista
   en caliente.
3. **El alcance se amplió con una migración nueva, no editando la anterior.** Cuando
   la historia creció de "solo Administrador" a "Administrador y Supervisor", la 0008
   ya podía estar aplicada en otro entorno: reescribirla habría significado depender de
   que todos los entornos la reaplicaran desde cero. La 0009 hace la misma operación
   que la 0008 —un `.add()` idempotente— pero para el rol nuevo, y su reversa retira
   solo lo que ella agregó.
4. **Una fila por persona, no por hogar.** Es el formato que un análisis externo
   real necesita —demografía por individuo—, y `Integrante` ya es exactamente esa
   tabla: no hizo falta inventar una vista ni una tabla intermedia.
5. **Función pura, reutilizable en dos formatos.** `base_consolidada()` no sabe de
   Excel ni de CSV; `reportes.py` no sabe de Django. La misma separación que ya
   estableció la HU-19, aplicada a filas en vez de a agregados.

---

## 12. Posibles preguntas del profesor

**¿Por qué no reutilizar `reportes.exportar`, si de todos modos ya lo tenía el
Supervisor?**
Porque en el momento en que se escribió esta historia eso habría ampliado, sin que
nadie lo decidiera explícitamente, el acceso del rol Supervisor completo a nombre,
RUT, teléfono e ingreso de cada familia del operativo. Un permiso nuevo obliga a que
esa decisión se tome a propósito, desde la matriz —y de hecho, cuando después sí se
decidió dársela al Supervisor, se hizo exactamente así: concediendo el permiso nuevo,
no reutilizando `reportes.exportar`—.

**Si al final el Supervisor también puede exportar la base, ¿para qué sirvió separar
los permisos?**
Para que fuera una decisión explícita y reversible, no un efecto colateral. Hoy el
Supervisor tiene los dos permisos, pero siguen siendo dos filas distintas en
`Rol.permisos`: se le puede retirar `reportes.exportar_base` sin tocar
`reportes.exportar`, y viceversa. Antes de la 0009 eso no era posible con un solo
permiso compartido —quitarle uno le habría quitado el otro—.

**¿Por qué la migración concede el permiso al Administrador si igual lo recibe por el
bypass de `Usuario.tiene_permiso()`?**
Para que la matriz de permisos de la HU-04 no mienta. El bypass hace que el
administrador **pueda** exportar sin la fila en `Rol.permisos`; sin ella, la pantalla
que muestra "quién puede hacer qué" mostraría su celda vacía para esta capacidad,
aunque sí la tiene. Es el mismo argumento que ya usó `0005_permisos_iniciales` para el
reparto inicial completo. El Supervisor no tiene ese bypass, así que para él la 0009
no es solo cosmética: es la única razón por la que puede exportar.

**¿Por qué una migración nueva (0009) y no editar la 0008 para agregar también al
Supervisor?**
Porque la 0008 pudo haberse aplicado ya en otro entorno —desarrollo de otra persona,
un despliegue previo—, y Django no reaplica una migración ya marcada como aplicada
aunque se le cambie el contenido: el entorno se quedaría con el estado viejo sin que
`makemigrations`/`migrate` avisaran de nada raro. Corregir hacia adelante con una
migración nueva es el mismo criterio que ya sigue todo el historial del proyecto para
cualquier cambio de esquema o de datos.

**¿Por qué una fila por persona y no por hogar?**
Porque es el nivel al que un análisis externo real pregunta: ¿cómo varía la
escolaridad por sexo?, ¿el ingreso del hogar se relaciona con la tenencia de la
vivienda? Esas preguntas necesitan una fila por individuo. Un archivo por hogar
perdería la variación dentro de cada familia.

**¿Por qué se excluyen las encuestas `ANULADA` y no, por ejemplo, solo las
`VALIDADA`?**
Porque "anulada" es una decisión activa de un supervisor de que ese dato no cuenta
—duplicado, información inválida—, y arrastrarlo a un análisis externo repetiría un
error que el propio sistema ya corrigió. Exigir `VALIDADA` habría sido más estricto de
lo que pidió la historia: descartaría datos reales de encuestas `COMPLETADA` u
`OBSERVADA` que todavía no terminaron su revisión pero que sí reflejan lo que se
levantó en terreno.

**¿Se agregó algún campo o tabla nueva?**
No. Todos los datos ya existían desde la HU-08 (vivienda y hogar) y la HU-09
(integrantes). La única migración es de datos: agrega una fila al catálogo de
permisos y la concede al rol Administrador.

---

## 13. Panel de campañas

### 13.1. Por qué no es una tercera exportación

La base consolidada (§1-§12) responde "dame TODO, con nombre y RUT, para cruzarlo
fuera del sistema". Esta ampliación responde una pregunta distinta y más frecuente:
"¿cuántas ayudas necesito conseguir?" —¿cuántos padrinazgos para una campaña de
apadrinamiento de niños?, ¿cuántos quintales de harina para cubrir a las familias de
un sector?—. Son preguntas de **tamaño**, no de **identidad**: quien las hace no
necesita saber QUIÉN es cada niño o cada familia, necesita un número en el que
basar una meta de recolección.

Por eso esta pantalla no es "la base consolidada en un tercer formato". Es la
misma base, RESUMIDA hasta el punto de no llevar un solo dato identificable, y
mostrada con gráficos porque una cifra se entiende más rápido en una barra que en
una fila de una tabla de 33 columnas.

### 13.2. Qué muestra

Cuatro indicadores, elegidos por ser los que una campaña de ayuda social típica
necesita para dimensionarse, no por agotar todo lo que el censo permite calcular:

| Indicador | Para qué campaña sirve | De dónde sale |
|---|---|---|
| Niños, niñas y adolescentes por tramo de edad (0-5, 6-12, 13-17) | Padrinazgo | `Integrante.indicadores_campanas()` |
| Adultos mayores (60 años o más) | Abrigo, leña, acompañamiento a la tercera edad | `Integrante.indicadores_campanas()` |
| Personas con discapacidad | Ayudas técnicas, accesibilidad | `Integrante.indicadores_campanas()` |
| Hogares, totales y por comuna/sector | Ayuda material por hogar (quintal de harina) | `GrupoFamiliar.indicadores_familias()` |

El umbral de 60 años para "adulto mayor" no es arbitrario: es el que fija SENAMA
(Ley N° 19.828) para Chile, y vive como constante `Integrante.EDAD_ADULTO_MAYOR`
junto a `EDAD_ESCOLARIDAD` y `EDAD_OCUPACION`, que ya eran umbrales legales del
mismo tipo. Los tramos de infancia (`Integrante.TRAMOS_INFANCIA`) sí son una
elección de esta pantalla —no un umbral legal— pensada para separar primera
infancia, escolar y adolescente, que es como una campaña de padrinazgo suele
organizar sus cupos.

Es una lista abierta a propósito: agregar un quinto indicador el día de mañana es
una entrada más en `indicadores_campanas()` o `indicadores_familias()`, no una
pantalla nueva.

### 13.3. Por qué `reportes.ver` y no `reportes.exportar_base`

`reportes.exportar_base` protege datos personales completos (§4); esta pantalla no
expone ninguno, así que ponerla detrás de ese permiso habría sido más restrictivo
de lo necesario —y por la razón inversa a la de §4, también habría sido
incoherente: el mismo permiso protegiendo cosas de gravedad completamente
distinta—.

`reportes.ver` ("Consultar los reportes de avance") ya existía desde la migración
0005 de la HU-04, ya lo tienen el Administrador y el Supervisor por defecto, y es
literalmente la descripción de esta pantalla: MIRAR el estado del operativo, sin
descargar nada. Por eso esta ampliación no necesita ninguna migración de permisos
propia —a diferencia de la ampliación del §13 anterior (la 0009)—: el permiso que
hacía falta ya estaba sembrado y ya repartido.

### 13.4. `PanelCampanasView`

```
GET /encuestas/base-consolidada/campanas/    fichas.views.PanelCampanasView
```

Un `TemplateView` protegido por `PermisoRequeridoMixin` con
`permisos_requeridos = ("reportes.ver",)`, igual patrón que `ReporteMixin` (HU-19).
Su `get_context_data()` solo llama a los dos classmethods y arma el contexto: no
hay lógica de negocio en la vista, la cuentan `Integrante.indicadores_campanas()` y
`GrupoFamiliar.indicadores_familias()`, en el modelo, como marca la convención del
proyecto.

### 13.5. Los gráficos: Chart.js vendorizado

Es la primera librería de JavaScript de APLICACIÓN del proyecto —hasta ahora todo
era Bootstrap (interacción de UI) sobre vistas 100% renderizadas en servidor—.
Vendorizada igual que Bootstrap, en `static/vendor/chartjs/chart.umd.min.js`: el
proyecto funciona sin internet (ver CLAUDE.md) y un `<script src="https://cdn...">`
lo habría roto.

Los datos llegan del contexto de Django al `<canvas>` con el filtro `json_script`
de Django (`{{ indicadores.ninos.tramos|json_script:"datos-ninos" }}`), no
interpolados a mano en una cadena de JavaScript: es la forma segura de pasar datos
del servidor al cliente que ya ofrece el framework, y evita que un nombre de
comuna con una comilla rompiera el `<script>`.

Cada gráfico es UNA barra por categoría con un solo color de serie —el eje ya
distingue las categorías (el tramo, la comuna), así que el color no necesita cargar
la identidad, y con una sola serie una leyenda sería ruido—. El color
(`#2a78d6`) se tomó de la paleta categórica validada de la guía interna de
visualización de datos del proyecto (no del azul de marca de OPSO, que no pasa el
umbral de contraste sobre fondo blanco para una barra de datos) y pasa las
comprobaciones de esa guía (banda de luminosidad, separación para daltonismo,
contraste). Cada gráfico tiene además una tabla equivalente detrás de un
`<details>` ("Ver como tabla"), por accesibilidad: nadie depende del color o de la
forma para leer el dato.

El desglose por sector (a diferencia del de comuna) se muestra como TABLA y no
como gráfico: puede haber muchos más sectores que comunas, y una tabla de veinte
filas se lee mejor que un gráfico de barras de veinte categorías apretadas.

### 13.6. Dónde se ve

Una tarjeta nueva, **"Indicadores para campañas"**, en `administrador.html` y en
`supervisor.html` —la primera vez que una tarjeta de este tipo se agrega a las dos
plantillas a la vez, porque el permiso que la protege (`reportes.ver`) ya era de
ambos roles desde el día uno—. Un solo botón, "Ver indicadores", sin advertencia de
datos personales: a diferencia de la tarjeta "Base consolidada", aquí no hace
falta, porque no hay ninguno.

Además, un enlace **"Indicadores"** en el menú superior (`templates/base.html`),
junto a "Operativos", "Mis encuestas" y "Revisión": esos tres ya seguían el patrón
de mostrarse según PERMISO y no según rol (ver los `{% comment %}` que ya
explicaban esa decisión en el propio archivo), así que el enlace nuevo solo repite
la misma receta con `reportes.ver`. Queda entre "Revisión" y "Mis sectores".

### 13.7. Archivos

```
backend/fichas/models.py
    Integrante
    + EDAD_ADULTO_MAYOR, TRAMOS_INFANCIA
    + es_adulto_mayor (property)
    + indicadores_campanas() (classmethod)
    GrupoFamiliar
    + indicadores_familias() (classmethod)

backend/fichas/views.py
    + TemplateView (import)
    + PanelCampanasView

backend/fichas/urls.py
    + base-consolidada/campanas/ -> panel_campanas

backend/templates/fichas/panel_campanas.html    la pantalla nueva

backend/templates/dashboards/administrador.html
    + tarjeta «Indicadores para campañas»

backend/templates/dashboards/supervisor.html
    + tarjeta «Indicadores para campañas»

backend/templates/base.html
    + enlace «Indicadores» en el menú superior, detrás de `reportes.ver`

backend/static/vendor/chartjs/chart.umd.min.js    Chart.js 4.5.1, vendorizado

backend/fichas/tests.py
    + 21 pruebas, sección rotulada
      # HU-20 (ampliación) — 77.1 INDICADORES PARA CAMPAÑAS DE AYUDA
```

Ninguna migración de esquema ni de permisos: `reportes.ver` ya existía y ya estaba
repartido. `makemigrations --check --dry-run` sigue respondiendo "No changes
detected".

### 13.8. Pruebas

| Clase | Qué comprueba |
|---|---|
| `IndicadoresCampanasTest` | clasifica correctamente los tramos de infancia; un adulto no cuenta como niño; el umbral de adulto mayor es 60 años inclusive; la discapacidad se cuenta sin importar la edad; excluye las encuestas `ANULADA` |
| `IndicadoresFamiliasTest` | cuenta el total de hogares; agrupa por sector; agrupa por comuna con porcentaje; excluye las encuestas `ANULADA` |
| `PanelCampanasViewTest` | administrador y supervisor pueden ver el panel (200); censista no puede (302, no tiene `reportes.ver`); un anónimo va al login; los indicadores calculados aparecen en el HTML; **ningún dato personal aparece** (nombre del integrante ausente de la respuesta) |
| `BotonPanelCampanasTest` | administrador y supervisor ven el botón "Indicadores para campañas" en su propio panel, con el enlace correcto |
| `MenuIndicadoresTest` | administrador y supervisor ven el enlace "Indicadores" en el menú superior; el censista (sin `reportes.ver`) no lo ve en ninguna pantalla suya |

### 13.9. Explicación para la defensa

**En una frase:** la base consolidada exporta identidad (§1-§12); este panel
exporta magnitud —cuenta personas y hogares sin nombrar a ninguno— y por eso vive
detrás de un permiso de solo lectura que Administrador y Supervisor ya tenían,
en vez de detrás del permiso que protege datos personales.

**Lo que conviene poder defender:**

1. **Un permiso distinto porque la gravedad es distinta, otra vez.** Mismo
   argumento que separó `reportes.exportar` de `reportes.exportar_base` en su
   momento (§4), aplicado ahora para separar "ver agregados" de "descargar PII": la
   pantalla usa el permiso que ya describía exactamente lo que hace, sin necesitar
   uno nuevo ni pedir prestado uno que protege algo distinto.
2. **Cero migraciones nuevas.** No porque se evitara la ampliación anterior (la
   0009 fue necesaria porque el Supervisor no tenía `reportes.exportar_base`), sino
   porque en este caso el permiso correcto —`reportes.ver`— YA estaba sembrado y YA
   repartido desde la HU-04: la arquitectura de permisos no necesitó ningún cambio
   para soportar una capacidad completamente nueva.
3. **La lógica vive en el modelo, no en la vista ni en la plantilla.**
   `indicadores_campanas()` e `indicadores_familias()` son classmethods que
   devuelven diccionarios listos para renderizar; `PanelCampanasView` solo los
   llama. Es la misma separación que ya usan `resumen_para_reporte()` (HU-19) y
   `base_consolidada()` (HU-20).
4. **Chart.js se vendorizó, no se enlazó a un CDN**, por la misma razón que
   Bootstrap: el sistema tiene que funcionar sin internet en terreno.

---

## 14. Posibles preguntas del profesor (ampliación §13)

**¿Por qué un panel con gráficos y no simplemente más columnas en el Excel de la
base consolidada?**
Porque resuelven preguntas distintas para audiencias distintas. La base
consolidada es materia prima para un analista que va a cruzar variables en otro
programa; este panel es la respuesta a una pregunta puntual —"¿cuántos niños hay
para la campaña de este mes?"— para alguien que solo necesita el número, ahora, sin
abrir Excel ni tener PII delante.

**¿Por qué los tramos de edad de la infancia (0-5, 6-12, 13-17) y no otros?**
No corresponden a ningún umbral legal —a diferencia de `EDAD_ADULTO_MAYOR`—: se
eligieron porque separan primera infancia, edad escolar básica y adolescencia, que
es como suelen organizarse los cupos de una campaña de padrinazgo. Al vivir en una
sola constante (`Integrante.TRAMOS_INFANCIA`), cambiarlos —o agregar un tramo— es
una edición ahí, no un cambio esparcido por la vista y la plantilla.

**¿Por qué Chart.js y no gráficos hechos solo con CSS, como las barras de
porcentaje que ya usa la HU-19?**
Porque acá el número de categorías por gráfico no es fijo —depende de cuántos
tramos de edad tengan datos, o de cuántas comunas existan—, y porque un tooltip al
pasar el mouse con el valor exacto es más simple de conseguir con una librería de
gráficos que reconstruyendo esa interacción a mano sobre barras de Bootstrap.
Chart.js es una dependencia nueva, pero se vendorizó exactamente como Bootstrap
para no romper el requisito de funcionar sin internet, y es la única pieza de
JavaScript de aplicación que agrega esta ampliación.

**¿Por qué la tabla de sectores no tiene gráfico, si la de comunas sí?**
Porque el número de comunas es chico y estable, y el de sectores puede crecer con
cada operativo. Un gráfico de barras con muchas categorías se vuelve ilegible antes
que una tabla del mismo tamaño, así que el sector se muestra donde se lee mejor.
