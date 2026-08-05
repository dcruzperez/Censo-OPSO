# HU-11 · Captura de la ubicación GPS

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero capturar automáticamente la ubicación GPS de la encuesta para validar su ubicación geográfica.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · HTML/CSS/Bootstrap 5.3
**Estado:** implementada y verificada con **63 pruebas automáticas** propias (**1.049** en total en el proyecto → `python manage.py test` → OK)

> Esta historia **no agrega ni un permiso** y es la **primera del proyecto con
> JavaScript propio**: la posición del aparato solo la puede pedir el navegador.
> Reutiliza `fichas.crear` y `fichas.editar` de la HU-04 y `zonas_disponibles()` de
> la HU-08. Cuelga de `Vivienda` **sin tocar ninguna otra tabla**, como la HU-08
> había previsto.

---

## Índice

1. [Explicación inicial: para qué sirve un punto](#1-explicación-inicial)
2. [Por qué la ubicación cuelga de la vivienda](#2-por-qué-cuelga-de-la-vivienda)
3. [Decimal y no float](#3-decimal-y-no-float)
4. [«Validar su ubicación»: las tres capas](#4-las-tres-capas-de-validación)
5. [La distancia, sin PostGIS](#5-la-distancia-sin-postgis)
6. [El JavaScript, y sus límites](#6-el-javascript-y-sus-límites)
7. [Sin mapa, y es deliberado](#7-sin-mapa-y-es-deliberado)
8. [La precisión es un dato, no un adorno](#8-la-precisión-es-un-dato)
9. [Por qué el GPS NO bloquea el cierre](#9-por-qué-el-gps-no-bloquea)
10. [Vistas, URLs y templates](#10-vistas-urls-y-templates)
11. [Seguridad y datos personales](#11-seguridad-y-datos-personales)
12. [Archivos creados y modificados](#12-archivos-creados-y-modificados)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 Qué resuelve un punto GPS

Una dirección escrita es ambigua en terreno: pasajes sin letrero, numeraciones que
saltan, «la casa del fondo». Un par de coordenadas no lo es. Con el punto guardado:

- el **supervisor** puede comprobar que la encuesta se levantó donde dice —que es
  literalmente lo que pide el título de la historia: *validar su ubicación
  geográfica*—;
- una **segunda visita** llega a la casa correcta aunque vaya otra persona;
- el **operativo siguiente** hereda la ubicación sin volver a buscarla.

### 1.2 Lo que aporta, en una tabla

| Antes | Después |
|---|---|
| «Pasaje Los Robles 47, la del fondo» | `-36.826700, -73.049700` |
| Un punto mal tomado parecía tan bueno como uno bien tomado | se guarda la **precisión** y se avisa cuando es mala |
| Un dedazo en el signo ponía la casa en Argelia | lo rechaza la base de datos |
| El teléfono devolvía la posición de hace media hora | el sistema lo detecta comparando con el resto de la zona |

---

## 2. Por qué cuelga de la vivienda

`latitud`, `longitud`, `precision_metros`, `ubicacion_capturada_en` y
`ubicacion_manual` son columnas de **`Vivienda`**, no de `Encuesta`.

Es consecuencia directa del corte que hizo la HU-08: **unas coordenadas describen un
lugar físico, no un trabajo**. Las tres consecuencias son concretas:

- dos hogares de la misma casa **comparten el punto**, y no puede haber dos
  versiones de dónde está la casa;
- el operativo del año que viene **hereda la ubicación** sin volver a medirla;
- una vivienda **sin encuesta abierta** sigue pudiendo tener punto.

La HU-08 escribió que el GPS y las fotografías colgarían de `Vivienda` sin cambiar
nada, y así fue: **esta historia no modificó ninguna otra tabla**.

---

## 3. Decimal y no float

Las coordenadas son `DecimalField(max_digits=9, decimal_places=6)`.

Un `float` binario **no puede representar exactamente 0,1**. El error es minúsculo,
pero en coordenadas se traduce en metros y —peor— en comparaciones que fallan por el
último dígito: un punto guardado y leído puede dejar de ser igual a sí mismo.
`DecimalField` guarda el número que se escribió.

**Seis decimales** es una precisión de unos 11 cm. El GPS de un teléfono da entre 5
y 20 m en el mejor caso, así que guardar más dígitos sería **fingir una exactitud
que el aparato no tiene**.

---

## 4. Las tres capas de validación

«Validar su ubicación geográfica» se implementa en tres niveles, y **cada uno
reacciona distinto a propósito**:

| Capa | Qué comprueba | Qué hace | Dónde vive |
|---|---|---|---|
| 1 | las dos coordenadas van juntas | **rechaza** | restricción de la tabla |
| 2 | el punto cae dentro de Chile | **rechaza** | restricción + formulario |
| 3 | el punto está cerca del resto de la zona | **pregunta** | formulario |

### 4.1 Capa 1 — media coordenada no ubica nada

```sql
CHECK ((latitud IS NULL AND longitud IS NULL)
    OR (latitud IS NOT NULL AND longitud IS NOT NULL))
```

Una latitud sin longitud es **una línea que cruza el planeta**. Sin la restricción
quedarían filas que *parecen* tener ubicación, y un mapa las dibujaría en cualquier
parte.

### 4.2 Capa 2 — el punto tiene que estar en Chile

Atrapa los dos errores habituales al escribir a mano:

- **olvidar el signo**: una latitud `+36` en vez de `-36` pone la vivienda en
  Argelia y nada avisa;
- **intercambiar latitud y longitud**.

El rango **incluye el territorio insular**. Si se acotara a Chile continental
(longitud −76 a −66), **Rapa Nui (−109,4) quedaría fuera**, y es territorio nacional
donde puede haber un operativo. Un límite que rechaza datos verdaderos es peor que
no tenerlo. Hay pruebas de Rapa Nui y de los dos extremos, norte y sur.

Los límites se escriben **una vez**, como constantes del módulo, y los usan la
restricción y el formulario. Dos copias con números distintos darían dos veredictos
para el mismo punto.

> Detalle: van a nivel de módulo y no dentro de la clase por una limitación del
> lenguaje — el cuerpo de una clase anidada (`class Meta`) no ve los nombres de la
> clase que la contiene.

### 4.3 Capa 3 — ¿está cerca del resto de la zona?

Esta **pregunta en vez de rechazar**, y la diferencia es el punto interesante de la
historia:

> Un punto fuera de Chile es **imposible**. Un punto lejos del resto de la zona es
> **improbable**: puede ser una parcela apartada que de verdad pertenece a la zona.

El caso real que persigue es concreto: **el teléfono devuelve la última posición
conocida**, la de donde estuvo hace media hora, y la guarda como si fuera la casa.
Comparando con el punto medio de las viviendas ya ubicadas de la zona, eso salta.

Si la distancia supera **500 m** el formulario se detiene, dice a cuántos metros
está y pide marcar una casilla. Es el mismo patrón del aviso de dirección duplicada
de la HU-08: **bloquear haría perder un dato verdadero; avisar cuesta un clic**.

Cuando la zona **no tiene ninguna otra vivienda ubicada** —la primera casa de la
jornada— no hay nada que comparar y no se pregunta. Inventar una referencia sería
peor que no comprobar.

Y al **recolocar** una vivienda, ella misma se excluye del cálculo: si no, mover una
casa 600 m siempre pediría confirmación contra su propia posición anterior.

---

## 5. La distancia, sin PostGIS

`Vivienda.distancia_a()` implementa la **fórmula del haversine** en doce líneas.

**¿Por qué no GeoDjango / PostGIS?** Porque haría falta instalar la extensión
PostGIS en el servidor y las bibliotecas GEOS y PROJ en cada equipo. Es una
dependencia grande, difícil de instalar en Windows, y complicaría la puesta en
marcha del proyecto —que hoy es `pip install -r requirements.txt`— **para ahorrarse
doce líneas**.

Si algún día hicieran falta consultas espaciales de verdad —«las viviendas dentro de
este polígono», «las diez más cercanas ordenadas por distancia»— PostGIS sería lo
correcto y esta función habría que tirarla. Mientras la pregunta sea «¿está este
punto lejos de aquel?», el haversine sobra.

Devuelve **metros** y no kilómetros porque las distancias que interesan son de
decenas o cientos de metros, y en kilómetros habría que leer «0,08» donde se quiere
leer «80».

Hay pruebas contra valores conocidos: un grado de latitud son ~111,2 km y una
diezmilésima de grado son ~11 m. Un cálculo geométrico no se comprueba «a ojo».

---

## 6. El JavaScript, y sus límites

Es la **única pantalla del proyecto con JavaScript propio**, y hace falta: la
posición del aparato solo la puede pedir el navegador con `navigator.geolocation`.
No existe forma de obtenerla desde el servidor.

### 6.1 Progressive enhancement, no dependencia

Los tres campos son **visibles y editables**. Sin JavaScript, sin permiso de
ubicación o bajo techo sin señal, la pantalla **sigue sirviendo**: se escriben las
coordenadas a mano y la encuesta no se queda sin punto. El botón de capturar es una
comodidad que rellena campos, **no el único camino**.

Además, un campo oculto que se rellena solo es imposible de revisar. Verlos permite
notar que el teléfono devolvió la posición de hace media hora.

### 6.2 Lo que el script sí hace bien

```js
{ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
```

- `enableHighAccuracy` pide el **GPS de verdad** y no la posición aproximada por
  red, que en terreno puede errar por kilómetros. Gasta más batería y aquí vale la
  pena: el punto **es** el dato.
- `maximumAge: 0` **prohíbe devolver una posición guardada** de antes, que es
  justamente el error que persigue la capa 3.
- Cada fallo tiene **su propio mensaje** —permiso denegado, sin señal, tiempo
  agotado— porque cada uno tiene una salida distinta y un «no se pudo» no ayuda.
- El aviso lleva `role="status"` y `aria-live="polite"` para que un lector de
  pantalla anuncie el resultado, que si no sería un cambio invisible.

### 6.3 Dos cosas que conviene saber al probarlo

- **La geolocalización exige HTTPS** en los navegadores actuales, con una excepción:
  `localhost`. En desarrollo funciona; para probarlo desde un teléfono en la red
  local hace falta un certificado o un túnel.
- El umbral de precisión llega del modelo a la plantilla, así que **pantalla y
  servidor no pueden discrepar** sobre qué es un punto bueno.

---

## 7. Sin mapa, y es deliberado

Dibujar el punto sobre un mapa sería más bonito y exigiría pedir las imágenes a un
servidor ajeno —OpenStreetMap, Google, Mapbox—, lo que significa dos cosas que este
proyecto no acepta:

1. **OPSO dejaría de funcionar sin internet.** Hasta Bootstrap está servido
   localmente, precisamente para eso.
2. **Las coordenadas de la casa de una familia viajarían a un tercero** cada vez que
   alguien abriera la ficha.

Si el mapa hiciera falta, la forma correcta sería un **servidor de teselas propio**.
Hay una prueba que comprueba que la página no menciona ningún dominio externo.

---

## 8. La precisión es un dato

`precision_metros` guarda el radio de error que **informa el propio aparato**. Sin
ese dato, **un punto tomado dentro de una casa parece tan bueno como uno tomado en
la calle**, y no lo es.

El umbral es **20 metros**: aproximadamente el ancho de una calle con sus dos
veredas. Por debajo, el punto distingue una casa de la de enfrente; por encima, ya
no.

Qué hace el sistema con eso:

- el mensaje de confirmación **dice la precisión** y, si es mala, sugiere repetir la
  captura afuera —«guardado» a secas escondería que el punto no sirve—;
- la ficha de la vivienda lo muestra como `±8 m` en verde o `±300 m, poco precisa`
  en ámbar;
- la pantalla de terminar la encuesta **avisa** si la precisión es mala.

**Sin dato de precisión, `precision_aceptable` devuelve False**: de un punto del que
no se sabe el error no se puede decir que sirve. Misma lógica con la que
`datos_completos` trata el vacío en la HU-08.

Y se distingue **cómo se obtuvo**: `ubicacion_manual` marca los puntos escritos a
mano, que no merecen la misma confianza. La suposición por defecto es la prudente —
si el script no marcó la captura, se guarda como manual.

---

## 9. Por qué el GPS no bloquea

Sería fácil agregar la ubicación a `pasos_pendientes()` (HU-10) y sería un error.

> El GPS depende de que haya señal, de que el sistema operativo dé el permiso y de
> que el teléfono no esté bajo techo: **nada de eso lo controla el encuestador**.

Exigirlo para terminar dejaría fichas completas y correctas atrapadas en borrador
por un fallo de cobertura, y la salida sería **inventar coordenadas** — que es
exactamente lo que todas las decisiones de este proyecto han evitado.

Lo que hace el sistema es **avisar** en la pantalla de terminar, con el enlace para
capturarla si todavía se está en la puerta. La regla, ya usada en la HU-08 y la
HU-10:

> **Se bloquea lo que el usuario puede resolver; se avisa de lo que quizá no.**

---

## 10. Vistas, URLs y templates

| URL | Qué hace |
|---|---|
| `/encuestas/viviendas/<pk>/ubicacion/` | captura o corrige el punto |

**Es una pantalla aparte y no un campo del formulario de vivienda**, porque la
ubicación se toma **en otro momento y a veces en otro sitio**: el formulario de la
vivienda se llena conversando, muchas veces dentro de la casa —donde el GPS es
peor—; el punto se toma en la puerta y son diez segundos. Mezclarlos acabaría
guardando la posición de donde estuviera el teléfono en ese instante.

Hay además un caso que solo esta pantalla resuelve: **las viviendas anteriores a la
HU-11 no tienen punto**, y hay que poder capturárselo al volver a pasar sin editar
todo lo demás.

**Quién puede**: las mismas reglas que editar la vivienda —zona asignada y
territorio abierto—. No se exige que la encuesta sea propia, por lo mismo que en
`EditarViviendaView`: el sector puede estar repartido y **la casa es la misma para
todas**. La ubicación describe el inmueble, no el trabajo de nadie.

---

## 11. Seguridad y datos personales

- **Octava historia seguida sin agregar permisos.**
- **Las coordenadas de una vivienda son un dato personal**: dicen dónde vive una
  familia. La pantalla lo dice explícitamente, y **no salen de OPSO** —ni siquiera
  para dibujar un mapa (sección 7)—.
- Las tres capas de validación se aplican **en el servidor**. El JavaScript rellena
  campos; no valida nada que el servidor no vuelva a comprobar.
- Un punto imposible se rechaza **con o sin** la casilla de confirmación: esa
  casilla solo cubre la lejanía, no el rango. Hay una prueba de eso.

---

## 12. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0005_ubicacion_gps.py
backend/templates/fichas/ubicacion_form.html      la única pantalla con JS propio
backend/docs/HU-11_ubicacion_gps.md               este documento
```

### Modificados

```
backend/fichas/models.py     + 5 columnas y 2 restricciones en Vivienda
                             + distancia_a(), centro_de_la_zona(), coordenadas,
                               precision_aceptable; nota en pasos_pendientes()
backend/fichas/forms.py      + UbicacionForm con las tres capas de validación
backend/fichas/views.py      + CapturarUbicacionView
backend/fichas/urls.py       + 1 ruta
backend/fichas/tests.py      + 63 pruebas
backend/fichas/management/commands/crear_encuestas_demo.py   siembra coordenadas
backend/templates/fichas/vivienda_detalle.html    + bloque de ubicación
backend/templates/fichas/encuesta_completar.html  + aviso no bloqueante
backend/README.md · README.md
```

**Ninguna tabla que no fuera `fichas_vivienda` cambió.**

---

## 13. Pruebas

```bash
python manage.py test fichas          # 503 (HU-07 a HU-11)
python manage.py test                 # 1.049 en total
```

| Bloque | Qué comprueba |
|---|---|
| `UbicacionModeloTest` | coordenadas formateadas, umbral de precisión, sin dato no es aceptable |
| `DistanciaTest` | haversine contra valores conocidos, centro de zona, exclusión |
| `RestriccionesUbicacionTest` | media coordenada, signo invertido, ejes intercambiados, **Rapa Nui sí** |
| `UbicacionFormTest` | obligatoriedad, mensajes por signo, marca de manual, las tres capas |
| `CapturarUbicacionTest` | pantalla, script presente, **sin dominios externos**, mensajes por precisión, 404 ajena |
| `UbicacionEnLasPantallasTest` | ficha, avisos al terminar, y que **no bloquea** |
| `IntegracionHU11Test` | recorrido: captura, vecina cerca, lejana rechazada, confirmada, imposible rechazada |

---

## 14. Explicación para la defensa

**En una frase:** el punto GPS convierte «la casa del fondo del pasaje» en un dato
verificable, y el sistema se toma en serio **cuánto vale** ese punto.

**Las tres cosas que conviene poder defender:**

1. **Tres capas de validación con tres reacciones distintas.** Se rechaza lo
   imposible (media coordenada, fuera de Chile) y se pregunta por lo improbable
   (lejos del resto de la zona). Bloquear lo improbable haría perder datos
   verdaderos.
2. **La precisión se guarda y se usa.** Sin ella, un punto tomado bajo techo parece
   tan bueno como uno tomado en la calle. El sistema lo dice en el mensaje, en la
   ficha y al terminar la encuesta.
3. **El GPS no bloquea el cierre.** Depende de la señal y del permiso del sistema:
   exigirlo dejaría fichas correctas atrapadas y empujaría a inventar coordenadas.

**Dos decisiones que se explican solas:** no se usó PostGIS para una función de doce
líneas, y no hay mapa porque las coordenadas de una familia no deben viajar a un
servidor ajeno cada vez que alguien abre la ficha.

---

## 15. Posibles preguntas del profesor

**¿Por qué la ubicación está en la vivienda y no en la encuesta?**
Porque describe un lugar físico, no un trabajo. Dos hogares de la misma casa
comparten el punto, y el operativo del año que viene lo hereda.

**¿Por qué Decimal y no float?**
Porque un float binario no representa exactamente 0,1, y en coordenadas ese error
son metros y comparaciones que fallan por el último dígito.

**¿Por qué no usaste PostGIS?**
Porque lo único que OPSO necesita de la geometría es una distancia entre dos puntos.
PostGIS exige extensión en el servidor y bibliotecas en cada equipo; el haversine
son doce líneas. Si hicieran falta consultas espaciales de verdad, PostGIS sería lo
correcto y esta función se tiraría.

**¿Por qué no muestras un mapa?**
Porque las teselas vienen de un servidor ajeno: OPSO dejaría de funcionar sin
internet y las coordenadas de la casa de una familia viajarían a un tercero cada vez
que se abre la ficha. Con un servidor de teselas propio, sí.

**¿Y si el encuestador no tiene señal?**
Puede escribir las coordenadas a mano —quedan marcadas como tales— o terminar la
encuesta sin ubicación: el sistema avisa pero no bloquea.

**¿Cómo detectas un punto tomado con la posición antigua del teléfono?**
Comparándolo con el punto medio de las viviendas ya ubicadas de la zona. A más de
500 m, el formulario pregunta. Y el script pide `maximumAge: 0`, que prohíbe al
navegador devolver una posición guardada.

**¿Por qué Rapa Nui aparece en las pruebas?**
Porque su longitud es −109,4 y un rango acotado a Chile continental la habría
rechazado. Un límite que rechaza datos verdaderos es peor que no tenerlo.

**¿El JavaScript no rompe el proyecto si está desactivado?**
No. Los tres campos son editables y el formulario funciona igual: el script rellena
campos, no sostiene la pantalla.

---

## 16. Conclusión técnica

La HU-11 agrega **cinco columnas, dos restricciones, una pantalla y ningún permiso**,
y es la primera del proyecto que necesita JavaScript — con la disciplina de que la
pantalla funcione sin él.

Su valor técnico está en tres cosas:

1. **Distingue lo imposible de lo improbable.** Tres capas de validación, dos que
   rechazan y una que pregunta, cada una en el sitio donde puede ser cierta.
2. **Guarda la calidad del dato junto al dato.** La precisión y el origen —capturado
   o escrito— hacen que un punto malo no pueda hacerse pasar por uno bueno.
3. **Elige bien qué NO hacer.** Sin PostGIS para doce líneas, sin mapa a cambio de
   la privacidad de una familia, y sin bloquear el cierre por algo que el
   encuestador no controla.

Queda una historia del sprint: las **fotografías de la vivienda** (HU-12), que
cuelgan de `Vivienda` igual que este punto y son las primeras que traen archivos al
proyecto.
