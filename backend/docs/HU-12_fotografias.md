# HU-12 · Fotografías de la vivienda

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como encuestador, quiero adjuntar fotografías de la vivienda cuando sea necesario como evidencia del levantamiento.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Pillow 12.3 · Bootstrap 5.3
**Estado:** implementada y verificada con **56 pruebas automáticas** propias (**1.105** en total en el proyecto → `python manage.py test` → OK)

> Última historia del sprint del encuestador. **No agrega ni un permiso** y es la
> primera del proyecto que guarda **archivos**, lo que trae una decisión de
> seguridad que no había aparecido nunca: **los archivos subidos no se pueden servir
> como estáticos**. Cuelga de `Vivienda` sin tocar ninguna otra tabla, igual que el
> GPS de la HU-11.

---

## Índice

1. [Explicación inicial: «cuando sea necesario»](#1-explicación-inicial)
2. [Una dependencia nueva, y por qué es un control de seguridad](#2-pillow)
3. [El modelo](#3-el-modelo)
4. [El nombre del archivo se descarta](#4-el-nombre-del-archivo)
5. [La decisión central: no servir MEDIA como estáticos](#5-no-servir-media)
6. [Lo que valida el formulario, y en qué orden](#6-lo-que-valida-el-formulario)
7. [No se fotografía a las personas](#7-no-se-fotografía-a-las-personas)
8. [Borrar de verdad, archivo incluido](#8-borrar-de-verdad)
9. [Vistas, URLs y templates](#9-vistas-urls-y-templates)
10. [Configuración](#10-configuración)
11. [Archivos creados y modificados](#11-archivos-creados-y-modificados)
12. [Pruebas](#12-pruebas)
13. [Explicación para la defensa](#13-explicación-para-la-defensa)
14. [Posibles preguntas del profesor](#14-posibles-preguntas-del-profesor)
15. [El sprint completo](#15-el-sprint-completo)
16. [Conclusión técnica](#16-conclusión-técnica)

---

## 1. Explicación inicial

### 1.1 Qué resuelve

Hay cosas que una ficha no puede explicar con texto: un número de casa borrado, un
pasaje sin letrero, una construcción a medio levantar, un medidor compartido entre
tres viviendas. La fotografía es la evidencia de que **lo que dice la ficha es lo
que había**.

### 1.2 «Cuando sea necesario» no es un adorno del enunciado

Es la parte de la historia que más condiciona el diseño. Un formulario que solo
dijera «sube una imagen» produciría **álbumes de casas ajenas**, que es exactamente
lo que un censo no debe acumular.

Por eso la pantalla **no empuja a fotografiar**:

| Mecanismo | Qué consigue |
|---|---|
| hay que elegir **qué se documenta** entre seis tipos | obliga a pensar antes de disparar |
| la **descripción es obligatoria** | si no se puede explicar por qué hizo falta, no hacía falta |
| tope de **5 fotos por vivienda** | la ficha no se vuelve un álbum |
| advertencia de **no fotografiar personas**, antes del campo | ver la sección 7 |

---

## 2. Pillow

Es la primera dependencia nueva desde el inicio del proyecto, y **no es una
comodidad: es un control de seguridad**.

`ImageField` **decodifica** el archivo con Pillow para comprobar que es una imagen.
Comprobar la extensión no valida nada, porque cualquiera puede renombrar un
archivo, y un `.jpg` que en realidad es otra cosa, subido a un servidor mal
configurado, es un problema serio.

Está fijada en `requirements.txt` con ese comentario, junto a las demás.

```
Pillow==12.3.0
```

---

## 3. El modelo

Una tabla nueva, `fichas_fotografia`, colgando de **`Vivienda`**.

Igual que la ubicación GPS de la HU-11 y por el mismo motivo: **una fotografía de la
fachada documenta un inmueble, no el trabajo de una persona**. Dos hogares de la
misma casa comparten la foto de la puerta, y el operativo siguiente la hereda.

Es la **tercera historia seguida** que cuelga de `Vivienda` sin tocar nada más —la
confirmación definitiva de que el corte de la HU-08 estaba bien hecho.

| Campo | Nota |
|---|---|
| `imagen` | `ImageField` con `upload_to` calculado (sección 4) |
| `tipo` | fachada, acceso, materialidad, servicios, croquis, otra |
| `descripcion` | **obligatoria**, con restricción en la base de datos |
| `tomada_por` | quién la subió (`SET_NULL`) |
| `tomada_en` | automática |

Dos restricciones:

```sql
CHECK (tipo IN (...))          -- fotografia_tipo_valido
CHECK (descripcion <> '')      -- fotografia_con_descripcion
```

La segunda no es celo: **una foto sin explicación no es evidencia de nada**, y
dentro de seis meses nadie sabrá qué se estaba mirando. La restricción lo garantiza
también para lo que no pase por el formulario, como una carga desde `/admin/`.

---

## 4. El nombre del archivo

Se guarda como `fichas/2026/08/<uuid4>.jpg`. **El nombre original se descarta por
completo**, por tres motivos distintos y los tres reales:

1. **Seguridad.** El nombre que llega en la subida lo elige quien sube: puede
   contener rutas relativas, caracteres que el sistema de archivos interpreta o
   tener 600 caracteres. Django ya lo limpia, pero **el modo seguro de tratar una
   entrada peligrosa es no usarla**.
2. **Imposibilidad de adivinar.** Aunque algún día alguien configure mal el servidor
   y deje la carpeta accesible, un archivo con nombre UUID no se encuentra probando
   direcciones. Es una **segunda línea de defensa** detrás de la vista de la sección
   5, no un sustituto de ella.
3. **Colisiones.** Diez teléfonos subiendo «IMG_0001.jpg» el mismo día terminan en
   diez archivos con sufijos numéricos y nombres que ya no dicen nada.

Se reparte por año y mes porque una carpeta con cien mil archivos es lenta de listar
y desagradable de respaldar. El año y el mes no identifican a nadie.

La extensión se conserva **solo si es una de las admitidas**; con cualquier otra
cosa se escribe `.jpg`. La extensión en disco es una comodidad para el sistema
operativo, **no la fuente de verdad sobre el contenido**: eso lo decidió Pillow.

---

## 5. No servir MEDIA

**Es la decisión más importante de la historia, y la más fácil de hacer mal.**

Lo habitual en un proyecto Django es añadir en `urls.py`:

```python
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

…y en producción un `location /media/` en Nginx. Con eso:

> **Cualquiera que conozca o adivine la dirección de un archivo lo descarga: sin
> sesión, sin rol y sin dejar rastro.**

Para un logotipo da igual. Para la fotografía de la casa de una familia censada, es
**publicar datos personales en internet**.

**OPSO no sirve `MEDIA_ROOT` en ningún entorno.** Los archivos se entregan por
`ServirFotografiaView`, que comprueba:

- que haya **sesión iniciada y permiso del módulo** (el mixin de la HU-04);
- que quien pregunta **tenga algo que ver con esa vivienda**: con `fichas.ver_todas`
  ve todas —lo que el supervisor necesita para revisar—; sin ese permiso, solo las
  de viviendas donde tiene trabajo o territorio asignado.

Y dos cabeceras que importan:

| Cabecera | Para qué |
|---|---|
| `X-Content-Type-Options: nosniff` | el navegador no adivina el tipo: si algo no fuera una imagen, no lo interpretará como otra cosa |
| `Cache-Control: private, no-store` | son datos personales; no pueden quedar en cachés intermedias |

Se usa `FileResponse`, que envía el archivo **por trozos** en vez de cargarlo entero
en memoria: con varias personas mirando fotos a la vez, la diferencia es el
servidor.

> **En producción**, servir archivos desde Python es más lento que hacerlo desde el
> servidor web. La forma correcta de recuperar ese rendimiento **sin perder el
> control de acceso** es `X-Accel-Redirect` (Nginx) o `X-Sendfile` (Apache): Django
> decide si la persona puede, y el servidor web entrega el archivo. Queda anotado en
> el código porque es un cambio de una línea y conviene no improvisarlo.

Hay una prueba que resume todo esto y que **fallaría si alguien agregara
`static(MEDIA_URL, ...)` a las URLs**, que es exactamente lo que tiene que pasar:

```python
def test_la_carpeta_media_no_se_sirve_como_estatica(self):
    respuesta = self.client.get(f"/{settings.MEDIA_URL}{self.foto.imagen.name}")
    self.assertNotEqual(respuesta.status_code, 200)
```

---

## 6. Lo que valida el formulario

Es el formulario con más validación del proyecto, y no por gusto: **es el único que
acepta un archivo**, que es la entrada más peligrosa que puede recibir una
aplicación web.

| # | Comprueba | Cómo |
|---|---|---|
| 1 | que sea **una imagen de verdad** | `ImageField` la decodifica con Pillow |
| 2 | que el **formato** sea JPEG, PNG o WEBP | Pillow abre docenas de formatos, algunos con historial de vulnerabilidades |
| 3 | que **no pese** más de 5 MB | evita bloquear la subida en una conexión de terreno |
| 4 | que la vivienda **no acumule un álbum** | tope de 5 |
| 5 | que haya **descripción** | mínimo una frase |

### 6.1 El orden importa

**El tamaño se comprueba antes que el formato**, y no es casual:

> Validar el formato obliga a **decodificar** la imagen, y decodificar una imagen
> enorme —o una preparada para expandirse al descomprimirse— consume memoria. Mirar
> `size` es leer un número que ya está ahí.

**Se rechaza barato antes de gastar caro.**

---

## 7. No se fotografía a las personas

Es la regla más importante de la historia **y no hay ningún campo que la
represente**: es una prohibición, no una opción.

Una fotografía de una persona en su casa es un dato personal de una categoría mucho
más sensible que su nombre o su ingreso, y **nada en este censo la necesita**.

Cómo lo aplica el sistema, sabiendo que no puede impedirlo del todo:

- el catálogo de tipos **no ofrece** «integrante» ni «grupo familiar»: no hay ningún
  motivo previsto para fotografiar gente;
- el formulario **lo advierte antes del campo de archivo** —leerlo cuando la foto ya
  está seleccionada no sirve de nada, y en un teléfono el selector se abre al primer
  toque—;
- la **descripción obligatoria** obliga a decir qué se está documentando;
- la foto es **borrable** mientras la encuesta siga abierta.

> Un sistema no puede impedir que alguien suba una foto equivocada. Lo que sí puede
> hacer —y hace— es **no ofrecerle nunca un motivo** para hacerlo.

---

## 8. Borrar de verdad

**Django no borra el archivo al borrar la fila.** Dejó de hacerlo a propósito hace
muchas versiones, porque en una transacción que se revierte el archivo ya no se
podría recuperar. La consecuencia es que hay que borrarlo explícitamente, y **si no
se hace, el disco acumula fotografías de casas de familias que ya nadie puede ver ni
saber que están ahí**.

Para datos personales eso no es un descuido de limpieza: es **conservar información
que ya no debería existir**, justo lo contrario de la minimización de datos
(Ley N° 21.719). Por eso el borrado vive en `Fotografia.borrar_archivo()` y no
repartido por las vistas.

Es la **segunda pantalla del proyecto que borra de verdad**, después de quitar a un
integrante en la HU-09, y por el mismo motivo: lo que se elimina es un dato
capturado por error, no un registro histórico que explique algo.

Dos pasos, como siempre: con un GET capaz de borrar, un `<img src="...">` incrustado
en cualquier página lo ejecutaría con la sesión de quien la mirara.

---

## 9. Vistas, URLs y templates

| URL | Qué hace |
|---|---|
| `/encuestas/viviendas/<pk>/fotografias/nueva/` | adjuntar |
| `/encuestas/fotografias/<pk>/ver/` | **entregar el archivo, con control de acceso** |
| `/encuestas/fotografias/<pk>/quitar/` | GET confirma, POST borra |

Subir va bajo la **vivienda** porque hace falta saber a cuál se adjunta; ver y
quitar van bajo `/fotografias/<pk>/` porque la foto ya sabe de qué vivienda es.

**Quién puede escribir**: las mismas reglas que editar la vivienda o capturar el
GPS. No se exige que la encuesta sea propia: la foto documenta el inmueble, y el
sector puede estar repartido.

> Detalle que rompe la primera subida de archivos de cualquier proyecto: el
> formulario necesita `enctype="multipart/form-data"` y la vista necesita
> `request.FILES`. Sin lo primero el navegador manda solo el nombre; sin lo segundo
> el campo llega vacío. Hay una prueba que comprueba el `enctype`.

En el admin, `Fotografia` **solo aparece como inline de la vivienda**, sin pantalla
propia. Es deliberado: una pantalla que lista todas las fotografías del operativo es
un álbum de casas de familias, y ninguna tarea la necesita.

---

## 10. Configuración

```python
MEDIA_ROOT = BASE_DIR / "media"           # dónde se guardan
MEDIA_URL  = "media/"                     # NO se sirve: ver la sección 5

OPSO_TAMANO_MAXIMO_FOTO        = 5 MB
OPSO_MAXIMO_FOTOS_POR_VIVIENDA = 5
FILE_UPLOAD_MAX_MEMORY_SIZE    = 1 MB     # a partir de ahí, a disco temporal
FILE_UPLOAD_PERMISSIONS        = 0o600    # solo el usuario de la aplicación
```

`FILE_UPLOAD_PERMISSIONS` merece una nota: sin él, el sistema usa el *umask* del
proceso, que en muchos servidores deja los archivos **legibles para todo el
mundo**. Con datos personales, ese valor por defecto no sirve.

`FILE_UPLOAD_MAX_MEMORY_SIZE` se baja del valor por defecto (2,5 MB) porque en
terreno pueden llegar varias subidas a la vez y **la memoria del servidor es el
recurso que primero se agota**.

`media/` ya estaba en `.gitignore`: las fotografías **no se versionan**.

---

## 11. Archivos creados y modificados

### Creados

```
backend/fichas/migrations/0006_fotografias.py
backend/templates/fichas/fotografia_form.html
backend/templates/fichas/fotografia_quitar.html
backend/docs/HU-12_fotografias.md                  este documento
```

### Modificados

```
backend/requirements.txt     + Pillow==12.3.0, con el porqué
backend/config/settings.py   + MEDIA_ROOT/MEDIA_URL y los cuatro límites de subida
backend/fichas/models.py     + Fotografia, TipoFotografia, ruta_de_la_fotografia()
backend/fichas/forms.py      + FotografiaForm
backend/fichas/views.py      + SubirFotografiaView, QuitarFotografiaView,
                               ServirFotografiaView y su mixin
backend/fichas/urls.py       + 3 rutas
backend/fichas/admin.py      + FotografiaInline (sin pantalla propia)
backend/fichas/tests.py      + 56 pruebas
backend/templates/fichas/vivienda_detalle.html   + galería de la vivienda
backend/README.md · README.md
```

---

## 12. Pruebas

```bash
python manage.py test fichas          # 559 (HU-07 a HU-12)
python manage.py test                 # 1.105 en total
```

Las pruebas construyen **imágenes de verdad en memoria con Pillow**: unos bytes
cualesquiera no servirían, porque el control que se quiere probar es justamente que
`ImageField` las decodifica. Y usan `override_settings(MEDIA_ROOT=carpeta temporal)`
para no ir llenando la carpeta real del proyecto.

| Bloque | Qué comprueba |
|---|---|
| `FotografiaModeloTest` | nombre UUID, extensión reemplazada, reparto por año/mes, borrado del archivo |
| `RestriccionesFotografiaTest` | tipo inválido y descripción vacía los rechaza la base |
| `FotografiaFormTest` | archivo que no es imagen, GIF rechazado, PNG/WEBP aceptados, tamaño, tope |
| `SubirFotografiaTest` | `enctype`, advertencia visible, autoría, 404 ajena, supervisor sin acceso |
| `QuitarFotografiaTest` | GET no borra, POST borra fila **y archivo** |
| `ServirFotografiaTest` | anónimo no, ajeno 404, supervisor sí, cabeceras, archivo faltante, **media no es pública** |
| `FotografiasEnLaFichaTest` | galería, y que nunca se enlaza el archivo directo |
| `IntegracionHU12Test` | recorrido completo hasta el borrado del archivo |

> Detalle que apareció al ejecutarlas en Windows: `FileResponse` **deja el archivo
> abierto** hasta que se cierra la respuesta, y en Windows un archivo abierto no se
> puede borrar. En producción lo cierra el servidor al terminar de enviarlo; en una
> prueba que después borra el archivo hay que llamar a `respuesta.close()`. Está
> comentado en la prueba donde ocurre.

---

## 13. Explicación para la defensa

**En una frase:** la foto es la evidencia de que lo que dice la ficha es lo que
había, y todo el diseño está pensado para que sean **pocas, justificadas y
privadas**.

**Las tres cosas que conviene poder defender:**

1. **Los archivos subidos no se sirven como estáticos.** El atajo habitual deja cada
   foto descargable por cualquiera que conozca la dirección, sin sesión ni rastro.
   OPSO las entrega por una vista que comprueba quién pregunta, y hay una prueba que
   fallaría si alguien reintrodujera el atajo.
2. **Pillow es un control de seguridad, no una comodidad.** Comprobar la extensión
   no valida nada; decodificar la imagen sí. Y el tamaño se comprueba **antes** que
   el formato, porque decodificar es lo caro.
3. **No se fotografía a las personas.** Es una prohibición sin campo que la
   represente: el catálogo no ofrece motivos para hacerlo, la advertencia va antes
   del campo de archivo y la descripción obligatoria fuerza a decir qué se
   documenta.

---

## 14. Posibles preguntas del profesor

**¿Por qué no sirves la carpeta media como hace todo el mundo?**
Porque con eso cualquiera que conozca la dirección descarga la foto de la casa de
una familia sin sesión, sin permiso y sin dejar rastro. Se entregan por una vista
que comprueba quién pregunta.

**¿No es lento servir archivos desde Django?**
Sí, y por eso está anotado en el código que en producción se usa `X-Accel-Redirect`
o `X-Sendfile`: Django decide si la persona puede y el servidor web entrega el
archivo. Es un cambio de una línea que no sacrifica el control de acceso.

**¿Por qué renombras los archivos?**
Por seguridad —el nombre lo elige quien sube—, para que la dirección no se pueda
adivinar y para evitar colisiones entre diez teléfonos subiendo «IMG_0001.jpg».

**¿Cómo sabes que lo subido es una imagen?**
Porque Pillow la decodifica. La extensión no prueba nada: cualquiera renombra un
archivo.

**¿Por qué compruebas el tamaño antes que el formato?**
Porque validar el formato obliga a decodificar, y decodificar una imagen enorme
consume memoria. Mirar el tamaño es leer un número.

**¿Qué impide que alguien fotografíe a la familia?**
Nada puede impedirlo del todo. Lo que hace el sistema es no darle nunca un motivo:
ningún tipo de evidencia lo contempla, la advertencia aparece antes del campo, hay
que explicar por escrito qué muestra la foto y se puede borrar.

**¿Por qué aquí sí se borra de verdad?**
Igual que al quitar a un integrante en la HU-09: es un dato capturado por error, no
un registro histórico. Y son datos personales: conservarlos «por si acaso» es lo
contrario de la minimización de datos.

**¿Por qué un tope de cinco fotos?**
Porque la historia dice «cuando sea necesario». Sin tope, la ficha se vuelve un
álbum de casas ajenas.

---

## 15. El sprint completo

Con esta historia terminan las seis del encuestador:

| HU | Historia | Pruebas | Tablas nuevas |
|---|---|---|---|
| 07 | Visualizar las encuestas asignadas y su estado | 137 | `encuesta` |
| 08 | Registrar vivienda y grupo familiar | 121 | `vivienda`, `grupo_familiar` |
| 09 | Registrar los integrantes del hogar | 97 | `integrante` |
| 10 | Guardar borradores y cerrar la encuesta | 85 | — |
| 11 | Capturar la ubicación GPS | 63 | — |
| 12 | Adjuntar fotografías | 56 | `fotografia` |
| | **Total del módulo** | **559** | **6 tablas** |

**Ninguna de las seis agregó un permiso.** Las cuatro que gobiernan el módulo
—`fichas.ver_propias`, `fichas.ver_todas`, `fichas.crear` y `fichas.editar`— las
sembró la HU-04 cuando no existía todavía ninguna pantalla de fichas.

Y las tres últimas colgaron de `Vivienda` **sin cambiar ninguna otra tabla**, que es
lo que la HU-08 había previsto por escrito al separar vivienda, encuesta y hogar.

**Lo que falta para cerrar el ciclo completo del censo** es la parte del supervisor:
validar u observar las fichas que llegan (`fichas.validar`, ya sembrado), y los
reportes de avance (`reportes.ver` y `reportes.exportar`, también sembrados). Las
tres pantallas que faltan ya tienen su permiso esperándolas.

---

## 16. Conclusión técnica

La HU-12 agrega **una tabla, tres pantallas, una dependencia y ningún permiso**, y
es la primera del proyecto que maneja archivos.

Su valor técnico está en tres cosas:

1. **Identifica el riesgo que trae un archivo subido y lo trata como tal.** No
   servir `MEDIA_ROOT` es la decisión que separa un sistema que guarda datos
   personales de uno que los publica sin saberlo.
2. **Valida en el orden correcto y con la herramienta correcta.** Pillow decodifica,
   el tamaño se mira antes, y la extensión no decide nada.
3. **Traduce «cuando sea necesario» a mecanismos concretos**: tipos cerrados,
   descripción obligatoria, tope por vivienda y una advertencia que se lee antes de
   elegir el archivo.
