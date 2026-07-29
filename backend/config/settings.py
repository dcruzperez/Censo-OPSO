"""
Configuración del proyecto OPSO (Operativo Social).

Cada bloque está comentado explicando QUÉ hace y POR QUÉ está ahí,
porque esta configuración es parte de la defensa del proyecto de título.

Regla general aplicada: NINGÚN dato sensible (contraseñas, SECRET_KEY)
está escrito dentro del código. Todo se lee desde el archivo .env
mediante python-decouple. Así el repositorio puede publicarse sin filtrar
credenciales (principio de "configuración por entorno", 12-factor app).
"""

from pathlib import Path

from decouple import Csv, config

# BASE_DIR apunta a la carpeta "backend/" (dos niveles arriba de este archivo).
# Se usa para construir rutas absolutas sin depender del sistema operativo.
BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================================================================
# 1. SEGURIDAD BÁSICA
# ==========================================================================

# La SECRET_KEY firma criptográficamente las cookies de sesión y los tokens
# CSRF. Si se filtra, un atacante podría falsificar sesiones. Por eso vive
# en .env y nunca en el repositorio.
SECRET_KEY = config("DJANGO_SECRET_KEY")

# DEBUG=True muestra trazas de error con código y variables internas.
# En producción SIEMPRE debe ser False (una traza revela rutas, consultas SQL
# y hasta fragmentos de configuración).
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

# Lista blanca de dominios que pueden servir la aplicación. Evita ataques de
# "HTTP Host header poisoning" (envenenamiento del encabezado Host).
ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv()
)

# Orígenes de confianza para peticiones POST con CSRF (necesario si se sirve
# detrás de un dominio con HTTPS o un proxy inverso).
CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())


# ==========================================================================
# 2. APLICACIONES INSTALADAS
# ==========================================================================

INSTALLED_APPS = [
    # --- Aplicaciones propias de Django ---
    "django.contrib.admin",  # panel de administración automático
    "django.contrib.auth",  # autenticación: hashing, permisos, grupos
    "django.contrib.contenttypes",  # registro de modelos (lo usa auth)
    "django.contrib.sessions",  # manejo de sesiones en base de datos
    "django.contrib.messages",  # mensajes flash ("Bienvenido", "Error...")
    "django.contrib.staticfiles",  # CSS, JS, imágenes
    # --- Aplicaciones de OPSO ---
    "usuarios",  # HU: autenticación, roles y auditoría de accesos
    "dashboards",  # paneles diferenciados por rol
]


# ==========================================================================
# 3. MIDDLEWARE (cadena de procesamiento de cada petición)
# ==========================================================================
# El orden IMPORTA: cada middleware envuelve al siguiente, como capas de
# cebolla. La petición baja de arriba hacia abajo y la respuesta sube al revés.

MIDDLEWARE = [
    # Encabezados de seguridad HTTP (HSTS, nosniff, redirección a HTTPS).
    "django.middleware.security.SecurityMiddleware",
    # Lee la cookie de sesión y deja disponible request.session.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Valida el token CSRF en todo POST/PUT/DELETE.
    "django.middleware.csrf.CsrfViewMiddleware",
    # Convierte la sesión en request.user (AnonymousUser si no hay sesión).
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # "Seguro por defecto": exige sesión iniciada en TODAS las vistas.
    # Las vistas públicas deben marcarse explícitamente con @login_not_required.
    # Disponible desde Django 5.1 y es la forma más robusta de evitar que una
    # vista nueva quede desprotegida por olvido del programador.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Middleware propio: cierra la sesión tras N minutos sin actividad.
    # Va después de MessageMiddleware porque necesita poder dejar un mensaje.
    "usuarios.middleware.CierreSesionPorInactividadMiddleware",
    # Impide que el sitio sea embebido en un <iframe> ajeno (clickjacking).
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"


# ==========================================================================
# 4. PLANTILLAS (templates)
# ==========================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Carpeta global de plantillas del proyecto.
        "DIRS": [BASE_DIR / "templates"],
        # También busca plantillas dentro de cada app (app/templates/).
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                # Inyecta la variable {{ user }} en todas las plantillas.
                "django.contrib.auth.context_processors.auth",
                # Inyecta {{ messages }} para los avisos flash.
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ==========================================================================
# 5. BASE DE DATOS: PostgreSQL
# ==========================================================================
# PostgreSQL es el motor objetivo del proyecto. Se permite conmutar a SQLite
# mediante la variable DB_ENGINE únicamente para ejecutar la batería de
# pruebas automáticas en un equipo sin servidor de base de datos levantado.
# El entorno de desarrollo y producción usa SIEMPRE PostgreSQL.

DB_ENGINE = config("DB_ENGINE", default="postgresql")

if DB_ENGINE == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db_pruebas.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="opso_db"),
            "USER": config("DB_USER", default="opso_user"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            # Reutiliza conexiones durante 60 s en vez de abrir una nueva por
            # petición: menos latencia y menos carga en PostgreSQL.
            "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
            "OPTIONS": {
                # Aborta consultas que superen los 10 segundos: evita que una
                # consulta mal escrita bloquee el servidor.
                "options": "-c statement_timeout=10000",
            },
        }
    }

    # Comprobación temprana de la contraseña de la base de datos.
    #
    # POR QUÉ: si .env se copió de .env.example y DB_PASSWORD quedó con el
    # texto de plantilla, PostgreSQL responde "la autentificación password
    # falló para el usuario opso_user" — el mismo error que da una contraseña
    # equivocada Y que un rol inexistente (con scram-sha-256 el servidor no
    # los distingue, a propósito, para no revelar qué usuarios existen).
    # Ese mensaje manda a depurar el servidor cuando el problema está en un
    # archivo de configuración sin completar.
    #
    # Falla al ARRANCAR y no en la primera consulta, porque un error de
    # configuración debe detenerse antes de atender peticiones.
    _clave_bd = DATABASES["default"]["PASSWORD"]
    if not _clave_bd or _clave_bd.startswith("reemplazar"):
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "DB_PASSWORD no está configurada en backend/.env "
            f"(valor actual: {'vacío' if not _clave_bd else 'texto de plantilla'}).\n"
            "Para crear la base de datos y escribir la contraseña "
            "automáticamente, ejecuta:\n"
            "    cd backend\n"
            "    ..\\.venv\\Scripts\\python.exe scripts\\preparar_base_datos.py --migrar\n"
            "Para ejecutar las pruebas sin servidor PostgreSQL: DB_ENGINE=sqlite3"
        )

# Tipo de clave primaria por defecto para los modelos nuevos.
# BigAutoField = entero de 64 bits: no se agota aunque el censo crezca mucho.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==========================================================================
# 6. MODELO DE USUARIO PERSONALIZADO
# ==========================================================================
# Le indicamos a Django que el usuario del sistema NO es el modelo por
# defecto, sino nuestro modelo usuarios.Usuario (que inicia sesión con correo
# electrónico y tiene un rol asociado).
AUTH_USER_MODEL = "usuarios.Usuario"


# ==========================================================================
# 7. VALIDACIÓN Y CIFRADO DE CONTRASEÑAS
# ==========================================================================

# Reglas que debe cumplir una contraseña al crearse o cambiarse.
# Se aplican al DEFINIR la contraseña, no al iniciar sesión.
AUTH_PASSWORD_VALIDATORS = [
    {
        # Rechaza contraseñas parecidas al correo, nombre o RUT del usuario.
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        # Compara contra una lista de las 20.000 contraseñas más usadas.
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        # Impide contraseñas puramente numéricas (12345678).
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Algoritmos de hash. El PRIMERO se usa para las contraseñas nuevas; los
# demás permiten verificar contraseñas antiguas y re-hashearlas al vuelo.
# Argon2id es el algoritmo recomendado actualmente (ganador del Password
# Hashing Competition): es lento a propósito y resistente a ataques con GPU.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


# ==========================================================================
# 8. RUTAS DE AUTENTICACIÓN
# ==========================================================================

# A dónde se envía a un visitante que intenta abrir una página protegida.
# Django agrega automáticamente ?next=/la/pagina/pedida para volver ahí
# después de autenticarse.
LOGIN_URL = "usuarios:login"

# A dónde va el usuario recién autenticado cuando no hay un ?next=.
# Apunta al "despachador": una vista que mira el rol y reenvía al panel
# correspondiente. Así esta constante no queda amarrada a un solo rol.
LOGIN_REDIRECT_URL = "dashboards:redirigir"

# A dónde va el usuario después de cerrar sesión.
LOGOUT_REDIRECT_URL = "usuarios:login"

# Backend de autenticación (el que compara el hash de la contraseña).
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]


# ==========================================================================
# 9. SESIONES
# ==========================================================================

# Las sesiones se guardan en la tabla django_session de PostgreSQL. El
# navegador solo recibe un identificador aleatorio firmado, nunca los datos.
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Duración máxima de la cookie de sesión: 8 horas (una jornada de terreno).
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=60 * 60 * 8, cast=int)

# JavaScript NO puede leer la cookie de sesión: mitiga el robo de sesión
# mediante XSS.
SESSION_COOKIE_HTTPONLY = True

# La cookie no se envía en peticiones originadas por otro sitio: refuerzo
# adicional contra CSRF.
SESSION_COOKIE_SAMESITE = "Lax"

# Solo enviar la cookie por HTTPS. Se desactiva en desarrollo (http://localhost).
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)

# Renueva la expiración en cada petición: la sesión "se mantiene viva"
# mientras el usuario trabaja y caduca cuando deja de usarla.
SESSION_SAVE_EVERY_REQUEST = True

CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_SAMESITE = "Lax"


# ==========================================================================
# 10. ENVÍO DE CORREO ELECTRÓNICO
# ==========================================================================
# Necesario para la recuperación de contraseña. Ninguna credencial está
# escrita aquí: todas se leen del archivo .env.

# QUÉ hace: elige el "motor" que realmente entrega el correo.
#   - console.EmailBackend  -> lo imprime en la terminal (DESARROLLO)
#   - smtp.EmailBackend     -> lo envía por SMTP de verdad (PRODUCCIÓN)
#   - locmem.EmailBackend   -> lo guarda en memoria (lo usan las PRUEBAS)
# En desarrollo se usa la consola a propósito: se ve el enlace de recuperación
# sin necesidad de una cuenta de correo ni de conexión a internet.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Servidor SMTP que entrega el mensaje (la "oficina de correos").
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")

# Puerto del servidor SMTP:
#   587 -> STARTTLS (la conexión empieza en claro y se cifra enseguida)
#   465 -> SSL/TLS directo (cifrada desde el primer byte)
#    25 -> sin cifrado; nunca usar en internet
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)

# Cifra la conexión con el servidor SMTP mediante STARTTLS.
# Es indispensable: sin esto, la contraseña de la cuenta de correo y el
# contenido del mensaje viajarían en texto plano por la red.
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

# Alternativa a TLS para el puerto 465. Son mutuamente excluyentes:
# activar ambos produce un error de conexión.
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)

# Cuenta con la que OPSO se autentica ante el servidor SMTP.
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")

# Contraseña de esa cuenta. En Gmail debe ser una "contraseña de aplicación"
# de 16 caracteres, no la contraseña personal (Google bloquea el acceso
# directo de aplicaciones desde 2022).
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

# Remitente que verá el usuario en su bandeja de entrada. Se usa cuando el
# código no especifica un remitente explícito.
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="OPSO - Operativo Social <no-responder@opso.cl>"
)

# Remitente de los mensajes automáticos de error del servidor (500).
SERVER_EMAIL = config("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# Segundos de espera antes de abandonar la conexión SMTP. Sin esto, un
# servidor de correo caído dejaría la petición HTTP colgada indefinidamente.
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)

# Prefijo del asunto. OJO: Django solo lo aplica a mail_admins() y
# mail_managers(), NO a los correos normales. El asunto del correo de
# recuperación se define en su propia plantilla.
EMAIL_SUBJECT_PREFIX = "[OPSO] "

# Nombre del sistema tal como aparece en los correos y en las pantallas.
OPSO_NOMBRE_SISTEMA = config("OPSO_NOMBRE_SISTEMA", default="OPSO")
OPSO_CORREO_SOPORTE = config("OPSO_CORREO_SOPORTE", default="soporte@opso.cl")


# ==========================================================================
# 11. RECUPERACIÓN DE CONTRASEÑA
# ==========================================================================

# Cuánto tiempo sigue siendo válido el enlace enviado por correo.
# El valor por defecto de Django son 3 días (259200 s); aquí se reduce a
# 1 hora. Razón: cuanto menos vive el enlace, menor es la ventana en que un
# correo filtrado o un equipo compartido permiten secuestrar la cuenta.
# Una hora es suficiente para que una persona lea su correo y reaccione.
PASSWORD_RESET_TIMEOUT = config("PASSWORD_RESET_TIMEOUT", default=60 * 60, cast=int)


# ==========================================================================
# 12. CACHÉ
# ==========================================================================
# Se usa para contar solicitudes de recuperación y frenar los abusos.
# ¿Por qué en caché y no en PostgreSQL? Porque es un dato EFÍMERO: interesa
# durante 15 minutos y después no vale nada. Guardarlo en la base implicaría
# una escritura por cada intento y una tabla que crece sin aportar información.
#
# LocMemCache vive en la memoria del proceso: perfecto para desarrollo, pero
# NO se comparte entre procesos. En producción con varios trabajadores
# (Gunicorn) debe reemplazarse por Redis o Memcached, o cada trabajador
# llevaría su propia cuenta.
CACHES = {
    "default": {
        "BACKEND": config(
            "CACHE_BACKEND", default="django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": config("CACHE_LOCATION", default="opso-cache-local"),
    }
}


# ==========================================================================
# 13. PARÁMETROS DE SEGURIDAD PROPIOS DE OPSO
# ==========================================================================

# Bloqueo temporal contra ataques de fuerza bruta (probar miles de claves).
OPSO_INTENTOS_MAXIMOS_LOGIN = config("OPSO_INTENTOS_MAXIMOS_LOGIN", default=5, cast=int)
OPSO_BLOQUEO_LOGIN_MINUTOS = config("OPSO_BLOQUEO_LOGIN_MINUTOS", default=15, cast=int)

# Cierre automático de sesión por inactividad (dato sensible en pantalla).
OPSO_INACTIVIDAD_MINUTOS = config("OPSO_INACTIVIDAD_MINUTOS", default=30, cast=int)

# Límite de solicitudes de recuperación de contraseña.
# Evita que alguien use el formulario como máquina de enviar correos (spam a
# una casilla ajena) o para saturar el servidor SMTP.
OPSO_MAX_SOLICITUDES_RECUPERACION = config(
    "OPSO_MAX_SOLICITUDES_RECUPERACION", default=3, cast=int
)
OPSO_MAX_SOLICITUDES_RECUPERACION_IP = config(
    "OPSO_MAX_SOLICITUDES_RECUPERACION_IP", default=10, cast=int
)
OPSO_VENTANA_RECUPERACION_MINUTOS = config(
    "OPSO_VENTANA_RECUPERACION_MINUTOS", default=15, cast=int
)


# ==========================================================================
# 14. ENCABEZADOS DE SEGURIDAD HTTP (activos solo en producción)
# ==========================================================================

# Impide que el navegador "adivine" el tipo de contenido (ataques MIME).
SECURE_CONTENT_TYPE_NOSNIFF = True

# Prohíbe que cualquier sitio embeba OPSO en un iframe.
X_FRAME_OPTIONS = "DENY"

# No filtrar la URL interna de OPSO al navegar hacia sitios externos.
SECURE_REFERRER_POLICY = "same-origin"

# Redirige todo http:// a https://. Se controla por variable de entorno (y no
# solo por DEBUG) porque el corredor de pruebas de Django fuerza DEBUG=False:
# si dependiera de DEBUG, cada petición de prueba respondería una redirección.
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=not DEBUG, cast=bool)

# HSTS: obliga al navegador a usar HTTPS durante un año.
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=31536000 if not DEBUG else 0, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0


# ==========================================================================
# 15. INTERNACIONALIZACIÓN
# ==========================================================================

LANGUAGE_CODE = "es-cl"  # mensajes de error de Django en español
TIME_ZONE = "America/Santiago"  # zona horaria de Chile continental
USE_I18N = True
# Guarda las fechas en UTC en PostgreSQL y las convierte al mostrarlas.
# Evita errores por el cambio de horario de verano chileno.
USE_TZ = True


# ==========================================================================
# 16. ARCHIVOS ESTÁTICOS
# ==========================================================================

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Carpeta destino de "collectstatic" para el servidor web en producción.
STATIC_ROOT = BASE_DIR / "staticfiles"

# En producción conviene agregar un hash al nombre de cada archivo estático
# (ManifestStaticFilesStorage) para forzar la actualización de la caché del
# navegador cuando cambia el CSS. Requiere haber ejecutado collectstatic.
USAR_MANIFIESTO_ESTATICOS = config(
    "USAR_MANIFIESTO_ESTATICOS", default=not DEBUG, cast=bool
)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            if USAR_MANIFIESTO_ESTATICOS
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}


# ==========================================================================
# 17. REGISTRO DE EVENTOS (logging)
# ==========================================================================
# Deja rastro de los eventos de seguridad. Es un requisito de trazabilidad:
# ante un incidente hay que poder responder "quién entró, cuándo y desde dónde".

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "opso": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": "opso",
        }
    },
    "loggers": {
        # Eventos de autenticación de OPSO.
        "usuarios": {
            "handlers": ["consola"],
            "level": "INFO",
            "propagate": False,
        },
        # Avisos de seguridad de Django (Host inválido, CSRF fallido, etc.).
        "django.security": {
            "handlers": ["consola"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# ==========================================================================
# 18. MENSAJES FLASH -> CLASES CSS DE BOOTSTRAP
# ==========================================================================
# Traduce los niveles de mensaje de Django a las clases de alerta de Bootstrap,
# para no repetir condicionales en las plantillas.

from django.contrib.messages import constants as niveles_mensaje  # noqa: E402

MESSAGE_TAGS = {
    niveles_mensaje.DEBUG: "secondary",
    niveles_mensaje.INFO: "info",
    niveles_mensaje.SUCCESS: "success",
    niveles_mensaje.WARNING: "warning",
    niveles_mensaje.ERROR: "danger",
}
