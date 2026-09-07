# HU-04 · Asignar roles y permisos desde una matriz configurable

**Proyecto:** OPSO — Operativo Social
**Historia de usuario:** *Como administrador, quiero asignar permisos a los roles desde una matriz configurable para controlar qué puede hacer cada perfil sin modificar código.*
**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3
**Estado:** implementada y verificada con **132 pruebas automáticas** propias (281 en total en el proyecto en el momento del commit `16c0768`; hoy, con las historias posteriores, son 1.423 → `python manage.py test` → OK)

> **Nota sobre este documento.** Es el único de las quince primeras historias que
> se integró sin su propio archivo — el propio `CLAUDE.md` lo señala como deuda
> pendiente, no como precedente a imitar. Se escribió después, reconstruyendo las
> decisiones a partir del código, las migraciones, las 132 pruebas de
> `tests_permisos.py` y el mensaje del commit `16c0768` que integró la historia
> completa. No hay nada inventado: cada afirmación se verificó contra el estado
> actual del repositorio.

---

## Índice

1. [Explicación inicial](#1-explicación-inicial)
2. [Decisiones de diseño](#2-decisiones-de-diseño)
3. [El modelo: `Permiso` y `Rol`](#3-el-modelo)
4. [`Usuario.tiene_permiso()`: las tres reglas](#4-tiene_permiso)
5. [Dos mixins para dos preguntas distintas](#5-dos-mixins)
6. [Los decoradores equivalentes, para vistas de función](#6-los-decoradores)
7. [La matriz se protege por ROL, no por permiso](#7-la-matriz-por-rol)
8. [Un formulario por rol](#8-un-formulario-por-rol)
9. [`MatrizPermisosView`: la vista completa](#9-la-vista)
10. [Las migraciones: esquema y datos, por separado](#10-las-migraciones)
11. [Dónde se ve](#11-dónde-se-ve)
12. [Archivos](#12-archivos)
13. [Pruebas](#13-pruebas)
14. [Explicación para la defensa](#14-explicación-para-la-defensa)
15. [Posibles preguntas del profesor](#15-posibles-preguntas-del-profesor)

---

## 1. Explicación inicial

Hasta esta historia, "quién puede hacer qué" estaba escrito directamente en cada
vista: `SoloAdministradorMixin`, `roles_permitidos = (RolCodigo.ADMINISTRADOR,)`,
comprobaciones de rol repartidas por `views.py` y `views_gestion.py`. Funcionaba,
pero tenía un costo fijo: cambiar quién puede validar una ficha o exportar un
reporte significaba editar Python, correr las pruebas y volver a desplegar. Para
una decisión que en la práctica es operativa —"este operativo necesita que el
supervisor también pueda crear censistas"— ese costo es desproporcionado.

Esta historia no agrega ninguna pantalla de negocio nueva. Agrega la **capa de
autorización** que las historias futuras (fichas, operativos, reportes) van a
consultar en vez de comprobar el rol a mano, y una pantalla —la matriz— para que
el administrador ajuste esa autorización sin que nadie edite código. Es, en ese
sentido, la historia menos visible y más estructural del proyecto: no se nota
usándola, se nota en que HU-05 a HU-20 no tuvieron que inventar su propio
mecanismo de control de acceso.

## 2. Decisiones de diseño

**Catálogo propio (`Permiso`) y no `django.contrib.auth.Permission`.** Django
genera automáticamente cuatro permisos por modelo —`add_x`, `change_x`,
`delete_x`, `view_x`—, y ese vocabulario describe operaciones sobre FILAS, no las
acciones del negocio. OPSO necesita expresar "validar una ficha levantada por un
censista" o "asignar censistas a un sector", que no es `change_ficha`: es una
acción funcional, a veces sobre la misma fila que otro rol también puede tocar
por un motivo distinto. Forzarlo en el esquema de Django habría exigido modelos
falsos solo para colgarles permisos. Los permisos de `auth` se conservan y
siguen gobernando `/admin/`; conviven con `usuarios.Permiso` porque gobiernan
cosas distintas.

**El rol ya era una tabla desde la HU-01** (`Rol`, con `codigo`, `activo`,
`dashboard_url_name`); esta historia no lo cambia, solo le agrega la relación
`permisos`. La ventaja de esa decisión anterior es justamente la que HU-04
explota: agregar el permiso "fichas.reabrir" es insertar una fila, no tocar el
modelo.

**Relación muchos-a-muchos sin modelo intermedio propio.** Se evaluó un
`RolPermiso` explícito con columnas `concedido_en`/`concedido_por`, y se
descartó: esa información ya la responde `RegistroAuditoria`, que además la
conserva incluso después de que el permiso se revoque. Una tabla intermedia solo
guarda el estado ACTUAL — si el permiso se quita, la fila y el dato de quién lo
concedió desaparecen juntos. Duplicarlo habría dado una respuesta peor y dos
fuentes que mantener coherentes.

**Principio de mínimo privilegio en el reparto inicial**, y una regla explícita:
la migración de datos **reproduce exactamente** el acceso que el sistema ya
tenía antes de esta historia, cuando estaba escrito a mano en cada vista. No es
casualidad ni conservadurismo: una migración que traslada dónde vive una regla
no debe, de paso, cambiar cuál es esa regla. Lo que cambia es que a partir de
aquí el reparto se ajusta desde la matriz.

## 3. El modelo

```python
class ModuloPermiso(models.TextChoices):
    USUARIOS, ROLES, AUDITORIA, FICHAS, OPERATIVOS, REPORTES = ...

class Permiso(models.Model):
    codigo = models.CharField(max_length=60, unique=True)   # "fichas.validar"
    nombre = models.CharField(max_length=120)                # "Validar o rechazar una ficha"
    modulo = models.CharField(choices=ModuloPermiso.choices)
    descripcion = models.TextField(blank=True)
    orden = models.PositiveSmallIntegerField(default=100)
    activo = models.BooleanField(default=True)
```

`modulo` solo AGRUPA la vista de la matriz — no es una entidad con datos propios,
por eso es un campo de opciones y no una tabla, a diferencia del rol. `orden`
existe para que cada módulo se lea de menos a más poder (ver, crear, editar,
borrar) y no alfabéticamente, que mezclaría "editar" antes que "crear". `activo`
permite retirar un permiso sin borrar las filas que documentan quién lo tenía:
`Usuario.tiene_permiso()` exige `activo=True` en el permiso además de en el rol.

`Rol` gana un campo:

```python
permisos = models.ManyToManyField(Permiso, related_name="roles", blank=True,
                                   db_table="usuarios_rol_permisos")

@property
def concede_todo(self):
    return self.codigo == RolCodigo.ADMINISTRADOR

def permisos_activos(self):
    return self.permisos.filter(activo=True)
```

`concede_todo` es la contraparte, en el modelo, de la regla 1 de
`Usuario.tiene_permiso()` (§4): el Administrador tiene todo por definición del
negocio, y la matriz lo consulta para pintar su columna marcada y NO editable —
dibujar casillas que un clic no cambia sería mentir sobre el efecto del clic.

## 4. `tiene_permiso()`

```python
def tiene_permiso(self, codigo):
    if self.es_administrador:
        return True
    if not self.rol_id or not self.rol.activo:
        return False
    return self.rol.permisos.filter(codigo=codigo, activo=True).exists()
```

Tres reglas, en este orden, y el orden importa:

1. **El Administrador (y el superusuario técnico) tienen todo concedido de forma
   implícita.** No es un atajo de conveniencia: es la MISMA regla que
   `RolRequeridoMixin` ya aplicaba con `permitir_administrador=True` desde la
   HU-01. Si aquí se decidiera lo contrario, el administrador podría quitarse a
   sí mismo el permiso que gobierna la propia matriz y dejar el sistema sin
   nadie capaz de repararlo desde la aplicación — el mismo bloqueo total
   ("lockout") que `es_ultimo_administrador_activo()` previene del lado de las
   cuentas.
2. **Sin rol, o con el rol desactivado, no hay ningún permiso.** Desactivar un
   rol corta el acceso de golpe, sin tener que recorrer sus filas de permisos
   una por una.
3. **En cualquier otro caso, se consulta la matriz**, exigiendo también
   `activo=True` en el propio permiso.

`tiene_algun_permiso(*codigos)` resuelve lo mismo con `__in` en una sola
consulta en vez de llamar a `tiene_permiso()` N veces — importa en una vista que
comprueba varios permisos para decidir qué botones dibujar. `codigos_permisos()`
devuelve un `set` (no un queryset) porque quien lo llama —típicamente una
plantilla— va a hacer varias comprobaciones de pertenencia seguidas, y resolverlas
en memoria con una sola consulta previa es más barato que repetir la consulta.

## 5. Dos mixins

```
RolRequeridoMixin      -> "¿QUIÉN eres?"          roles_permitidos = (...)
PermisoRequeridoMixin  -> "¿QUÉ puedes hacer?"    permisos_requeridos = (...)
```

`RolRequeridoMixin` ya existía desde el commit inicial (la HU-01 lo usa para los
paneles). Esta historia agrega `PermisoRequeridoMixin` al mismo archivo
(`usuarios/mixins.py`) y **ambos conviven a propósito** — no es una migración a
medias de uno al otro:

- Vistas cuyo acceso **no debe poder reconfigurarse** desde una pantalla siguen
  con `RolRequeridoMixin`: los paneles de cada rol, y la propia matriz de
  permisos (§7).
- Vistas cuyo reparto **es una decisión operativa** —administración de usuarios,
  y todo lo que agreguen las historias de fichas, operativos y reportes— pasan a
  `PermisoRequeridoMixin`. El ejemplo que esta misma historia migra es
  `ModuloUsuariosMixin` (`usuarios/views_gestion.py`): antes de la HU-04 exigía
  el rol Administrador; ahora exige el permiso que cada vista declara. El acceso
  resultante es IDÉNTICO gracias al reparto inicial (§10), pero pasa a ser
  configurable sin desplegar código.

Ambos mixins comparten el mismo comportamiento de rechazo
(`RechazoAmableMixin`): a un visitante anónimo se le pide iniciar sesión; a un
usuario autenticado sin autorización se le muestra un mensaje y se le redirige a
SU propio panel, con una salvaguarda contra un bucle infinito si su propio panel
fuera justo el que no puede ver.

Una vista que hereda de `PermisoRequeridoMixin` sin declarar
`permisos_requeridos` no queda abierta por omisión: `ImproperlyConfigured` se
lanza al primer uso, porque una vista sin permisos declarados es casi con
certeza un descuido del programador, y "seguro por defecto" también se aplica al
descuido.

## 6. Los decoradores

Para vistas basadas en función, `usuarios/decorators.py` ofrece el equivalente
exacto de cada mixin: `rol_requerido(*codigos)` / `solo_administrador` (ya
existían) y `permiso_requerido(*codigos, exigir_todos=False)`, nuevo en esta
historia. Mismo criterio, misma regla, mismo valor por defecto (`exigir_todos`
en `False`), para que las dos formas de escribir una vista se comporten igual.

**Detalle que vale la pena señalar tal como es:** hoy, `permiso_requerido()` no
tiene ningún llamador en el código de aplicación — solo lo usan sus propias
pruebas (`tests_permisos.py`, sección 5) y una vista de prueba declarada en el
propio archivo de tests. No es un error ni código muerto para borrar: todas las
vistas de HU-04 en adelante se escribieron como clases, así que el decorador
sigue siendo la pieza correcta el día que una vista de función necesite esta
regla, y mientras tanto está probado y disponible. Es la misma filosofía que ya
aplica el catálogo de permisos con los módulos `FICHAS`, `OPERATIVOS` y
`REPORTES` (§10): preparar la autorización antes de que exista la pantalla que
la va a usar no abre ningún hueco, porque sin una vista que lo compruebe, un
permiso no autoriza nada.

## 7. La matriz por rol

`MatrizPermisosView` (`/roles/permisos/`) usa `SoloAdministradorMixin` —es
decir, `RolRequeridoMixin`— y **no** `PermisoRequeridoMixin`, aunque esta misma
historia lo introduce. Es la regla de "la llave no se guarda dentro de la caja
que abre": si el acceso a la matriz dependiera de un permiso de la propia
matriz, un administrador podría revocárselo a su propio rol con un clic y nadie
podría volver a entrar a repararlo desde la aplicación — habría que intervenir
la base de datos a mano.

Esto tiene una consecuencia visible en el catálogo: existen los permisos
`roles.ver` y `roles.asignar_permisos` (§10), pero **ninguno de los dos gobierna
nada en el código** — ni protegen `MatrizPermisosView`, ni ningún otro lugar los
comprueba. Podría parecer un descuido; no lo es, y hay una prueba que lo deja
explícito, `MatrizAccesoTest.test_la_matriz_no_se_protege_con_un_permiso_del_catalogo`:
quitarle a un rol el permiso `roles.asignar_permisos` no cierra la matriz para el
administrador, porque su acceso depende del ROL, no de una casilla que él mismo
podría desmarcar. Los dos permisos están en el catálogo para que la matriz misma
pueda mostrar, en su propia tabla, "esto es lo que significaría delegar la
gestión de permisos" — documentación ejecutable de una capacidad que, a
propósito, no está conectada a ningún candado real.

## 8. Un formulario por rol

Se evaluaron dos formas de modelar la matriz (permisos × roles):

- **A)** Un formulario gigante con un campo booleano por celda: con 19 permisos
  y 3 roles editables serían decenas de campos generados a mano con nombres del
  tipo `permiso_7_rol_2`, y habría que parsearlos al guardar.
- **B)** Un formulario **por rol**, cada uno con un único
  `ModelMultipleChoiceField`.

Se eligió B. Django resuelve solo la validación de que los identificadores
enviados existan y sean permisos vigentes, y "los permisos de este rol" queda
expresado como lo que es: una lista. Cada `PermisosRolForm` lleva un **prefijo**
calculado a partir del rol (`rol{pk}`, nunca pasado a mano), así los campos de
Supervisor y Censista no chocan en el mismo POST.

Dos detalles de `guardar()` que no son obvios leyendo solo la firma:

- **Los permisos desactivados y ya concedidos se conservan.** La matriz solo
  muestra los permisos con `activo=True`; si uno se desactivó pero un rol lo
  tenía, no aparece como casilla y por tanto no llega en el POST. Guardar con un
  `set()` de solo lo marcado lo habría revocado en silencio, y al reactivarlo el
  rol lo habría perdido sin que nadie lo decidiera. `guardar()` los vuelve a
  añadir explícitamente antes de fijar la lista final.
- **El formulario no escribe en la bitácora.** No conoce al administrador que
  hace el cambio ni la petición HTTP; solo devuelve `(antes, después)` para que
  la vista arme el detalle de auditoría. Mezclar las dos responsabilidades
  habría hecho imposible probar el formulario aislado, que es justamente la
  ventaja de la opción B: `PermisosRolFormTest` lo prueba sin construir la
  matriz completa ni simular HTTP.

## 9. La vista

`MatrizPermisosView` es una `View` "cruda", no un `FormView`/`UpdateView`:
ninguna de esas clases modela lo que aquí ocurre —VARIOS formularios y ningún
objeto único que se esté editando—, y forzarlas habría obligado a sobrescribir
tanto método que no quedaría nada del comportamiento original.

- `obtener_permisos()` devuelve un **queryset** (no una lista): lo exige
  `ModelMultipleChoiceField.queryset`, y un queryset evaluado una sola vez se
  reparte en caché entre todos los formularios y la matriz, así que la consulta
  a PostgreSQL se hace una sola vez aunque la use N veces.
- `construir_matriz()` arma en Python la estructura que la plantilla recorre
  —módulo → fila de permiso → celda por rol—, porque el lenguaje de plantillas
  de Django no permite preguntas como "¿está el permiso 7 en la lista del rol
  2?" sin inventar un filtro propio.
- El `POST` valida TODOS los formularios antes de guardar nada: si alguno trae
  un identificador que no corresponde a un permiso vigente (una petición
  manipulada, porque la pantalla nunca produce eso), se rechaza el POST
  **completo** dentro de una única `transaction.atomic()`. Aplicar a medias un
  cambio de permisos dejaría el sistema en un estado que nadie decidió.
- Cada rol efectivamente modificado genera una fila de auditoría
  (`AccionAuditoria.CAMBIAR_PERMISOS`) con `describir_cambio_permisos()`, que
  arma un detalle legible ("concedidos: Validar fichas; revocados: Crear
  cuentas") a partir del nombre visible del permiso, no de su código interno.
  Guardar sin cambios reales no escribe nada: una bitácora llena de filas vacías
  esconde las que sí importan.

## 10. Las migraciones

**`0004_permisos.py` (esquema)**, generada con `makemigrations` y no escrita a
mano: crea `usuarios_permiso` y la tabla intermedia `usuarios_rol_permisos`, y
además agrega `rol_afectado`/`rol_afectado_nombre` a `RegistroAuditoria` —porque
a partir de esta historia una acción auditada puede recaer sobre un ROL y no
solo sobre una cuenta— y extiende el catálogo de acciones de la bitácora con
`CAMBIAR_PERMISOS`.

**`0005_permisos_iniciales.py` (datos)**, separada de la anterior por el mismo
criterio que ya estableció el par 0001/0002: esquema y datos no se mezclan. Dos
decisiones documentadas en su propio docstring:

- **De dónde salen los 19 permisos del catálogo inicial:** de los módulos ya
  implementados (usuarios, auditoría, roles) —cuyas acciones son exactamente las
  rutas que ya protegía `SoloAdministradorMixin`— y de las descripciones de rol
  ya sembradas en `0002_roles_iniciales`, que ya nombraban el trabajo de terreno
  ("valida las fichas levantadas por los censistas", "asigna sectores"). Por eso
  el catálogo incluye permisos de módulos sin pantalla todavía (`fichas`,
  `operativos`, `reportes`): cuando esas historias se implementaron, la
  autorización ya estaba modelada y solo hubo que consultarla.
- **El reparto inicial aplica mínimo privilegio** y reproduce EXACTAMENTE el
  acceso anterior a esta historia: Administrador recibe todos (coherente con el
  bypass de `tiene_permiso()`, y sembrado para que la matriz muestre la verdad
  en vez de una fila vacía engañosa); Supervisor recibe ver/validar/reportar
  pero ni gestión de usuarios ni permisos; Censista, solo sus propias fichas.

## 11. Dónde se ve

Una tarjeta **"Roles y permisos"** en `templates/dashboards/administrador.html`,
con un botón "Ver matriz de permisos" hacia `/roles/permisos/`. No hay un
enlace en el menú superior (`base.html`): a diferencia de "Operativos" o
"Revisión", el acceso a esta pantalla no se decide por permiso (§7), así que no
sigue el patrón `{% if user|tiene_permiso:... %}` que ya usan esos otros
enlaces — vive únicamente en el panel del administrador, coherente con que solo
él puede entrar.

**Detalle que solo se ve mirando el historial de git y no el código de esta
historia:** el filtro de plantilla `{% load permisos %}` /
`{{ user|tiene_permiso:"..." }}` (`usuarios/templatetags/permisos.py`), que hoy
es lo que oculta o muestra "Operativos", "Mis encuestas", "Revisión" e
"Indicadores" en el menú superior, **no nació con esta historia**: el archivo se
agregó en el commit de la HU-05, cuando "Operativos" fue el primer enlace del
menú que necesitó ocultarse según un permiso de la matriz en vez de según el
rol. HU-04 construyó el modelo y la matriz; HU-05 construyó el primer consumidor
visible de ese modelo en una plantilla compartida por todo el sistema. Ninguna
de las dos historias funciona sin la otra, y por eso vale la pena decirlo aquí en
vez de dejar que parezca que todo llegó junto.

## 12. Archivos

```
usuarios/models.py
    + ModuloPermiso, Permiso
    Rol
    + permisos (ManyToManyField), concede_todo, permisos_activos()
    Usuario
    + tiene_permiso(), tiene_algun_permiso(), codigos_permisos()

usuarios/mixins.py
    + PermisoRequeridoMixin
    (RolRequeridoMixin y RechazoAmableMixin ya existían)

usuarios/decorators.py
    + permiso_requerido()
    (rol_requerido() y solo_administrador ya existían)

usuarios/views_permisos.py       (nuevo)   MatrizPermisosView
usuarios/forms_permisos.py       (nuevo)   PermisosRolForm
usuarios/templatetags/permisos.py          (no existe todavía: llega con la HU-05)

usuarios/views_gestion.py
    + ModuloUsuariosMixin (reemplaza el control por rol de SoloAdministradorMixin
      en las vistas de administración de usuarios; SoloAdministradorMixin se
      conserva para lo que no debe reconfigurarse, como la propia matriz)

usuarios/auditoria.py
    + describir_cambio_permisos()

usuarios/urls.py
    + roles/permisos/ -> usuarios:permisos

usuarios/migrations/0004_permisos.py             (esquema)
usuarios/migrations/0005_permisos_iniciales.py   (datos: catálogo + reparto inicial)

templates/usuarios/gestion/permisos_matriz.html  (nuevo)
templates/dashboards/administrador.html
    + tarjeta «Roles y permisos»

usuarios/tests_permisos.py       (nuevo)   132 pruebas
```

## 13. Pruebas

`usuarios/tests_permisos.py`, 132 pruebas en 11 secciones (más el URLconf de
prueba que usan las de mixins y decoradores):

| Sección / clase | Qué comprueba |
|---|---|
| `PermisoModeloTest` | el catálogo, sus restricciones y `etiqueta_modulo` |
| `RolPermisosTest` | la relación `Rol.permisos`, `concede_todo`, `permisos_activos()` |
| `UsuarioTienePermisoTest` | las tres reglas de `tiene_permiso()`: administrador implícito, rol inactivo, consulta a la matriz; `tiene_algun_permiso()`; `codigos_permisos()` |
| `PermisoRequeridoMixinTest` | el mixin exige el permiso declarado, `ImproperlyConfigured` sin declarar ninguno, `exigir_todos` |
| `PermisoRequeridoDecoradorTest` | el equivalente para vistas de función, mismo criterio que el mixin |
| `MatrizAccesoTest` | solo el Administrador entra; el Supervisor no puede ni ver ni guardar (el POST también se rechaza, no solo se esconde el botón); un visitante anónimo va al login; el superusuario técnico entra; **la matriz no se protege con un permiso del propio catálogo** (§7); el POST exige CSRF |
| `MatrizGetTest` | qué dibuja la pantalla: módulos, filas, celdas, columna del Administrador no editable |
| `MatrizPostTest` | guardar concede y revoca correctamente; un rol sin cambios no genera auditoría; un permiso inexistente rechaza el POST completo (transacción atómica); permisos desactivados y ya concedidos sobreviven a un guardado |
| `PermisosRolFormTest` | el formulario aislado, sin construir la matriz ni simular HTTP |
| `AuditoriaRolTest` | `describir_cambio_permisos()` y la fila de `RegistroAuditoria` con `rol_afectado` |
| `IntegracionPermisosTest` | un permiso concedido a otro rol desde la matriz cambia el acceso real de ese rol, sin ningún cambio de código |
| `ModuloUsuariosPermisosTest` | la administración de usuarios migró de rol a permiso sin cambiar quién puede entrar hoy, y sí cambia si la matriz se lo concede a otro rol |

## 14. Explicación para la defensa

**En una frase:** esta historia no agrega una pantalla de negocio, agrega la capa
de autorización que todas las historias posteriores consultan, y una pantalla
para ajustarla sin tocar código — con la única excepción, deliberada, de la
pantalla que ajusta esa misma capa.

**Lo que conviene poder defender:**

1. **Catálogo propio, no `django.contrib.auth.Permission`.** El vocabulario de
   Django describe filas de una tabla; OPSO necesita describir acciones del
   negocio, y a veces varias acciones distintas sobre la misma tabla.
2. **Dos mixins, dos preguntas, y los dos siguen vivos.** `RolRequeridoMixin`
   para lo que no debe poder reconfigurarse (los paneles, y la propia matriz);
   `PermisoRequeridoMixin` para lo que sí es una decisión operativa. No es una
   migración a medias: es una distinción permanente, con un ejemplo de cada uno
   dentro del propio proyecto.
3. **La llave no vive dentro de la caja que abre.** La matriz se protege por rol
   para que un administrador nunca pueda quedarse fuera del único lugar que
   podría repararlo. `roles.ver`/`roles.asignar_permisos` existen en el catálogo
   sin gobernar nada, y hay una prueba que demuestra exactamente eso a
   propósito.
4. **La migración de datos reproduce el acceso anterior, no lo cambia.**
   Trasladar dónde vive una regla y cambiar cuál es la regla son dos
   operaciones distintas, y mezclarlas en una sola migración habría hecho
   imposible saber, más adelante, cuál de las dos pasó.
5. **Un formulario por rol, no un campo por celda.** La opción que delega la
   validación en Django y permite probar el formulario sin la matriz completa.

## 15. Posibles preguntas del profesor

**¿Por qué la matriz no se protege con `PermisoRequeridoMixin`, si es lo que
esta misma historia introduce?**
Porque sería guardar la llave dentro de la caja que abre: un administrador
podría revocarse a sí mismo el acceso a la única pantalla capaz de restaurarlo,
sin poder arreglarlo después desde la aplicación. Por eso conserva
`RolRequeridoMixin`, y por eso existe una prueba
(`test_la_matriz_no_se_protege_con_un_permiso_del_catalogo`) que verifica que
quitarle `roles.asignar_permisos` al rol Administrador no le cierra la puerta.

**Si `roles.ver` y `roles.asignar_permisos` no protegen nada, ¿para qué están en
el catálogo?**
Para que la matriz pueda mostrarse a sí misma en su propia tabla —"esto es lo
que significaría delegar la gestión de permisos"— sin mentir sobre lo que el
Administrador puede hacer. Un permiso sin una vista que lo compruebe no abre
ningún hueco de seguridad: es documentación ejecutable, no una puerta.

**¿Por qué la migración de datos reproduce exactamente el acceso anterior en vez
de aprovechar para "mejorar" el reparto?**
Porque son dos cambios distintos y mezclarlos habría sido irresponsable: una
migración que traslada dónde vive una regla de negocio no debe, de paso, decidir
una regla distinta sin que nadie lo pida explícitamente. Ajustar el reparto es
exactamente para lo que sirve la matriz, después de que existe.

**¿Por qué el catálogo incluye permisos de módulos que todavía no tenían
pantalla (`fichas`, `operativos`, `reportes`)?**
Porque esos permisos salen de las descripciones de rol que ya existían desde la
HU-02 ("valida las fichas levantadas por los censistas"), y modelar la
autorización antes de que exista la pantalla significa que, cuando esa historia
se implemente, solo hay que consultarla — no hay que decidir de nuevo quién
puede hacer qué. Un permiso sin vista que lo compruebe no concede nada por sí
solo.

**¿Por qué un formulario por rol y no un solo formulario con una casilla por
celda?**
Porque con 19 permisos y 3 roles serían decenas de campos generados a mano con
nombres artificiales (`permiso_7_rol_2`), y habría que parsearlos al guardar. Un
`ModelMultipleChoiceField` por rol deja que Django valide solo que los
identificadores enviados sean permisos vigentes, y el formulario se prueba
aislado.

**¿Por qué el filtro de plantilla `tiene_permiso` no está en los archivos de
esta historia?**
Porque no hacía falta todavía: HU-04 protege vistas (donde `Usuario.tiene_permiso()`
se llama directamente) y una única pantalla propia. El primer lugar que
necesitó ocultar un enlace del MENÚ según un permiso fue "Operativos", en la
HU-05, y ahí se escribió el filtro — reutilizando `tiene_permiso()`/`tiene_algun_permiso()`
del modelo, sin reimplementar ninguna regla.
