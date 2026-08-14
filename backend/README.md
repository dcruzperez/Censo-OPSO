# OPSO — Backend (Django)

Sistema web para digitalizar el levantamiento de información de familias.
Proyecto de título · Ingeniería en Computación e Informática.

**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3

---

## Estado actual

| Historia de usuario | Estado | Documentación |
|---|---|---|
| HU-01 · Inicio de sesión seguro con control de acceso por rol | ✅ Implementada | [`docs/HU-01_inicio_de_sesion.md`](docs/HU-01_inicio_de_sesion.md) |
| HU-02 · Recuperación de contraseña por correo electrónico | ✅ Implementada | [`docs/HU-02_recuperacion_contrasena.md`](docs/HU-02_recuperacion_contrasena.md) |
| HU-03 · Administración de usuarios (crear, editar, deshabilitar) | ✅ Implementada | [`docs/HU-03_administracion_usuarios.md`](docs/HU-03_administracion_usuarios.md) |
| HU-04 · Asignar roles y permisos (matriz configurable) | ✅ Implementada | — |
| HU-05 · Comunas, sectores y zonas (organización territorial) | ✅ Implementada | [`docs/HU-05_organizacion_territorial.md`](docs/HU-05_organizacion_territorial.md) |
| HU-06 · Asignación de sectores a los encuestadores | ✅ Implementada | [`docs/HU-06_asignacion_de_sectores.md`](docs/HU-06_asignacion_de_sectores.md) |
| HU-07 · Encuestas asignadas y su estado (encuestador) | ✅ Implementada | [`docs/HU-07_encuestas_asignadas.md`](docs/HU-07_encuestas_asignadas.md) |
| HU-08 · Registro de vivienda y grupo familiar | ✅ Implementada | [`docs/HU-08_registro_vivienda_grupo_familiar.md`](docs/HU-08_registro_vivienda_grupo_familiar.md) |
| HU-09 · Registro de los integrantes del hogar | ✅ Implementada | [`docs/HU-09_integrantes_del_hogar.md`](docs/HU-09_integrantes_del_hogar.md) |
| HU-10 · Borradores y cierre de la encuesta | ✅ Implementada | [`docs/HU-10_borradores_y_cierre.md`](docs/HU-10_borradores_y_cierre.md) |
| HU-11 · Captura de la ubicación GPS | ✅ Implementada | [`docs/HU-11_ubicacion_gps.md`](docs/HU-11_ubicacion_gps.md) |
| HU-12 · Fotografías de la vivienda | ✅ Implementada | [`docs/HU-12_fotografias.md`](docs/HU-12_fotografias.md) |
| HU-13 · Revisión de las encuestas recibidas | ✅ Implementada | [`docs/HU-13_revision_de_encuestas.md`](docs/HU-13_revision_de_encuestas.md) |
| HU-14 · Aprobar o anular encuestas | ✅ Implementada | [`docs/HU-14_aprobar_o_anular.md`](docs/HU-14_aprobar_o_anular.md) |
| HU-15 · Devolver encuestas con observaciones | ✅ Implementada | [`docs/HU-15_devolver_con_observaciones.md`](docs/HU-15_devolver_con_observaciones.md) |
| HU-16 · Alertas de registros incompletos | ✅ Implementada | [`docs/HU-16_alertas_de_registros_incompletos.md`](docs/HU-16_alertas_de_registros_incompletos.md) |
| HU-17 · Editar registros permitidos (corregir errores detectados) | ✅ Resuelta sin código nuevo — reutiliza el flujo de devolución de la HU-15 | [`docs/HU-17_editar_registros_permitidos.md`](docs/HU-17_editar_registros_permitidos.md) |

**1.338 pruebas automáticas** en total (`python manage.py test` → OK). La HU-17 no
agregó pruebas propias: no tiene comportamiento nuevo que probar.

---

## Puesta en marcha

### 1. Entorno virtual y dependencias

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Configuración

```bash
cd backend
copy .env.example .env
```

Genera una clave secreta y pégala en `DJANGO_SECRET_KEY` dentro de `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

> `.env` contiene credenciales reales y **no debe versionarse**.
> `.env.example` es la plantilla que sí se versiona.

### 3. Base de datos PostgreSQL (una sola vez)

```bash
python scripts\preparar_base_datos.py --migrar
```

El script pide la contraseña del usuario `postgres` (no se muestra ni se
guarda en ningún archivo) y luego, por sí solo:

- consulta la configuración real del servidor y elige la codificación y el
  ordenamiento que ese servidor acepta,
- crea el rol `opso_user` con privilegios acotados,
- crea la base `opso_db` en UTF-8,
- otorga los permisos sobre el esquema `public` (necesario desde PostgreSQL 15),
- genera una contraseña aleatoria fuerte y la escribe en `DB_PASSWORD` del `.env`,
- aplica las migraciones y crea los usuarios de demostración (por `--migrar`).

Se puede volver a ejecutar sin romper nada: detecta lo que ya existe.

> Alternativa manual con SQL: [`scripts/crear_base_datos.sql`](scripts/crear_base_datos.sql)

### 4. Superusuario y servidor

```bash
python manage.py createsuperuser        # acceso a /admin/
python manage.py runserver
```

→ http://127.0.0.1:8000/login/

---

## Cuentas de demostración

| Rol | Correo | Usuario | Contraseña | Destino |
|---|---|---|---|---|
| Administrador | `admin@opso.cl` | `arojas` | `Censo2026#Opso` | `/dashboard/admin/` |
| Supervisor | `supervisor@opso.cl` | `lperez` | `Censo2026#Opso` | `/dashboard/supervisor/` |
| Censista | `censista@opso.cl` | `msoto` | `Censo2026#Opso` | `/dashboard/censista/` |

El inicio de sesión es siempre con el **correo**; el nombre de usuario es solo
una etiqueta corta para listados.

---

## Rutas

| Ruta | Descripción | Acceso |
|---|---|---|
| `/` | Redirige al panel del rol | Requiere sesión |
| `/login/` | Inicio de sesión | Público |
| `/logout/` | Cierre de sesión (solo POST) | Público |
| `/recuperar-contrasena/` | Solicitar enlace de recuperación | Público |
| `/recuperar-contrasena/enviado/` | Confirmación neutra del envío | Público |
| `/restablecer/<uid>/<token>/` | Definir la contraseña nueva | Público (con token válido) |
| `/restablecer/completado/` | Aviso de éxito | Público |
| `/sin-rol/` | Aviso: cuenta sin rol asignado | Requiere sesión |
| `/dashboard/` | Despachador según rol | Requiere sesión |
| `/dashboard/admin/` | Panel del Administrador | Rol Administrador |
| `/dashboard/supervisor/` | Panel del Supervisor | Rol Supervisor (o Administrador) |
| `/dashboard/censista/` | Panel del Censista | Rol Censista (o Administrador) |
| `/usuarios/` | Listado de usuarios (buscar, filtrar, paginar) | Rol Administrador |
| `/usuarios/nuevo/` | Crear usuario | Rol Administrador |
| `/usuarios/<pk>/` | Ficha del usuario con su historial | Rol Administrador |
| `/usuarios/<pk>/editar/` | Editar datos, rol y estado | Rol Administrador |
| `/usuarios/<pk>/deshabilitar/` | Confirmar (GET) y deshabilitar (POST) | Rol Administrador |
| `/usuarios/<pk>/habilitar/` | Confirmar (GET) y habilitar (POST) | Rol Administrador |
| `/usuarios/<pk>/enviar-enlace/` | Reenviar enlace de contraseña (solo POST) | Rol Administrador |
| `/usuarios/auditoria/` | Bitácora de acciones administrativas | Rol Administrador |
| `/operativos/` | Operativos, comunas, sectores y zonas | `operativos.ver` |
| `/operativos/<pk>/asignaciones/` | Reparto de sectores del operativo | `operativos.ver` |
| `/operativos/mis-sectores/` | El territorio propio del encuestador | Requiere sesión |
| `/encuestas/` | Las encuestas propias y su estado | `fichas.ver_propias` |
| `/encuestas/<pk>/` | Ficha de una encuesta | `fichas.ver_propias` (la propia) o `fichas.ver_todas` |
| `/encuestas/<pk>/hogar/` | Registrar o editar el grupo familiar | `fichas.crear` o `fichas.editar` |
| `/encuestas/viviendas/nueva/` | Registrar una vivienda | `fichas.crear` o `fichas.editar` |
| `/encuestas/viviendas/<pk>/` | Ficha de la vivienda y sus hogares | `fichas.ver_propias` o `fichas.ver_todas` |
| `/encuestas/viviendas/<pk>/editar/` | Corregir o completar la vivienda | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/integrantes/` | Personas del hogar y su avance | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/integrantes/nuevo/` | Agregar una persona al hogar | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/integrantes/<id>/editar/` | Corregir sus datos | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/integrantes/<id>/quitar/` | Confirmar (GET) y quitar (POST) | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/borrador/` | Nota de avance y próxima visita | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/completar/` | Qué falta y envío a revisión | `fichas.crear` o `fichas.editar` |
| `/encuestas/<pk>/cerrar/` | Cerrar sin levantar, con motivo | `fichas.crear` o `fichas.editar` |
| `/encuestas/viviendas/<pk>/ubicacion/` | Capturar el punto GPS de la vivienda | `fichas.crear` o `fichas.editar` |
| `/encuestas/viviendas/<pk>/fotografias/nueva/` | Adjuntar una fotografía | `fichas.crear` o `fichas.editar` |
| `/encuestas/fotografias/<pk>/ver/` | Entregar el archivo, con control de acceso | `fichas.ver_propias` o `fichas.ver_todas` |
| `/encuestas/fotografias/<pk>/quitar/` | Confirmar (GET) y borrar (POST) | `fichas.crear` o `fichas.editar` |
| `/encuestas/revision/` | Bandeja de encuestas recibidas | `fichas.ver_todas` |
| `/encuestas/<pk>/revisar/` | La encuesta completa, para revisarla | `fichas.ver_todas` |
| `/encuestas/<pk>/validar/` | Confirmar (GET) y aprobar (POST) | `fichas.validar` |
| `/encuestas/<pk>/anular/` | Formulario (GET) y anular (POST) | `fichas.validar` |
| `/admin/` | Administración de Django | `is_staff` |

---

## Correo electrónico

En desarrollo no hay que configurar nada: el backend por defecto es
`console.EmailBackend`, que **imprime el correo completo en la terminal donde
corre `runserver`**, con el enlace de recuperación listo para copiar. No
requiere cuenta de correo ni conexión a internet.

Para enviar correos reales, completar en `.env`:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST_USER=tu-cuenta@gmail.com
EMAIL_HOST_PASSWORD=contraseña-de-aplicacion-de-16-caracteres
```

> Con Gmail hay que usar una **contraseña de aplicación**
> (https://myaccount.google.com/apppasswords), no la contraseña personal.

---

## Pruebas

```bash
python manage.py test                                 # 1.338 pruebas
python manage.py test -v 2                            # con el nombre de cada prueba
python manage.py test usuarios.tests                  # solo HU-01 y HU-02 (80)
python manage.py test usuarios.tests_gestion          # solo HU-03 (69)
python manage.py test usuarios.tests_permisos         # solo HU-04 (132)
python manage.py test operativos.tests                # solo HU-05 (141)
python manage.py test operativos.tests_asignaciones   # solo HU-06 (124)
python manage.py test fichas                          # HU-07 a HU-16 (792)
```

Si PostgreSQL no está disponible, se puede correr la batería sobre SQLite en memoria:

```bash
DB_ENGINE=sqlite3 python manage.py test      # Git Bash
$env:DB_ENGINE="sqlite3"; python manage.py test   # PowerShell
```

El entorno de desarrollo y producción usa **siempre PostgreSQL**; esta alternativa
existe solo como contingencia para ejecutar las pruebas.

---

## Comandos útiles

```bash
python manage.py crear_usuarios_demo        # una cuenta por rol
python manage.py crear_encuestas_demo       # operativo con encuestas en los 7 estados
python manage.py makemigrations             # detecta cambios en los modelos
python manage.py showmigrations             # estado de las migraciones
python manage.py sqlmigrate usuarios 0001   # muestra el SQL generado
python manage.py check --deploy             # auditoría de seguridad para producción
python manage.py shell                      # consola interactiva
```

---

## Estructura

```
backend/
├── config/          configuración del proyecto (settings, urls, wsgi)
├── usuarios/        autenticación, roles, permisos y auditoría
├── dashboards/      paneles diferenciados por rol
├── operativos/      territorio (comuna/sector/zona) y reparto del trabajo
├── fichas/          encuestas, viviendas, hogares, integrantes y fotografías
├── media/           archivos subidos (NO se versiona ni se sirve como estático)
├── templates/       plantillas HTML
├── static/          CSS y Bootstrap local (funciona sin internet)
├── scripts/         script SQL de creación de la base de datos
└── docs/            documentación técnica de cada historia de usuario
```
