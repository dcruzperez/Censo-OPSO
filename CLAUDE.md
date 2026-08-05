# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

El código, los comentarios, los docstrings, los nombres de modelos/campos/URLs y la
documentación están **en español**. Mantener esa convención: `Usuario`, `nombre_usuario`,
`registrar_accion()`, `roles_permitidos`, `/recuperar-contrasena/`. Los docstrings explican
el *por qué* de cada decisión porque el repositorio es la defensa de un proyecto de título.

## Comandos

El proyecto Django vive en `backend/`. El entorno virtual está en la raíz (`.venv/`), un
nivel arriba, y **no** se activa: se invoca el intérprete por ruta explícita.

```bash
cd backend

# Servidor de desarrollo (requiere PostgreSQL levantado y .env configurado)
../.venv/Scripts/python.exe manage.py runserver

# Batería completa: 1.319 pruebas, ~52 s
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test

# Un archivo, una clase, una prueba
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test usuarios.tests_gestion
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test usuarios.tests.BloqueoFuerzaBrutaTest
DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test usuarios.tests_gestion.CrearUsuarioTest.test_crea_usuario_valido

# Migraciones y auditoría de despliegue
../.venv/Scripts/python.exe manage.py makemigrations usuarios
../.venv/Scripts/python.exe manage.py showmigrations
../.venv/Scripts/python.exe manage.py check --deploy
```

`DB_ENGINE=sqlite3` es obligatorio para correr pruebas sin un servidor PostgreSQL: sin esa
variable, `config/settings.py` lanza `ImproperlyConfigured` al arrancar si `DB_PASSWORD`
está vacía o conserva el texto de plantilla. Desarrollo y producción usan **siempre**
PostgreSQL; SQLite es solo contingencia para las pruebas.

Puesta en marcha desde cero: `scripts/preparar_base_datos.py --migrar` crea el rol
`opso_user` y la base `opso_db`, genera una contraseña aleatoria, la escribe en
`backend/.env`, aplica migraciones y crea los usuarios de demostración. Es idempotente.

No hay linter ni formateador configurado. No hay `pytest`: el corredor es el de Django.

## Arquitectura

Django 6 · PostgreSQL · Bootstrap 5 servido localmente (`static/vendor/`, funciona sin
internet). Cuatro apps:

| App | Dominio | HU |
|---|---|---|
| `usuarios` | autenticación, roles, permisos, gestión de cuentas, auditoría | HU-01 a HU-04 |
| `dashboards` | paneles diferenciados por rol | transversal |
| `operativos` | operativos, organización territorial, asignación de sectores | HU-05, HU-06 |
| `fichas` | encuestas: vivienda, grupo familiar, integrantes, borrador y cierre, GPS, fotografías, revisión del supervisor | HU-07 a HU-15 |

Sin API REST ni JavaScript de aplicación: son vistas renderizadas en servidor con plantillas.

### El rol es una tabla, no un campo de texto

`Rol` es un modelo con `codigo` (validado por `CheckConstraint` contra `RolCodigo`),
`activo` y **`dashboard_url_name`**. La relación rol→panel está *guardada en la base de
datos*, así que `Usuario.get_dashboard_url()` la resuelve con `reverse()` en vez de un
`if/elif`. Consecuencia práctica: agregar un rol es insertar una fila (ver
`migrations/0002_roles_iniciales.py`), no editar Python. `Usuario.rol` usa `PROTECT`.

### Cerrado por defecto

`LoginRequiredMiddleware` (Django 5.1+) está en `MIDDLEWARE`: **toda vista nueva exige
sesión automáticamente**. Una vista pública es la excepción y debe marcarse explícitamente
con `@method_decorator(login_not_required, name="dispatch")` — así lo hacen
`LoginOPSOView` y `LogoutOPSOView`. Nunca se quita ese middleware para "arreglar" un 302.

Sobre eso, la autorización por rol tiene dos caminos equivalentes, según el tipo de vista:

- **CBV** → `RolRequeridoMixin` (`usuarios/mixins.py`), declarando `roles_permitidos`.
  Redirige al panel propio con un mensaje en vez de responder 403 seco, y tiene
  salvaguarda contra bucle de redirecciones.
- **FBV** → `@rol_requerido(...)` / `@solo_administrador` (`usuarios/decorators.py`).

Ambos aceptan al administrador por defecto (`permitir_administrador = True`) y delegan la
regla real en `Usuario.tiene_rol()`, que además exige `rol.activo`. La lógica de permisos
vive en el modelo (*fat model, thin view*), igual que las consultas reutilizables, que
viven en `UsuarioManager` (`administradores_activos()`, `buscar()`, `activos_con_rol()`).

### Dos bitácoras distintas, a propósito

| Modelo | Pregunta que responde | Se escribe desde |
|---|---|---|
| `IntentoAcceso` | ¿quién entró al sistema? | señales de `django.contrib.auth` → `seguridad.registrar_intento()` |
| `RegistroAuditoria` | ¿quién modificó a quién? | vistas de gestión → `auditoria.registrar_accion()` |

`IntentoAcceso` es además defensa activa: `seguridad.esta_bloqueado()` cuenta los fallos
recientes del correo para frenar fuerza bruta, y reinicia el conteo tras un ingreso
exitoso. Nunca se guarda la contraseña probada.

`RegistroAuditoria` **desnormaliza los correos a propósito** (`administrador_email`,
`usuario_afectado_email`) porque las FK son `SET_NULL`: si una cuenta se elimina, la fila
sigue siendo legible. Es de solo escritura: no hay vistas de edición ni borrado, y está
bloqueada en el admin. `auditoria.describir_cambios(form)` arma el detalle desde
`form.changed_data` traduciendo valores internos a etiquetas legibles.

### Lógica fuera de las vistas

`usuarios/seguridad.py` y `usuarios/auditoria.py` son módulos de funciones puras (reciben
`request` opcional, no dependen de él). Se prueban sin simular HTTP y se reutilizan desde
formularios, señales, middleware y comandos. Al agregar lógica de seguridad o auditoría va
ahí, no dentro de la vista.

Los eventos de login se capturan con **señales** (`usuarios/signals.py`), no con código
dentro de `LoginOPSOView`: la auditoría sigue funcionando si mañana entra otra vía de
autenticación.

### Detalles que sorprenden si no se leen

- **El control de frecuencia vive en la caché, no en PostgreSQL** (`seguridad.py`). Usa
  `cache.add()` para que la ventana sea fija desde la *primera* solicitud. `LocMemCache` no
  se comparte entre procesos: en producción con varios workers hay que pasar a Redis.
- **Las cuentas nuevas reciben una contraseña aleatoria de 50 caracteres**, no
  `set_unusable_password()`, porque `PasswordResetForm.get_users()` descarta las cuentas sin
  contraseña utilizable y el enlace de invitación nunca se enviaría.
- **La invitación reutiliza la maquinaria de recuperación** (`default_token_generator` y
  `usuarios:password_reset_confirm`); lo único propio es el texto del correo. No escribir
  criptografía nueva.
- **`Usuario.es_ultimo_administrador_activo()`** impide deshabilitar o degradar la última
  cuenta administradora: evita que el sistema quede cerrado por dentro. El superusuario
  técnico cuenta como administrador aunque no tenga fila de rol, y esa regla está duplicada
  a propósito en `es_administrador` y en `administradores_activos()` — si se cambia una, hay
  que cambiar la otra.
- **`Usuario.save()` normaliza** correo (minúsculas), RUT y `nombre_usuario` antes de
  escribir. No normalizar a mano en las vistas.
- **`SECURE_SSL_REDIRECT` se controla por variable de entorno y no por `DEBUG`**, porque el
  corredor de pruebas fuerza `DEBUG=False` y toda petición respondería una redirección.
- **En desarrollo el correo se imprime en la terminal de `runserver`**
  (`console.EmailBackend`), con el enlace listo para copiar. Las pruebas usan `locmem`.
- Login siempre con **correo** (`USERNAME_FIELD = "email"`, `username = None`);
  `nombre_usuario` es solo etiqueta corta para listados.
- **`MEDIA_ROOT` no se sirve como archivos estáticos, en ningún entorno.** Las fotografías de
  las viviendas se entregan por `fichas.views.ServirFotografiaView`, que comprueba quién
  pregunta. El atajo habitual (`static(settings.MEDIA_URL, document_root=...)` en `urls.py`, o
  un `location /media/` en Nginx) publicaría fotos de casas de familias reales sin sesión ni
  permiso. `MEDIA_URL` existe solo porque Django lo pide.

### Documentación y pruebas por historia de usuario

Cada HU tiene su documento en `backend/docs/HU-0N_*.md` y las pruebas se reparten por tema:

| Archivo | Cubre |
|---|---|
| `usuarios/tests.py` | HU-01, HU-02 (80) |
| `usuarios/tests_gestion.py` | HU-03 (69) |
| `usuarios/tests_permisos.py` | HU-04 (matriz de permisos) |
| `operativos/tests.py` | HU-05 (territorio) |
| `operativos/tests_asignaciones.py` | HU-06 (asignación de sectores) |
| `fichas/tests.py` | HU-07 a HU-15 (7.923 líneas, 73 secciones numeradas y rotuladas por HU) |

`docs/HU-04_*.md` **falta**: HU-04 se integró sin su documento. Escribirlo es deuda
pendiente, no un precedente a imitar. Las pruebas se agrupan en clases por preocupación
(`BloqueoFuerzaBrutaTest`, `UltimoAdministradorTest`, `ProteccionCSRFTest`…) sobre una clase
base compartida que crea roles y usuarios (`BaseAutenticacionTest`, `BaseGestionTest`), y
usan `@override_settings` para fijar los umbrales en vez de depender del `.env`.

## Estado del historial

**`main` contiene HU-01 a HU-15 completas** (1.319 pruebas verdes), en un historial lineal con
un commit por historia de usuario y sin commits de merge. Sincronizada con
`origin/main` (`github.com/dcruzperez/Censo-OPSO`) al 2026-08-05. No queda trabajo terminado
fuera de `main`: todas las ramas de desarrollo se integraron y se borraron.

Dos cosas que conviene saber al leer `git log`, porque no se deducen de él:

1. **Los nueve commits de HU-07 a HU-15 se obtuvieron partiendo un commit monolítico.** El
   original era `ac7a984` ("Proyecto Censo OPSO"), que agrupaba las nueve historias con un
   mensaje que no las nombraba. Se repartió por HU usando las banderas de sección del propio
   código (`# HU-08 — …`) y las migraciones como referencia, verificando que el árbol final
   quedara idéntico byte a byte al original.
2. **Solo `da45051` (HU-15) está verde entre esos nueve.** Los ocho anteriores no corren por
   sí solos, porque las HU posteriores *reestructuraron* a las anteriores en vez de solo
   agregarles cosas: en HU-07 la encuesta colgaba de la zona y llevaba la dirección, y HU-08
   interpuso `Vivienda` (lo explica la cabecera de `fichas/models.py`). El estado "solo
   HU-07" nunca existió, así que esos commits reparten los artefactos por historia pero no
   reconstruyen estados ejecutables intermedios. Además `config/settings.py` y
   `dashboards/views.py` entran enteros en HU-07 aunque contengan bloques de HU-12 y HU-13, y
   los dos `README.md` entran en HU-15 porque describen el estado final.

Consecuencia práctica: **no usar `git bisect` ni `git checkout` de un commit intermedio entre
`37c78ad` (HU-07) y `1850da7` (HU-14) esperando un árbol ejecutable.** Para bisecar, `098af4d`
(HU-06) y `da45051` (HU-15) sí son puntos válidos.

## Convenciones al agregar una historia de usuario nueva

**Ramas: una por HU**, nombrada `hu-N-<tema-en-kebab-case>` (ej.: `hu-16-informes-por-comuna`),
y **un commit por HU**. El historial pasado tiene dos infracciones ya corregidas que no se
deben imitar: la rama `hu-04-05-permisos-y-territorio` agrupaba dos historias, y `ac7a984`
agrupaba nueve en un solo commit.

**No se mergea a `main` sin pruebas verdes.** La batería completa debe pasar entera —hoy son
1.319 pruebas, y la rama debe sumar las suyas, no solo no romper las anteriores:

```bash
cd backend && DB_ENGINE=sqlite3 ../.venv/Scripts/python.exe manage.py test
```

**¿App nueva o archivos en `usuarios`?** Decide el dominio de los modelos:

- **Modelos de un dominio propio → app nueva.** Zonas, sectores y operativos son entidades
  del territorio, no del acceso al sistema: por eso viven en la app `operativos`.
- **Extender acceso, permisos o gestión de cuentas → archivos `*_<tema>.py` dentro de
  `usuarios`.** Es el caso de `views_permisos.py`, `forms_permisos.py` y
  `templatetags/permisos.py`: son vistas y formularios sobre el dominio que `usuarios` ya
  posee. `views.py`/`forms.py` se mantienen para HU-01 y HU-02; no se engordan.

**Un archivo de pruebas por tema, no por HU**, cuando varias historias comparten dominio:
`fichas/tests.py` cubre las nueve HU de las encuestas en un solo archivo, con secciones
numeradas y rotuladas (`# HU-11 — 45. LA UBICACIÓN EN EL MODELO`). Esas banderas no son
decoración: son lo que permitió partir el commit monolítico por historia, así que **al
agregar pruebas hay que rotular la sección con su HU**. Dentro de cada sección, una clase por
preocupación sobre una clase base compartida, y `@override_settings` para fijar umbrales en
vez de leerlos del `.env`.

**`backend/docs/HU-0N_*.md` es obligatorio antes de cerrar la HU**, no después. El documento
explica las decisiones de diseño y sus alternativas descartadas: es material de defensa ante
el profesor corrector, y escribirlo con el código fresco es lo que hace que los docstrings
del repositorio y la documentación digan lo mismo.

Antes de mergear, además, `manage.py makemigrations --check --dry-run` debe responder
"No changes detected": ningún cambio de modelo sin su migración.

Sobre `manage.py check --deploy`: con el `.env` de desarrollo devuelve **5 warnings
esperados** (`W004`, `W008`, `W012`, `W016`, `W018`), todos consecuencia de `DEBUG=True` y de
las cookies sin HTTPS en local. No hay que "arreglarlos" tocando `settings.py` —ya están
controlados por variable de entorno y desaparecen en producción—. Lo que importa es que no
aparezca un **sexto** hallazgo.

## Cuentas de demostración

`admin@opso.cl` · `supervisor@opso.cl` · `censista@opso.cl`, todas con `Censo2026#Opso`
(las crea `manage.py crear_usuarios_demo`, que corre dentro de `preparar_base_datos.py --migrar`).
