# HU-18 · Filtrar por fecha, sector, estado y censista

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor o administrador, quiero filtrar la información por fecha, sector, estado y censista para facilitar el análisis.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **7 pruebas automáticas** propias (**1.345** en total en el proyecto → `python manage.py test` → OK)

> Tres de los cuatro filtros que pide esta historia ya existían: `FiltroRevisionForm`
> los ofrece desde la HU-13. Esta historia agrega el único que faltaba —**fecha**— al
> mismo formulario, en vez de construir una pantalla nueva.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Lo que ya existía, y lo único que faltaba](#2-lo-que-ya-existía)
3. [El campo nuevo: rango sobre `cerrada_en`](#3-el-campo-nuevo)
4. [Validación del rango invertido](#4-validación-del-rango-invertido)
5. [Por qué `cerrada_en` y no `creada_en`](#5-por-qué-cerrada_en)
6. [El administrador ya podía entrar: no fue necesario nada nuevo](#6-el-administrador)
7. [Archivos modificados](#7-archivos-modificados)
8. [Pruebas](#8-pruebas)
9. [Verificación manual](#9-verificación-manual)
10. [Explicación para la defensa](#10-explicación-para-la-defensa)
11. [Posibles preguntas del profesor](#11-posibles-preguntas-del-profesor)

---

## 1. Explicación inicial

La bandeja de revisión (`/encuestas/revision/`, HU-13) es la pantalla donde un
supervisor o administrador mira el trabajo de todo el operativo, y desde esa misma
historia ya lleva un formulario de filtros: texto libre, estado, operativo, sector y
censista. Antes de escribir una sola línea se revisó ese formulario a fondo —es el
paso que esta historia repite en cada HU nueva— y resultó que **tres de los cuatro
filtros que pide el enunciado ya estaban resueltos**. Lo único ausente era acotar por
fecha.

Por eso esta historia no crea una pantalla de "análisis" nueva ni un formulario
paralelo: agrega dos campos (`fecha_desde`, `fecha_hasta`) al `FiltroRevisionForm` que
ya existía, y una validación de rango. Es la misma decisión que ya tomó la HU-16 al
reutilizar `resumen_para_revision()` en vez de recalcular sus señales desde cero.

---

## 2. Lo que ya existía

| Filtro que pide la historia | Ya existía desde | Cómo |
|---|---|---|
| **Estado** | HU-13 | `FiltroRevisionForm.estado`, con agrupaciones ("Esperando revisión", "Ya revisadas", "Todas") además de cada estado suelto |
| **Sector** | HU-13 | `FiltroRevisionForm.sector`, acotado a los sectores que tienen encuestas revisables |
| **Censista** | HU-13 | `FiltroRevisionForm.censista`, acotado a quienes tienen encuestas revisables |
| **Fecha** | — | **Esta historia** |

De regalo, el formulario también filtra por `operativo` y por texto libre (dirección o
jefe de hogar), que no pedía el enunciado pero ya estaban ahí.

**El administrador ya podía usar todo esto.** `BandejaRevisionView` exige el permiso
`fichas.ver_todas`, y `Usuario.tiene_permiso()` devuelve `True` para cualquier
administrador sin consultar la tabla de permisos (`usuarios/models.py`, la misma regla
que ya documentó la HU-07). La bandeja, con sus cinco filtros, ya era accesible para
"supervisor o administrador" —el sujeto exacto de esta historia— antes de escribir
nada. Hay una prueba de la HU-13 que ya lo comprobaba
(`BandejaRevisionTest.test_el_administrador_entra`); esta historia no repite esa
prueba, solo se apoya en que ya existe.

---

## 3. El campo nuevo

```python
fecha_desde = forms.DateField(
    label="Desde",
    required=False,
    widget=forms.DateInput(attrs={"class": CLASE_TEXTO, "type": "date"}, format="%Y-%m-%d"),
)
fecha_hasta = forms.DateField(
    label="Hasta",
    required=False,
    widget=forms.DateInput(attrs={"class": CLASE_TEXTO, "type": "date"}, format="%Y-%m-%d"),
)
```

Dos campos y no uno solo llamado "fecha", porque un supervisor mirando el avance de la
semana necesita acotar un **rango** ("todo lo recibido desde el lunes"), no un día
exacto. El widget `type="date"` es el mismo patrón que ya usan `OperativoForm`
(`fecha_inicio`/`fecha_termino`) e `IntegranteForm` (`fecha_nacimiento`): deja que el
navegador muestre su propio selector en vez de pedir el formato a mano.

En `BandejaRevisionView.aplicar_filtros()`:

```python
if fecha_desde := datos.get("fecha_desde"):
    consulta = consulta.filter(cerrada_en__date__gte=fecha_desde)

if fecha_hasta := datos.get("fecha_hasta"):
    consulta = consulta.filter(cerrada_en__date__lte=fecha_hasta)
```

Ambos son opcionales e independientes: se puede usar solo "desde", solo "hasta", o los
dos juntos. Una encuesta sin `cerrada_en` —una en `BORRADOR`, por ejemplo, que sigue
siendo "revisable" en el sentido de `RevisionMixin.encuestas_revisables()`— no entra en
ningún rango, porque en SQL una comparación contra `NULL` nunca es verdadera. Hay una
prueba que lo comprueba directamente
(`test_una_encuesta_sin_cerrar_no_entra_en_ningun_rango`).

---

## 4. Validación del rango invertido

```python
def clean(self):
    limpios = super().clean()
    desde = limpios.get("fecha_desde")
    hasta = limpios.get("fecha_hasta")

    if desde and hasta and desde > hasta:
        self.add_error(
            "fecha_hasta", "La fecha «hasta» no puede ser anterior a «desde»."
        )

    return limpios
```

Un rango invertido —"hasta" antes que "desde"— no tiene una lectura razonable, así que
se avisa en el campo `fecha_hasta` en vez de adivinar cuál de las dos fechas se
equivocó. Con eso, el formulario completo queda inválido, y `BandejaRevisionView`
sigue exactamente el mismo camino que ya tomaba desde la HU-13 cuando llega un `estado`
inventado por la URL: cae al valor por defecto (`COMPLETADA`, "esperando revisión") en
vez de romper la pantalla con un 500. No fue necesario escribir ningún manejo de error
nuevo; el `is_valid()` que ya protegía `get_queryset()` protege también este caso.

---

## 5. Por qué `cerrada_en`

`Encuesta` tiene varias fechas: `creada_en` (cuándo se abrió la ficha, `auto_now_add`),
`iniciada_en` (primera visita) y `cerrada_en` (cuándo dejó de ser trabajo abierto). El
filtro usa `cerrada_en` por la misma razón que ya la usa el orden de la cola
(`order_by(F("cerrada_en").asc(nulls_last=True))`, HU-13) y el cálculo de
`dias_esperando()`: es la fecha que responde "¿cuándo llegó esto a mi bandeja?", que es
la pregunta que un supervisor filtrando por fecha está haciendo. `creada_en` respondería
una pregunta distinta —cuándo se le asignó el trabajo al censista, no cuándo lo
entregó— y mezclarla habría hecho que "encuestas de esta semana" incluyera fichas
creadas hace un mes y recién cerradas hoy, o excluyera una cerrada hoy pero creada la
semana pasada.

La comparación usa `__date`, que en Django convierte el `DateTimeField` a la zona
horaria local (`TIME_ZONE`) antes de comparar. Es el mismo criterio que ya aplica
`Encuesta.dias_esperando()` con `timezone.localtime(self.cerrada_en).date()`: sin eso,
una encuesta cerrada a las 23:50 hora de Chile podría contarse en el día siguiente por
estar en UTC.

---

## 6. El administrador

Esta historia no agregó ningún permiso, mixin ni vista nueva para que el administrador
pueda filtrar. `RevisionMixin` (HU-13) ya exige `fichas.ver_todas`, y
`PermisoRequeridoMixin` (`usuarios/mixins.py`) ya deja pasar a cualquier administrador
antes de consultar el permiso, con `permitir_administrador = True` por defecto —la
misma regla documentada desde la HU-04. Agregar el rango de fecha al formulario
compartido significa que el administrador lo recibe automáticamente, sin ningún cambio
adicional.

---

## 7. Archivos modificados

```
backend/fichas/forms.py
    FiltroRevisionForm
    + fecha_desde, fecha_hasta (DateField)
    + clean() — valida que el rango no esté invertido

backend/fichas/views.py
    BandejaRevisionView.aplicar_filtros()
    + filtro por cerrada_en__date__gte / __lte

backend/templates/fichas/revision_bandeja.html
    + dos campos de fecha en el formulario de filtros
    + mensaje de error del rango invertido

backend/fichas/tests.py
    + 7 pruebas, sección rotulada # HU-18 — 75. FILTRAR POR FECHA

backend/docs/HU-18_filtrar_por_fecha_sector_estado_censista.md    este documento

backend/README.md
    ~ fila de HU-18: de lo que corresponda a "✅ Implementada", con enlace
```

Ninguna migración: `cerrada_en` ya existía desde la HU-13, y no se agregó ningún campo
de modelo.

---

## 8. Pruebas

```bash
cd backend
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas.tests.FiltroPorFechaTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test          # 1.345 en total
```

| Prueba | Qué comprueba |
|---|---|
| `test_desde_excluye_lo_anterior` | `fecha_desde` deja fuera lo cerrado antes de esa fecha |
| `test_hasta_excluye_lo_posterior` | `fecha_hasta` deja fuera lo cerrado después de esa fecha |
| `test_el_rango_combina_ambos_extremos` | usados juntos, solo queda lo que cae dentro del rango |
| `test_convive_con_el_filtro_de_censista` | el rango de fecha se combina con `censista` sin pisarlo, igual que ya hacían sector, operativo y estado entre sí desde la HU-13 |
| `test_un_rango_invertido_no_rompe_la_pantalla` | "hasta" antes que "desde" responde 200, no 500 |
| `test_un_rango_invertido_avisa_en_el_campo_y_no_filtra_nada` | se muestra el mensaje de error y la bandeja cae al valor por defecto, sin aplicar ningún filtro de la URL |
| `test_una_encuesta_sin_cerrar_no_entra_en_ningun_rango` | una encuesta sin `cerrada_en` (por ejemplo, en `BORRADOR`) no aparece al filtrar por fecha |

No se repitieron las pruebas de estado, sector ni censista: ya existen en
`FiltrosRevisionTest` (HU-13) y siguen pasando sin cambios, que es la prueba de que
agregar el rango de fecha no rompió lo que ya filtraba.

---

## 9. Verificación manual

Con `runserver` sobre PostgreSQL y los datos de `crear_encuestas_demo`:

| Paso | Resultado |
|---|---|
| `GET /encuestas/revision/?estado=TODAS&fecha_desde=2026-08-01` como supervisor | **200**, solo las encuestas cerradas desde esa fecha |
| Mismo filtro, como `admin@opso.cl` | **200**, mismo resultado — sin ningún cambio para que funcionara |
| `fecha_desde` posterior a `fecha_hasta` | **200**, con el aviso "La fecha «hasta» no puede ser anterior a «desde»" y la bandeja mostrando lo que espera revisión por defecto |
| Combinar `fecha_desde` con `sector` y `censista` a la vez | el resultado es la intersección de los tres, coherente con `aplicar_filtros()` aplicándolos en cadena |
| "Quitar los filtros" con un rango de fecha activo | vuelve a `/encuestas/revision/` sin ningún parámetro, igual que ya hacía con los demás filtros |

---

## 10. Explicación para la defensa

**En una frase:** de los cuatro filtros que pide la historia, tres ya existían desde
la HU-13; esta historia identificó el hueco real —fecha— y lo agregó al mismo
formulario en vez de construir algo nuevo.

**Lo que conviene poder defender:**

1. **Investigar antes de programar evitó reescribir código que ya funcionaba.** El
   patrón de este proyecto —revisar qué existe antes de cada HU— es el que llevó a
   notar que estado, sector y censista ya estaban resueltos, y que "supervisor o
   administrador" ya tenía acceso sin ningún cambio.
2. **El rango vive en el mismo formulario, no en uno paralelo.** Un formulario nuevo
   habría duplicado los otros cuatro campos —y su lógica de qué desplegables
   mostrar— solo para agregar dos.
3. **`cerrada_en` y no `creada_en`.** Es la fecha que ya usa el orden de la cola y el
   cálculo de días esperando; usar otra habría introducido dos nociones distintas de
   "fecha de la encuesta" en la misma pantalla.
4. **Un rango invertido no rompe nada.** Se reutiliza el mismo mecanismo que ya
   protegía contra un `estado` inventado por URL desde la HU-13: formulario inválido
   → valor por defecto, no una excepción.

---

## 11. Posibles preguntas del profesor

**¿Por qué esta historia no tiene una pantalla propia, si el enunciado habla de
"facilitar el análisis"?**
Porque la pantalla que ese análisis necesita ya existía: la bandeja de revisión de la
HU-13 es, literalmente, la lista de encuestas con filtros que un supervisor usa para
analizar el estado del operativo. Construir una segunda pantalla con los mismos datos
habría sido duplicar, no facilitar.

**¿Por qué el rango es sobre `cerrada_en` y no sobre `creada_en` o `actualizada_en`?**
Porque `cerrada_en` es la fecha que responde la pregunta que alguien filtrando por
fecha está haciendo —"¿cuándo llegó esto a revisión?"—, y es la misma fecha que ya
ordena la cola y calcula los días de espera desde la HU-13. Usar `creada_en` mezclaría
"cuándo se le asignó el trabajo al censista" con "cuándo lo entregó", que son hechos
distintos.

**¿Qué pasa con una encuesta que nunca se cerró (`cerrada_en` es `NULL`) si filtro por
fecha?**
Queda fuera de cualquier rango, porque SQL nunca considera verdadera una comparación
contra `NULL`. Es el comportamiento correcto: no se puede decir que una encuesta sin
fecha de cierre "está dentro" o "fuera" de un rango de fechas de cierre.

**¿Por qué el administrador no necesitó ningún cambio para poder filtrar?**
Porque `PermisoRequeridoMixin` ya deja pasar a cualquier administrador antes de
consultar el permiso —`permitir_administrador = True` por defecto, la regla que fija la
HU-04—, y la bandeja de revisión exige un único permiso (`fichas.ver_todas`) que esa
regla ya cubre. Fue una comprobación, no un desarrollo.

**¿Se agregó algún campo o migración nueva?**
No. `cerrada_en` existe desde la HU-13; esta historia solo agrega un filtro sobre un
campo que ya estaba en la base de datos.
