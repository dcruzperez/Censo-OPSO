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

**422 pruebas automáticas** en total (`python manage.py test` → OK).

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
python manage.py test                         # 422 pruebas
python manage.py test -v 2                    # con el nombre de cada prueba
python manage.py test usuarios.tests          # solo HU-01 y HU-02 (80)
python manage.py test usuarios.tests_gestion  # solo HU-03 (69)
python manage.py test usuarios.tests_permisos # solo HU-04 (132)
python manage.py test operativos              # solo HU-05 (141)
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
├── operativos/      operativos y organización territorial (comuna/sector/zona)
├── templates/       plantillas HTML
├── static/          CSS y Bootstrap local (funciona sin internet)
├── scripts/         script SQL de creación de la base de datos
└── docs/            documentación técnica de cada historia de usuario
```
