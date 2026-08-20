# HU-20 · Exportar la base consolidada en Excel y CSV

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como administrador, quiero exportar la base consolidada en formatos Excel y CSV para realizar análisis externos.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · openpyxl 3.1.5 · `csv` (librería estándar)
**Estado:** implementada y verificada con **18 pruebas automáticas** propias (**1.389** en total en el proyecto → `python manage.py test` → OK)

> No es la HU-19 con un formato más. La HU-19 exporta **agregados** —conteos, sin un
> solo dato de una familia—; esta historia exporta la **base cruda**, una fila por
> persona con nombre, RUT, teléfono e ingreso del hogar. Son dos capacidades de
> gravedad distinta, y por eso viven detrás de permisos distintos.

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
**nuevo y separado**. El enunciado dice "Como administrador" —no "supervisor o
administrador", como sí decía la HU-19— y este permiso lo respeta: nace sin
asignárselo a Supervisor ni a Censista, así que solo el Administrador puede exportar
la base hasta que alguien, explícitamente, decida lo contrario desde la matriz de la
HU-04.

---

## 5. La migración

```
usuarios/migrations/0008_permiso_exportar_base.py
```

Agrega la fila del permiso al catálogo y la concede **explícitamente solo al rol
ADMINISTRADOR**, con `administrador.permisos.add(permiso)`. Es el mismo criterio que
ya aplicó `0005_permisos_iniciales` para el reparto inicial: `Usuario.tiene_permiso()`
ya le concede todo al administrador de forma implícita sin mirar la tabla, así que el
`.add()` no es necesario para que el administrador pueda exportar —eso ya funcionaría
igual—. Es necesario para que la **matriz de permisos no mienta**: sin la fila en
`Rol.permisos`, la pantalla de la HU-04 mostraría la celda del administrador sin
marcar para esta capacidad, y sí la tiene.

`borrar_permiso()` (la operación inversa) solo borra la fila del `Permiso`: PostgreSQL
limpia en cascada la tabla intermedia `usuarios_rol_permisos`, igual que ya documentó
la HU-04 en `0005_permisos_iniciales`.

**Consecuencia comprobada con una prueba** (`test_el_supervisor_puede_si_la_matriz_se_lo_concede`):
si el administrador concede `reportes.exportar_base` a otro rol desde la matriz, ese
rol puede exportar la base igual, sin ningún cambio de código. No hay ningún
`if usuario.rol == ADMINISTRADOR` escondido en la vista — la puerta es el permiso, no
el rol, exactamente como establece la arquitectura de permisos desde la HU-04.

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

Una tarjeta nueva en `templates/dashboards/administrador.html`, **"Base
consolidada"**, con dos botones —Excel en verde, CSV en azul (outline)— y una
advertencia explícita: *"Incluye nombre, RUT, teléfono e ingreso del hogar de cada
familia: es información personal, trátala en consecuencia"*. Se retiró de la misma
plantilla la viñeta *"Exportar reportes consolidados del censo"* de "Próximas
historias de usuario": esta historia (junto con la HU-19) es exactamente eso, ya
implementado.

La tarjeta se protege con `{% if user|tiene_permiso:"reportes.exportar_base" %}`, el
mismo patrón que ya usan los botones de la HU-19 en la bandeja de revisión. En la
práctica, hoy esa condición es siempre verdadera para quien llega a ver esta pantalla
—`DashboardAdministradorView` ya exige el rol Administrador, que además hace bypass de
cualquier permiso—, pero se mantiene por coherencia con el resto del proyecto y porque
dejaría de ser inerte el día que la matriz conceda el permiso a otro rol con acceso a
otra pantalla.

---

## 8. Archivos

### Creados

```
usuarios/migrations/0008_permiso_exportar_base.py    agrega y concede el permiso nuevo
backend/docs/HU-20_base_consolidada.md                este documento
```

### Modificados

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

Una sola migración de **datos** (`0008_permiso_exportar_base`): no se agregó ningún
campo ni tabla nueva. `makemigrations --check --dry-run` sigue respondiendo "No
changes detected".

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
| `ExportarBaseTest` | administrador descarga ambos formatos con `Content-Type`/`Content-Disposition` correctos; supervisor con `reportes.exportar` (HU-19) **no** puede —son permisos distintos—; el mismo supervisor **sí** puede si la matriz le concede `reportes.exportar_base` explícitamente; censista y anónimo no pueden; el contenido coincide con `base_consolidada()`; las anuladas quedan fuera también desde la vista |
| `TarjetaBaseConsolidadaTest` | el administrador ve la tarjeta con los dos enlaces |

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
).exists()   # False
Permiso.objects.count()   # 20

from fichas.models import Integrante
len(Integrante.base_consolidada())   # 41, sobre los datos de demostración
```

| Paso | Resultado |
|---|---|
| `construir_base_excel(filas)` + `.save()`, reabierto con `openpyxl.load_workbook` | 42 filas (encabezado + 41 personas), 33 columnas, encabezado en negrita y congelado |
| `construir_base_csv(buffer, filas)` | CSV de 42 líneas, acentos y «ñ» correctos en UTF-8 |
| `GET /encuestas/base-consolidada.xlsx` como administrador | 200, `Content-Type` de Excel |
| Mismo endpoint, como supervisor (sin concesión de la matriz) | 302 |

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
usa la HU-19 para exportar agregados, porque son capacidades de gravedad distinta y
mezclarlas habría ampliado silenciosamente el acceso del rol Supervisor.

**Lo que conviene poder defender:**

1. **Un permiso nuevo, no una reutilización.** `reportes.exportar` (HU-19) y
   `reportes.exportar_base` (esta historia) protegen cosas distintas a propósito:
   conteos sin PII, y datos personales completos. El enunciado mismo lo marca —"Como
   administrador", no "supervisor o administrador"— y el permiso lo respeta sin
   necesidad de un `if` de rol en el código.
2. **La migración concede el permiso al rol, no lo hardcodea en la vista.** El
   administrador puede exportar por herencia del rol (vía la migración) y también por
   el bypass de `Usuario.tiene_permiso()`; cualquier otro rol puede recibir la misma
   capacidad desde la matriz de la HU-04, sin desplegar código nuevo. Hay una prueba
   que lo demuestra concediéndoselo al Supervisor en caliente.
3. **Una fila por persona, no por hogar.** Es el formato que un análisis externo
   real necesita —demografía por individuo—, y `Integrante` ya es exactamente esa
   tabla: no hizo falta inventar una vista ni una tabla intermedia.
4. **Función pura, reutilizable en dos formatos.** `base_consolidada()` no sabe de
   Excel ni de CSV; `reportes.py` no sabe de Django. La misma separación que ya
   estableció la HU-19, aplicada a filas en vez de a agregados.

---

## 12. Posibles preguntas del profesor

**¿Por qué no reutilizar `reportes.exportar`, si de todos modos ya lo tenía el
Supervisor?**
Justamente por eso. Reutilizarlo habría ampliado, sin que nadie lo decidiera
explícitamente, el acceso del rol Supervisor completo a nombre, RUT, teléfono e
ingreso de cada familia del operativo. Un permiso nuevo obliga a que esa decisión se
tome a propósito, desde la matriz, si algún día se quiere.

**¿Por qué la migración concede el permiso al Administrador si igual lo recibe por el
bypass de `Usuario.tiene_permiso()`?**
Para que la matriz de permisos de la HU-04 no mienta. El bypass hace que el
administrador **pueda** exportar sin la fila en `Rol.permisos`; sin ella, la pantalla
que muestra "quién puede hacer qué" mostraría su celda vacía para esta capacidad,
aunque sí la tiene. Es el mismo argumento que ya usó `0005_permisos_iniciales` para el
reparto inicial completo.

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
