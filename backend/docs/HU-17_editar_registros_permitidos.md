# HU-17 · Editar registros permitidos

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como supervisor o administrador, quiero editar registros permitidos para corregir errores detectados.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** **satisfecha sin código nuevo** — reutiliza el flujo de devolución de la HU-15

> Esta historia no agrega ni una línea a `fichas/`. Se resuelve dejando constancia de
> que el sistema **ya** tiene un camino para corregir errores detectados, y de por qué
> ese camino —y no una edición directa— es la decisión correcta dado el resto del
> diseño. Este documento es esa constancia.

---

## Índice

1. [Por qué esta historia no tiene implementación propia](#1-por-qué-esta-historia-no-tiene-implementación-propia)
2. [La restricción que ya existe, y en qué lugares está escrita](#2-la-restricción-que-ya-existe)
3. [El camino que sí está construido](#3-el-camino-que-sí-está-construido)
4. [La alternativa descartada](#4-la-alternativa-descartada)
5. [Qué pasaría si se implementara de todos modos](#5-qué-pasaría-si-se-implementara-de-todos-modos)
6. [Cobertura de pruebas](#6-cobertura-de-pruebas)
7. [Explicación para la defensa](#7-explicación-para-la-defensa)
8. [Posibles preguntas del profesor](#8-posibles-preguntas-del-profesor)

---

## 1. Por qué esta historia no tiene implementación propia

Leída literalmente, la historia pide que un supervisor o un administrador puedan
**editar directamente** vivienda, hogar o integrantes de una encuesta ajena. Antes de
construir esa pantalla se revisó qué existía en `fichas/`, y resultó que:

- El sistema **ya distingue** entre "detectar un error" (tarea de quien revisa) y
  "corregirlo" (tarea de quien levantó el dato), y ese reparto está resuelto desde la
  HU-15 con `DevolverEncuestaView`.
- Construir además una edición directa para supervisor/administrador **no sería una
  ampliación neutra**: contradice, en el código y en su propia documentación, la
  separación de funciones que las HU-03, HU-08 y HU-09 dejaron escrita a propósito.

Por eso esta historia se cierra como una decisión de diseño documentada, no como una
funcionalidad nueva.

---

## 2. La restricción que ya existe

Dos lugares del código lo dicen explícitamente, no es una inferencia de esta historia:

**`zonas_disponibles()`** (`fichas/forms.py:63`), la función que decide qué territorio
puede tocar cada persona:

> «Un administrador o un supervisor no tienen asignaciones y por tanto no obtienen
> ninguna zona. Es correcto: quien levanta información en terreno es el encuestador, y
> la separación de funciones que la HU-03 estableció —quien valida no es quien
> levanta— se rompería si el supervisor pudiera registrar fichas. Para casos
> excepcionales está el admin, que es el camino técnico y deja rastro en su propio
> log.»

**`HogarDeLaEncuestaMixin`** (`fichas/views.py:838`), base de las cuatro pantallas de
integrantes:

> «Ni siquiera `fichas.ver_todas` abre esta puerta: escribir una persona en la ficha de
> otro encuestador dejaría el dato atribuido a quien no estuvo en la vivienda.»

Esto se aplica en dos capas, y las dos tendrían que romperse para que la historia, leída
literalmente, funcionara:

| Capa | Qué impide la edición ajena |
|---|---|
| **Permisos** (HU-04) | `fichas.crear` y `fichas.editar` los siembra `usuarios/migrations/0005_permisos_iniciales.py:128` solo para el rol Censista. Supervisor no los trae por defecto. |
| **Consulta** (`fichas/views.py`) | Aunque se concediera el permiso desde la matriz de HU-04, `EditarViviendaView.vivienda` filtra por `zonas_disponibles(request.user)` y `HogarDeLaEncuestaMixin.encuesta` / `EncuestaPropiaMixin.encuesta` filtran por `censista=request.user`. Un supervisor o administrador no tiene sectores asignados ni encuestas propias: la consulta devuelve vacío y la vista responde 404. |

---

## 3. El camino que sí está construido

**`DevolverEncuestaView`** (`fichas/views.py:2312`, ruta `/encuestas/<pk>/devolver/`,
HU-15) es el mecanismo real para "corregir errores detectados":

```
El supervisor revisa   ──►  detecta un error  ──►  devuelve con observaciones
(fichas.validar)             (problemas_detectados()   (OBSERVADA, reabre la ficha)
                               las prerrellena)
                                                              │
                                                              ▼
                                          El censista LEE el motivo, corrige
                                          su propio registro y reenvía
                                          (misma pantalla que usó para levantarla)
```

Esto cumple el objetivo de negocio de la historia —"corregir errores detectados"— sin
que nadie escriba en el registro de otra persona. El error se corrige; solo cambia
quién pulsa la tecla, y eso es exactamente lo que la separación de funciones exige.

---

## 4. La alternativa descartada

Se consideró construir una edición directa para supervisor/administrador sobre
vivienda, hogar e integrantes, con estas piezas:

- Un permiso nuevo o una excepción a `zonas_disponibles()` para que el supervisor
  alcance viviendas fuera de su territorio (que es ninguno).
- Un campo para distinguir **quién levantó el dato** (`censista`, la atribución
  original) de **quién lo corrigió** (una persona distinta, en otro momento), porque
  sobrescribir `censista` falsificaría quién estuvo en la vivienda.
- Una bitácora propia para esas ediciones, del mismo espíritu que `RegistroAuditoria`
  (HU-03) pero para datos censales en vez de cuentas de usuario.

Se descartó porque:

1. **Contradice una decisión ya tomada y documentada**, no una ausencia de decisión. No
   es un permiso que "faltó activar": es una restricción que el propio código explica
   y defiende en dos archivos distintos.
2. **El objetivo de negocio ya está cumplido** por HU-15. Construir un segundo camino
   para el mismo fin duplicaría lógica y abriría dos formas distintas de llegar al
   mismo resultado, con reglas de integridad distintas cada una.
3. **La única puerta de excepción que el propio código reconoce es `/admin/` de
   Django** —"el camino técnico, que deja rastro en su propio log"— y no una pantalla
   nueva dentro del módulo `fichas`.

---

## 5. Qué pasaría si se implementara de todos modos

Si en un sprint futuro el negocio decide que sí hace falta una edición directa (por
ejemplo, para corregir una dirección mal escrita sin round-trip al censista), la
historia tendría que replantearse como una **excepción explícita y acotada**, no como
una ampliación de `fichas.editar`:

- Qué campos son corregibles sin re-atribuir el registro (candidatos: dirección,
  coordenadas GPS, datos administrativos) frente a los que si se tocan cambian el
  sentido de "quién estuvo ahí" (integrantes, respuestas del hogar).
- Un campo de auditoría propio (`corregido_por` / `corregido_en`), separado de
  `censista`, para no perder la atribución original.
- Si eso ocurre, es una historia nueva con su propio número, no una reinterpretación
  de esta.

---

## 6. Cobertura de pruebas

No se agregan pruebas nuevas porque no hay comportamiento nuevo que probar. El camino
que satisface esta historia ya está cubierto por las pruebas de HU-15
(`fichas/tests.py`, sección rotulada `# HU-15`), en particular:

| Clase | Qué comprueba, relevante para esta historia |
|---|---|
| `DevolverEncuestaVistaTest` | el supervisor no puede resolver su propia ficha ni la de otro supervisor; solo devuelve la que está en revisión |
| `ObservacionesParaElEncuestadorTest` | el censista lee el motivo, corrige su propio registro y lo reenvía |
| `IntegracionHU15Test` | el circuito completo: devolver → leer → corregir → reenviar → validar |

```bash
cd backend
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test fichas
```

---

## 7. Explicación para la defensa

**En una frase:** la historia pide corregir errores, no reasignar quién los corrige; el
sistema ya separa esas dos cosas desde la HU-15, y abrir una edición directa para
supervisor/administrador rompería una regla de integridad de datos que el propio
código documenta a propósito.

**Lo que conviene poder defender:**

1. **No es una omisión, es una decisión verificada contra el código.** Se revisaron los
   dos puntos exactos donde el sistema impide la edición ajena —`zonas_disponibles()`
   y `HogarDeLaEncuestaMixin`— antes de decidir no construir nada nuevo.
2. **El objetivo de negocio de la historia ya se cumple**, por otro camino: HU-15
   permite corregir cualquier error detectado en revisión, con el censista original
   como autor de la corrección.
3. **La puerta de excepción existe y es deliberada**: `/admin/` de Django, para casos
   verdaderamente excepcionales, con su propio registro de cambios.

---

## 8. Posibles preguntas del profesor

**¿Por qué esta HU no tiene código si el enunciado pide editar?**
Porque revisar el sistema antes de programar mostró que editar directamente el trabajo
de otra persona ya estaba impedido a propósito, en dos capas, por una razón de
integridad de datos: el registro quedaría atribuido a quien no estuvo en la vivienda.
Construir una excepción a esa regla sin que el negocio lo pidiera explícitamente habría
sido resolver el síntoma equivocado.

**Entonces, ¿cómo se corrige un error si no es editando?**
Se devuelve la encuesta al censista que la levantó (`/encuestas/<pk>/devolver/`, HU-15)
con el motivo escrito. La ficha se reabre, el censista corrige su propio registro y la
reenvía a revisión. El error se corrige igual; solo cambia quién ejecuta la corrección.

**¿Y si el error está en algo que el censista ya no puede tocar, como una vivienda de
otro sector?**
`EditarViviendaView` ya permite corregir una vivienda a cualquier censista con esa zona
asignada, no solo a quien la registró —el comentario en `fichas/views.py:577` lo dice
explícitamente: "completar una vivienda que registró un compañero de sector es
legítimo". El caso sin cubrir es que alguien **sin ninguna zona asignada** (supervisor,
administrador) corrija directamente, y para ese caso extremo la vía es `/admin/`.

**¿Qué haría falta para construir la edición directa si el negocio insiste en pedirla?**
Separar qué campos son corregibles sin perder la atribución original (dirección,
coordenadas) de los que si se tocan cambian el sentido de "quién estuvo ahí"
(integrantes, respuestas del hogar), y agregar un campo de auditoría propio distinto de
`censista`. Sería una historia nueva, con su propio análisis de qué se permite y qué no
— no una reinterpretación de esta.
