# HU-19 · Generar reportes en PDF y Excel

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor o administrador, quiero generar reportes en PDF y Excel para compartir resultados del operativo.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3 · ReportLab 5.0.1 · openpyxl 3.1.5
**Estado:** implementada y verificada con **26 pruebas automáticas** propias (**1.371** en total en el proyecto → `python manage.py test` → OK)

> A diferencia de las HU-16, HU-17 y HU-18, esta historia **no tenía nada que reutilizar**:
> no existía app de reportes, ni vista, ni librería de exportación instalada. Lo único que
> ya estaba era el permiso `reportes.exportar`, sembrado por la HU-04 desde antes de que
> hubiera una sola pantalla que lo exigiera.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Decisiones de diseño, y por qué se preguntaron antes de programar](#2-decisiones-de-diseño)
3. [`Encuesta.resumen_para_reporte()`: el mismo dato, listo para dos formatos](#3-resumen_para_reporte)
4. [`fichas/reportes.py`: funciones puras que arman el archivo](#4-fichasreportespy)
5. [Las vistas de exportación](#5-las-vistas)
6. [`reportes.exportar`, no `fichas.ver_todas`](#6-el-permiso)
7. [Reutilizar el filtro exacto de la bandeja](#7-reutilizar-el-filtro)
8. [Por qué ReportLab y no WeasyPrint](#8-por-qué-reportlab)
9. [Archivos creados y modificados](#9-archivos)
10. [Pruebas](#10-pruebas)
11. [Verificación manual](#11-verificación-manual)
12. [Explicación para la defensa](#12-explicación-para-la-defensa)
13. [Posibles preguntas del profesor](#13-posibles-preguntas-del-profesor)

---

## 1. Explicación inicial

Antes de programar nada se revisó qué existía —el mismo paso que ya tomaron todas las
HU de este sprint— y el resultado fue distinto al de las tres anteriores: no había una
app `reportes`, ni una vista que exportara nada, ni `openpyxl` ni ninguna librería de
PDF en `requirements.txt`. Lo único que ya existía era el par de permisos
`reportes.ver` / `reportes.exportar`, sembrados por la migración de la HU-04 como
"historia futura" y ya repartidos al rol Supervisor, sin que ninguna pantalla los
exigiera todavía.

Esta historia es, entonces, la primera de este sprint que agrega una capacidad
realmente nueva: convertir un resumen de resultados en un archivo descargable, en dos
formatos.

---

## 2. Decisiones de diseño

Antes de escribir código se resolvieron tres preguntas que no tenían una respuesta
obvia en el código existente, y que se conversaron explícitamente:

| Pregunta | Respuesta | Por qué |
|---|---|---|
| **¿Qué librería arma el PDF?** | ReportLab | Pura Python, sin dependencias nativas de sistema. La alternativa evaluada, WeasyPrint, convierte HTML/CSS y habría permitido reusar las plantillas Bootstrap, pero exige GTK/Pango instalados aparte del entorno virtual —una complicación real en Windows, donde corre este proyecto en desarrollo—. |
| **¿Qué lleva el reporte?** | Solo los conteos agregados (por estado, por sector, por censista) | Sin datos de las familias. Coincide con el principio de exportar lo mínimo necesario, y evita que un archivo pensado para "compartir resultados del operativo" termine llevando direcciones y nombres de jefes de hogar fuera del sistema. |
| **¿Desde dónde se genera?** | La bandeja de revisión, con sus filtros activos | La HU-18, la historia inmediatamente anterior, le dio a la bandeja filtros de fecha, sector, estado y censista. "Compartir resultados" es casi siempre "compartir lo que estoy mirando ahora mismo", así que el reporte exporta exactamente ese recorte en vez de construir una pantalla de reportes aparte. |

---

## 3. `resumen_para_reporte()`

```python
@classmethod
def resumen_para_reporte(cls, queryset):
    return {
        "total": queryset.count(),
        "generado_en": timezone.localtime(timezone.now()),
        "alertas": cls.resumen_alertas_calidad(queryset),
        "por_estado": [...],    # + porcentaje
        "por_sector": [...],    # + comuna, porcentaje
        "por_censista": [...],  # + validadas, observadas
    }
```

Vive en `Encuesta` (`fichas/models.py`), junto a `resumen_alertas_calidad()` (HU-16), por
la misma razón que aquella: no es un cálculo de una sola pantalla, y **recibe el
queryset ya filtrado** en vez de calcularlo él mismo, para que el mismo método sirva
tanto al Excel como al PDF sin duplicar el criterio de qué encuestas entran.

Un primer borrador de este método solo traía `total`, `por_estado`, `por_sector` y
`por_censista`, cada uno con nombre y un `total` a secas. El usuario lo probó y lo
encontró "pobre", así que se le agregaron cuatro cosas más, todas reutilizando cálculos
que ya existían en vez de inventar reglas nuevas:

- **`alertas`**: exactamente `resumen_alertas_calidad()` (HU-16) aplicado sobre el
  mismo queryset filtrado. El reporte no define una segunda noción de "ficha con
  problemas": usa la misma que ya ve el supervisor en su panel.
- **`generado_en`**: la fecha y hora de la exportación. Un archivo que se comparte
  fuera del sistema —por correo, por un pendrive— pierde el contexto de cuándo se
  generó si no lo lleva escrito encima.
- **`porcentaje`** en `por_estado` y `por_sector`: qué proporción del total filtrado
  representa cada fila, calculado con `_porcentaje(parte, total)` (una función de
  módulo, no un método, porque no le pertenece a ningún estado del modelo).
- **`comuna`** en `por_sector`, y **`validadas`/`observadas`** en `por_censista`: dos
  columnas más por bloque, sacadas de la misma consulta agrupada —una comuna la tiene
  el sector desde la HU-05, y contar validadas/observadas por persona es el mismo
  patrón `Count(filter=Q(...))` que ya usa `DashboardSupervisorView.resumen_revision`
  (HU-13) para los contadores del panel.

Las cuentas de `por_estado`, `por_sector` y `por_censista` son agrupaciones directas
—`values().annotate(Count(...))`— y viven enteras en la base de datos. `por_estado`
traduce el código a su etiqueta legible con `EstadoEncuesta(codigo).label` para no
obligar a quien arma el Excel o el PDF a conocer el `TextChoices`.

---

## 4. `fichas/reportes.py`

Funciones puras: reciben el diccionario de `resumen_para_reporte()` y devuelven el
archivo armado, sin conocer `request` ni `HttpResponse`. Es el mismo criterio que
`usuarios/seguridad.py` y `usuarios/auditoria.py` ya aplican para lógica que no
depende de la petición —se prueban llamándolas directamente, sin simular HTTP—.

```python
def construir_reporte_excel(resumen) -> Workbook: ...
def construir_reporte_pdf(buffer, resumen) -> None: ...
```

El archivo abre con el título, la fecha de generación y un bloque **"Resumen
general"** (total de encuestas y las tres alertas de calidad), y sigue con los tres
bloques agrupados —por estado, por sector, por censista—, cada uno con sus propias
columnas. Los tres se recorren con la misma tupla `BLOQUES`, que describe título,
columnas y cómo sacarle una fila a cada elemento del resumen, para que agregar un
cuarto bloque el día de mañana sea una entrada más en esa lista y no un bloque de
código copiado entre el Excel y el PDF.

Un bloque sin filas —un filtro que no dejó ninguna encuesta de cierto sector, por
ejemplo— no se omite ni se deja con solo el encabezado: los dos formatos escriben
*"Sin datos para este filtro."* en su lugar. Se decidió así para que un reporte vacío
se lea como "no hay nada que mostrar con este filtro", no como un archivo mal armado.

---

## 5. Las vistas

```
GET /encuestas/revision/reporte.xlsx
GET /encuestas/revision/reporte.pdf
```

`ExportarReporteExcelView` y `ExportarReportePDFView` son `View` de una sola acción,
igual que `SubirFotografiaView` o `CapturarUbicacionView` de historias anteriores.
Cada una:

1. Arma el mismo queryset filtrado que vería la bandeja con esos parámetros de URL
   (§7).
2. Le pide a `Encuesta.resumen_para_reporte()` los tres bloques.
3. Le pasa el resumen a `construir_reporte_excel()` / `construir_reporte_pdf()`.
4. Devuelve el archivo con `Content-Disposition: attachment` y el nombre
   `reporte_operativo_AAAA-MM-DD.xlsx` / `.pdf`.

Ninguna de las dos vive en una app `reportes` nueva: no hay ningún modelo propio del
dominio "reportes" —el dato ya vive en `Encuesta`—, así que, siguiendo el criterio que
`CLAUDE.md` fija para decidir entre app nueva y archivo dentro de una app existente
("Modelos de un dominio propio → app nueva"), esto se queda en `fichas`, junto a la
pantalla de la que depende.

---

## 6. El permiso

```python
class ReporteMixin(PermisoRequeridoMixin):
    permisos_requeridos = ("reportes.exportar",)
```

Y no `fichas.ver_todas`, aunque las dos vistas están enlazadas desde la bandeja de
revisión (que sí exige `ver_todas`). La razón es la misma separación de
responsabilidades que `RevisionMixin` ya aplicó entre `ver_todas` y `validar` en la
HU-13: el reporte solo lleva conteos —ningún dato de una familia—, así que puede
gobernarse con su propio permiso, sembrado desde la HU-04 exactamente para esto
(`"Exportar los reportes consolidados"`). Un rol futuro con acceso a reportes pero sin
acceso a la ficha de otra persona —un cargo de solo estadísticas, por ejemplo— es una
combinación que la matriz de la HU-04 ya permite configurar sin tocar código.

Hay una prueba que fija esta distinción explícitamente
(`test_sin_ver_todas_el_supervisor_igual_puede_exportar`): un supervisor sin
`fichas.ver_todas` puede exportar igual, porque el permiso que abre esta puerta es el
otro.

---

## 7. Reutilizar el filtro exacto de la bandeja

```python
def _encuestas_filtradas_para_reporte(get_params):
    consulta = RevisionMixin.encuestas_revisables()
    filtro = FiltroRevisionForm(get_params or None)

    if filtro.is_valid():
        consulta = BandejaRevisionView.aplicar_filtros(consulta, filtro.cleaned_data)
    else:
        consulta = consulta.filter(estado=EstadoEncuesta.COMPLETADA)

    return consulta
```

Para que esto usara **exactamente** el mismo criterio que `BandejaRevisionView`, sin
duplicar la lógica de filtrado, `RevisionMixin.encuestas_revisables()` y
`BandejaRevisionView.aplicar_filtros()` se convirtieron en `@staticmethod` —ninguna de
las dos leía `self` en realidad, solo vivían como métodos de instancia porque nada
antes de esta historia necesitaba llamarlas sin heredar del mixin—. El cambio es
puramente mecánico: las 37 pruebas de la bandeja y de sus filtros (HU-13 y HU-18)
siguen pasando sin ningún cambio, porque `self.aplicar_filtros(...)` sigue
funcionando igual cuando el método es estático.

Con esto, los botones "Exportar Excel" y "Exportar PDF" de la plantilla llevan los
parámetros de la URL actual:

```html
<a href="{% url 'fichas:reporte_excel' %}?{{ parametros }}">Exportar Excel</a>
```

`parametros` ya existía en el contexto desde la HU-13 (la bandeja lo usa para que los
filtros sobrevivan al paginar); exportar reutiliza esa misma variable.

---

## 8. Por qué ReportLab

Se evaluaron tres opciones para el PDF:

- **ReportLab** (elegida): arma el documento con código —párrafos, tablas, estilos—,
  sin ninguna dependencia fuera de `pip install`. El costo es que no reutiliza las
  plantillas HTML existentes: el reporte se construye por separado, con su propio
  layout.
- **WeasyPrint**: convierte HTML/CSS a PDF, lo que habría permitido reusar
  `revision_bandeja.html` casi tal cual. Se descartó porque necesita GTK y Pango
  instalados como librerías nativas del sistema operativo, fuera del entorno virtual
  de Python —un paso extra y distinto en Windows, en Linux y en el servidor de
  producción, en un proyecto que hasta ahora no pide nada fuera de
  `pip install -r requirements.txt`—.
- **xhtml2pdf**: también pura Python y también HTML→PDF, pero con soporte de CSS
  limitado; el diseño Bootstrap actual probablemente no se vería bien sin reescribirlo
  para este propósito.

Para Excel no hubo dilema: `openpyxl` es la librería estándar del ecosistema Python
para `.xlsx`, también pura Python.

---

## 9. Archivos

### Creados

```
backend/fichas/reportes.py                                    funciones puras: arman el .xlsx y el .pdf
backend/docs/HU-19_reportes_pdf_excel.md                       este documento
```

### Modificados

```
backend/requirements.txt
    + openpyxl==3.1.5
    + reportlab==5.0.1

backend/fichas/models.py
    + import Count, Q
    + _porcentaje() (función de módulo)
    Encuesta
    + resumen_para_reporte() (classmethod)

backend/fichas/views.py
    + import HttpResponse
    + import construir_reporte_excel, construir_reporte_pdf
    RevisionMixin.encuestas_revisables()   ahora @staticmethod
    BandejaRevisionView.aplicar_filtros()  ahora @staticmethod
    + _encuestas_filtradas_para_reporte()  función de módulo
    + ReporteMixin
    + ExportarReporteExcelView
    + ExportarReportePDFView

backend/fichas/urls.py
    + revision/reporte.xlsx -> reporte_excel
    + revision/reporte.pdf  -> reporte_pdf

backend/templates/fichas/revision_bandeja.html
    + {% load permisos %}
    + botones «Exportar Excel» / «Exportar PDF», visibles solo con reportes.exportar

backend/fichas/tests.py
    + 26 pruebas, sección rotulada # HU-19 — 76. REPORTES EN PDF Y EXCEL

backend/README.md
    ~ fila de HU-19: de lo que corresponda a «✅ Implementada», con enlace
```

Ninguna migración: no se agregó ningún campo de modelo. `reportes.exportar` ya existía
en la base de datos desde la migración `0005_permisos_iniciales` de la HU-04.

---

## 10. Pruebas

```bash
cd backend
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ResumenParaReporteTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ConstruirReporteExcelTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ConstruirReportePdfTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.ExportarReportesTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.BotonesDeExportarTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test          # 1.371 en total
```

| Clase | Qué comprueba |
|---|---|
| `ResumenParaReporteTest` | el total y los cuatro bloques cuentan bien; la etiqueta de estado es legible y no el código, y trae su porcentaje; el sector agrupa por nombre e incluye su comuna y porcentaje; el censista junta nombre y apellido y desglosa validadas/observadas; `alertas` es exactamente `resumen_alertas_calidad()` sobre el mismo queryset; el método respeta el queryset que recibe (no consulta `Encuesta.objects.all()` por su cuenta); y un queryset vacío no rompe nada |
| `ConstruirReporteExcelTest` | el `.xlsx` generado, leído de vuelta con `openpyxl.load_workbook`, contiene el bloque «Resumen general», las columnas nuevas de cada bloque (comuna, validadas, observadas) y sus datos, y un bloque sin filas escribe el aviso en vez de dejar solo el encabezado |
| `ConstruirReportePdfTest` | el PDF generado empieza con la cabecera `%PDF` (es un PDF válido) y un bloque vacío no lanza una excepción |
| `ExportarReportesTest` | supervisor y administrador descargan ambos formatos con el `Content-Type` y `Content-Disposition` correctos; un censista y un visitante anónimo no pueden; `reportes.exportar` es el permiso que manda —sin `fichas.ver_todas` igual se exporta, sin `reportes.exportar` no—; lo exportado coincide con lo que la bandeja mostraría con el mismo filtro; un rango de fecha invertido no rompe la exportación (cae al valor por defecto, igual que en la bandeja) |
| `BotonesDeExportarTest` | los botones aparecen solo con `reportes.exportar`, y los enlaces llevan los filtros activos de la URL actual |

---

## 11. Verificación manual

Con `manage.py shell` sobre PostgreSQL y los datos de `crear_encuestas_demo`:

```python
from fichas.models import Encuesta
qs = Encuesta.objects.exclude(estado="PENDIENTE")
Encuesta.resumen_para_reporte(qs)
# {'total': 15,
#  'alertas': {'datos_incompletos': 0, 'espera_prolongada': 3, 'visitas_vencidas': 5},
#  'por_estado': [{'etiqueta': 'Anulada', 'total': 1, 'porcentaje': 6.7},
#                 {'etiqueta': 'Borrador', 'total': 5, 'porcentaje': 33.3},
#                 {'etiqueta': 'Completada', 'total': 3, 'porcentaje': 20.0},
#                 {'etiqueta': 'No ubicada', 'total': 1, 'porcentaje': 6.7},
#                 {'etiqueta': 'Observada', 'total': 2, 'porcentaje': 13.3},
#                 {'etiqueta': 'Rechazada', 'total': 1, 'porcentaje': 6.7},
#                 {'etiqueta': 'Validada', 'total': 2, 'porcentaje': 13.3}],
#  'por_sector': [{'sector': 'Los Boldos', 'comuna': 'Concepción', 'total': 15, 'porcentaje': 100.0}],
#  'por_censista': [{'censista': 'Marta Soto', 'total': 15, 'validadas': 2, 'observadas': 2}]}
```

| Paso | Resultado |
|---|---|
| `construir_reporte_excel(resumen)` + `.save()`, reabierto con `openpyxl.load_workbook` | las filas esperadas: título, fecha de generación, «Resumen general» con las 3 alertas, y los tres bloques completos con sus columnas nuevas (comuna, %, validadas, observadas) |
| `construir_reporte_pdf(buffer, resumen)` | archivo de 2.733 bytes, cabecera `%PDF` válida |
| `GET /encuestas/revision/reporte.xlsx?estado=TODAS` vía el cliente de pruebas de Django, como supervisor | 200, `Content-Type` de Excel, contenido coincide con el shell |
| Mismo filtro, como censista | 302 (sin `reportes.exportar`) |

---

## 12. Explicación para la defensa

**En una frase:** esta historia agrega la primera capacidad de exportación del
sistema, y lo hace exportando exactamente lo que la bandeja de revisión ya muestra
—con sus filtros de la HU-18—, en vez de construir una pantalla de reportes separada.

**Lo que conviene poder defender:**

1. **El resumen se calcula una vez y alimenta los dos formatos.**
   `resumen_para_reporte()` no sabe que existe un PDF ni un Excel; `fichas/reportes.py`
   no sabe de dónde vino el resumen. Cada capa tiene una sola responsabilidad, y un
   tercer formato el día de mañana (CSV, por ejemplo) solo necesitaría una función más
   en `reportes.py`.
2. **`reportes.exportar` y no `fichas.ver_todas`.** El reporte no expone datos
   personales —solo conteos—, así que se protege con el permiso que la HU-04 ya había
   anticipado para esto, no con el que abre la ficha de una familia.
3. **Exportar es "descargar lo que estoy viendo".** Reutilizar el filtro exacto de la
   bandeja (`encuestas_revisables()` + `aplicar_filtros()`, convertidos a
   `@staticmethod` para esto) garantiza que un supervisor que filtró por su equipo y su
   semana reciba un reporte de justamente eso, sin tener que repetir el filtro en una
   pantalla nueva.
4. **ReportLab sin dependencias nativas.** Se evaluó y descartó WeasyPrint —más cómodo
   por reusar HTML, pero exige GTK/Pango fuera de `pip`— para no introducir un paso de
   instalación distinto entre el equipo de desarrollo, el del profesor corrector y
   producción.
5. **Cada dato agregado reutiliza un cálculo que ya existía.** La primera versión
   —total y tres bloques con solo nombre y total— se sintió pobre al probarla; lo que se
   agregó después (alertas de calidad, porcentajes, comuna, validadas/observadas) no es
   lógica nueva: son `resumen_alertas_calidad()` (HU-16), la comuna que el sector ya
   tiene desde la HU-05, y el mismo `Count(filter=Q(...))` que el panel del supervisor
   usa desde la HU-13. "Se ve pobre" se resolvió sacándole más partido a lo que el
   sistema ya calculaba, no inventando funcionalidad.

---

## 13. Posibles preguntas del profesor

**¿Por qué el reporte no incluye los datos de las familias (direcciones, nombres),
si la bandeja de revisión sí los muestra en pantalla?**
Porque se decidió deliberadamente que "compartir resultados del operativo" es
compartir agregados —cuántas fichas por estado, por sector, por censista—, no un
volcado de información personal. Es una decisión de alcance tomada antes de programar,
no una limitación técnica: `Encuesta.resumen_para_reporte()` recibe el queryset
completo y podría iterarlo fila por fila si una historia futura lo pidiera.

**¿Por qué ReportLab y no generar el PDF a partir de las plantillas HTML que ya
existen?**
Porque la alternativa que sí reutiliza HTML, WeasyPrint, necesita GTK y Pango
instalados como librerías del sistema operativo, no como paquetes de `pip`. Eso
introduce un paso de instalación distinto en cada entorno —desarrollo, corrección,
producción—, algo que este proyecto ha evitado deliberadamente hasta ahora
(`requirements.txt` es autosuficiente). ReportLab construye el documento con código en
vez de HTML, pero no depende de nada fuera del entorno virtual.

**¿Por qué la exportación exige `reportes.exportar` y no `fichas.ver_todas`, si solo
se llega a estos botones desde una pantalla que sí exige `ver_todas`?**
Porque son preguntas distintas: `ver_todas` pregunta "¿puede ver la ficha de otra
persona?", y el reporte no muestra ninguna ficha, solo conteos. Separar los permisos
dejó abierta una combinación que la matriz de la HU-04 ya permite configurar sin tocar
código: un rol que solo necesita cifras agregadas, sin acceso a los datos de una
familia en particular.

**¿Por qué `encuestas_revisables()` y `aplicar_filtros()` pasaron a ser
`@staticmethod`?**
Porque ninguna de las dos leía `self` en la práctica —no dependían de la petición ni
de ningún estado de la instancia—; solo eran métodos de instancia porque, hasta esta
historia, nada necesitaba llamarlas sin heredar de `RevisionMixin` o de
`BandejaRevisionView`. Convertirlas en estáticas permite que las vistas de exportación
—que exigen un permiso distinto y no heredan de esos mixins— reutilicen el mismo
código exacto en vez de reimplementar el filtro.

**¿Se agregó algún campo o migración nueva?**
No. El dato ya vivía en `Encuesta`; esta historia solo agrega la capacidad de
agregarlo y exportarlo. El permiso `reportes.exportar` que la protege existe desde la
migración de la HU-04.
