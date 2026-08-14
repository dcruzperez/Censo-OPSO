# HU-16 · Alertas de registros incompletos

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor, quiero recibir alertas de registros incompletos para mejorar la calidad de los datos.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **19 pruebas automáticas** propias (**1.338** en total en el proyecto → `python manage.py test` → OK)

> La HU-15 ya había reservado este número y advertido, en dos sitios de su propio
> código, que el catálogo de alertas era «una historia aparte». Esta historia no
> inventa ninguna señal nueva: **cuenta** tres que el sistema ya calculaba fila por
> fila desde la HU-10 y la HU-13, y las pone donde el supervisor entra primero.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Las tres señales, y de dónde viene cada una](#2-las-tres-señales)
3. [`tiene_datos_incompletos`: una propiedad que no mira el estado](#3-tiene_datos_incompletos)
4. [`resumen_alertas_calidad()`: por qué vive en el modelo](#4-resumen_alertas_calidad)
5. [Por qué dos cuentas van por SQL y una por Python](#5-sql-y-python)
6. [Dónde se ve, y dónde se decidió que no](#6-dónde-se-ve)
7. [Archivos creados y modificados](#7-archivos-creados-y-modificados)
8. [Pruebas](#8-pruebas)
9. [Verificación manual](#9-verificación-manual)
10. [Explicación para la defensa](#10-explicación-para-la-defensa)
11. [Posibles preguntas del profesor](#11-posibles-preguntas-del-profesor)

---

## 1. Explicación inicial

Desde la HU-13, la bandeja de revisión pinta en cada fila cuatro señales —personas
registradas contra declaradas, si la vivienda está descrita, si tiene ubicación y
cuántas fotos tiene— para que el supervisor "sospeche antes de entrar". Y desde la
HU-10, una encuesta en borrador puede llevar una fecha de "próxima visita" que el
propio censista anotó.

Las dos cosas ya existían, pero solo **fila por fila**: había que abrir la bandeja y
mirar encuesta por encuesta para notar que algo faltaba. No había ningún número que
dijera, de un vistazo, "hoy hay 6 fichas con problemas de calidad" — y el panel del
supervisor, que es lo primero que ve al entrar, no mencionaba la calidad de los datos
en absoluto: solo contaba **estados** (recibidas, validadas, observadas).

Esta historia agrega esa vista agregada. No agrega ningún campo a la base de datos, ni
un estado nuevo, ni un permiso nuevo.

---

## 2. Las tres señales

| Alerta | De dónde viene | Qué significa |
|---|---|---|
| **Fichas enviadas con datos incompletos** | `resumen_para_revision()` (HU-13) | El censista marcó la encuesta como `COMPLETADA` pero le falta algo que el sistema sabe contar: hogar sin registrar, menos personas que las declaradas, vivienda sin describir, o sin ubicación GPS. |
| **Esperando revisión hace demasiado** | `espera_prolongada` (HU-13) | `COMPLETADA` con `cerrada_en` a más de `DIAS_ESPERA_PROLONGADA` (7 días). Ya existía como resaltado por fila en la cola del panel; aquí se **cuenta**. |
| **Visitas vencidas** | `visita_pendiente_vencida` (HU-10) | El propio censista anotó "vuelvo el jueves" (`proxima_visita`) y esa fecha ya pasó, y la encuesta sigue siendo trabajo suyo (`ESTADOS_ABIERTOS`). Antes solo se lo veía el propio censista en su lista; el supervisor no tenía forma de saberlo. |

Las tres comparten algo: **ninguna es una opinión del sistema sobre si el trabajo está
bien hecho.** Son hechos contables —cuenta esto, compara con aquello, compara una fecha
con hoy— igual que ya lo eran cuando alimentaban `problemas_detectados()` en la HU-15.
Esta historia no cambia lo que significan; cambia que ahora se **cuentan** y se
**muestran agregadas**.

---

## 3. `tiene_datos_incompletos`

```python
@property
def tiene_datos_incompletos(self):
    datos = self.resumen_para_revision()
    return (
        not datos["tiene_hogar"]
        or datos["personas"] < datos["declaradas"]
        or not datos["vivienda_descrita"]
        or not datos["tiene_ubicacion"]
    )
```

Es la primera señal de la tabla anterior, convertida en un booleano. **No mira el
estado a propósito**: una vivienda sin describir es igual de real esté la encuesta en
borrador o ya enviada. Hay una prueba que lo comprueba directamente
(`test_no_depende_del_estado`), construyendo una encuesta en `BORRADOR` sin hogar y
verificando que la propiedad da `True` igual.

La decisión de **a qué estados les importa esta alerta** no vive aquí: vive en quien
llama. Una encuesta en borrador se supone incompleta todavía —es lo que "borrador"
significa— así que contarla como alerta produciría ruido constante. Solo importa
cuando alguien ya la dio por terminada y sigue faltando algo, y esa decisión de
alcance la toma `resumen_alertas_calidad()`, no la propiedad.

---

## 4. `resumen_alertas_calidad()`

```python
@classmethod
def resumen_alertas_calidad(cls, queryset=None):
    base = cls.objects.all() if queryset is None else queryset
    completadas = base.filter(estado=EstadoEncuesta.COMPLETADA)...
    return {
        "datos_incompletos": ...,
        "espera_prolongada": ...,
        "visitas_vencidas": ...,
    }
```

Vive en el modelo (`fichas/models.py`) y no en `dashboards/views.py`, que es su único
consumidor hoy. La razón es la misma que ya aplicó `zonas_disponibles()` en la HU-08:
**no es un cálculo de una sola pantalla.** El panel del supervisor es quien lo pidió
primero, pero un reporte futuro, o un filtro nuevo en la propia bandeja de revisión,
necesitarían exactamente el mismo número. Si cada consumidor lo recalculara a su
manera, bastaría con que uno se quedara atrás para que dos pantallas mostraran cifras
distintas del mismo hecho.

Acepta un `queryset` opcional para que quien llama pueda acotar el universo —por
ejemplo, a los operativos vigentes, que es justo lo que hace `DashboardSupervisorView`
al pasarle `revisables`, el mismo queryset que ya usaba para `resumen_revision`—, sin
que el método tenga que saber nada sobre operativos ni vigencia.

---

## 5. Por qué dos cuentas van por SQL y una por Python

Las tres alertas no se calculan del mismo modo, y es una decisión deliberada:

**`espera_prolongada` y `visitas_vencidas` son un `.count()` con un filtro de
fecha.** `cerrada_en <= (ahora - 7 días)` y `proxima_visita <= hoy` son comparaciones
que la base de datos resuelve en una sola consulta, sin traer ninguna fila a Python.

**`datos_incompletos` no puede serlo**, porque depende de comparar cuántos
`Integrante` hay registrados contra `integrantes_declarados`, un campo en
`GrupoFamiliar`. Eso es una relación uno-a-muchos que habría que expresar como una
subconsulta con `annotate(Count(...))` combinada con las otras tres condiciones por
`OR` — posible, pero bastante menos legible que lo que ya existía, para una operación
que en este proyecto se hace sobre un puñado de fichas (las `COMPLETADA` de un
operativo, no el histórico completo).

Por eso `resumen_alertas_calidad()` **primero filtra por `COMPLETADA` en la base de
datos** —así el universo que llega a Python es, en la práctica, del mismo tamaño que
la bandeja de revisión, no todo el historial del sistema— y **después** cuenta con
`tiene_datos_incompletos` fila por fila. Es exactamente lo que la bandeja ya hacía
desde la HU-13 para pintar sus badges; aquí solo se suma en vez de mostrarse una por
una.

---

## 6. Dónde se ve, y dónde se decidió que no

Se agregó una tarjeta nueva en `dashboards/supervisor.html`, "Alertas de calidad de
datos", con los tres números y un enlace a la bandeja. Se descartaron dos alternativas
que se evaluaron antes de programar nada:

- **Un filtro nuevo en `FiltroRevisionForm`** ("Con datos incompletos"), que habría
  reusado `/encuestas/revision/` en vez de tocar el panel. Se descartó porque el
  objetivo de la historia es que el supervisor **reciba** la alerta al entrar, no que
  tenga que ir a buscarla activando un filtro.
- **Notificaciones** (correo, push). Este proyecto no tiene esa infraestructura —"Sin
  API REST ni JavaScript de aplicación" es una decisión de arquitectura ya tomada— y
  agregarla para esto habría sido una historia de infraestructura completa disfrazada
  de una de datos.

El enlace "Ir a la bandeja" lleva a `/encuestas/revision/` **sin filtrar**, por lo
mismo que el enlace de la tarjeta de "Encuestas por revisar" ya hace: no se construyó
ningún parámetro de query nuevo para esto.

---

## 7. Archivos creados y modificados

### Creados

```
backend/docs/HU-16_alertas_de_registros_incompletos.md    este documento
```

### Modificados

```
backend/fichas/models.py
    + import timedelta
    + Encuesta.tiene_datos_incompletos (property)
    + Encuesta.resumen_alertas_calidad() (classmethod)

backend/dashboards/views.py
    DashboardSupervisorView.get_context_data()
    + contexto["alertas_calidad"] = Encuesta.resumen_alertas_calidad(revisables)
    + contexto["dias_espera_prolongada"] = Encuesta.DIAS_ESPERA_PROLONGADA

backend/templates/dashboards/supervisor.html
    + tarjeta "Alertas de calidad de datos"

backend/fichas/tests.py
    + 19 pruebas, sección rotulada # HU-16 — 74. ALERTAS DE CALIDAD DE DATOS

backend/README.md
    ~ fila de HU-16: de "⏳ Pendiente" a "✅ Implementada", con enlace
```

Ninguna migración: no se agregó ni se modificó ningún campo de modelo.

---

## 8. Pruebas

```bash
cd backend
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas   # 792 (HU-07 a HU-16)
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test          # 1.338 en total
```

| Clase | Qué comprueba |
|---|---|
| `DatosIncompletosTest` | las cuatro condiciones por separado, que todo completo da `False`, y que la propiedad **no** mira el estado |
| `ResumenAlertasCalidadTest` | cuenta solo entre `COMPLETADA`, respeta el mismo umbral que `espera_prolongada`, una visita futura o sin fecha no cuenta, una encuesta ya resuelta con `proxima_visita` vencida tampoco cuenta, y el `queryset` que se le pasa se respeta |
| `AlertasEnElPanelTest` | el panel muestra los tres números, el mensaje de "sin alertas" cuando corresponde, y que el umbral de 7 días viene del modelo y no está escrito a mano en la plantilla |

---

## 9. Verificación manual

Con `runserver` sobre PostgreSQL y los datos de `crear_encuestas_demo`:

| Paso | Resultado |
|---|---|
| `Encuesta.resumen_alertas_calidad()` en el shell | `{'datos_incompletos': 0, 'espera_prolongada': 3, 'visitas_vencidas': 2}` |
| Las 3 `COMPLETADA` del operativo demo | las tres con `tiene_datos_incompletos = False` (los datos de demostración están completos) |
| `GET /dashboard/supervisor/` como supervisor | **200**, tarjeta "Alertas de calidad de datos" con `0`, `3` y `2`, coincidiendo exacto con el cálculo del shell |
| Colores de la tarjeta | verde en `datos_incompletos` (0), ámbar en las otras dos (>0) |

---

## 10. Explicación para la defensa

**En una frase:** esta historia no descubre ningún dato nuevo; junta tres señales que
ya existían sueltas —dos desde la HU-13, una desde la HU-10— y las pone donde el
supervisor las necesita ver sin tener que ir a buscarlas.

**Lo que conviene poder defender:**

1. **Cero lógica de negocio nueva.** Las tres alertas se definen exactamente igual
   que ya las definían `resumen_para_revision()`, `espera_prolongada` y
   `visita_pendiente_vencida`. Lo único nuevo es contarlas y agregarlas.
2. **La cuenta vive en el modelo, no en la vista.** `resumen_alertas_calidad()`
   acepta un queryset porque no se sabe todavía quién más lo va a necesitar —y ya
   hay un candidato natural, un filtro futuro en la bandeja de revisión— y esa
   decisión de diseño evita que el día de mañana existan dos criterios distintos de
   "qué es una ficha incompleta" en dos archivos distintos.
3. **Sin infraestructura nueva.** No hay notificaciones, ni JavaScript, ni una API:
   es una tarjeta más en una pantalla que Django ya renderizaba, coherente con que
   este proyecto es "vistas renderizadas en servidor con plantillas" de punta a
   punta.

---

## 11. Posibles preguntas del profesor

**¿Por qué "datos incompletos" solo cuenta las `COMPLETADA` y no todas las
encuestas?**
Porque una encuesta en borrador se supone incompleta todavía —es lo que significa
estar en borrador—. Contarla como alerta generaría ruido constante y le restaría
atención a lo que sí importa: una ficha que el censista **dio por terminada** y sigue
sin cumplir lo mínimo.

**¿Por qué el umbral de "espera prolongada" es el mismo que ya existía en la HU-13 y
no uno nuevo para esta historia?**
Porque es la misma pregunta —"¿cuánto es demasiado esperando revisión?"— con la misma
respuesta. Definir un segundo umbral distinto para el mismo concepto habría creado dos
números que responden lo mismo con valores distintos, sin ninguna razón de negocio
para que difieran.

**¿Por qué "datos incompletos" se calcula fila por fila en Python y las otras dos con
un `.count()` en la base de datos?**
Porque comparar cuántos integrantes hay registrados contra cuántos se declararon
requiere una relación uno-a-muchos que un único `COUNT` con filtro no expresa con
claridad. Se filtra primero por `COMPLETADA` en SQL —así el universo que llega a
Python es chico— y se cuenta en Python después, con el mismo método que la bandeja de
revisión ya usaba para pintar sus badges desde la HU-13.

**¿Por qué no se agregó un filtro "con datos incompletos" a la bandeja de
revisión, ya que casi todo el cálculo ya existe?**
Porque el objetivo de la historia es que el supervisor **reciba** la alerta al
entrar al sistema, no que tenga que ir a activarla. Se evaluó y se descartó a
propósito, dejando la puerta abierta —`resumen_alertas_calidad()` vive en el modelo
justamente para que agregarlo después no obligue a reimplementar el criterio.

**¿Por qué no se envía la alerta por correo o como notificación?**
Porque el proyecto no tiene esa infraestructura y agregarla sería una historia de
arquitectura completa, no una de datos. OPSO son "vistas renderizadas en servidor con
plantillas" de punta a punta, sin API REST ni JavaScript de aplicación; una tarjeta en
el panel que ya se visita al iniciar sesión es coherente con eso.

**¿Se agregó algún campo o migración nueva?**
No. Las tres señales ya se podían calcular con los campos que existían desde la
HU-07, la HU-08 y la HU-10. Esta historia es puramente de lectura y agregación.
