"""Funciones de apoyo a la seguridad del inicio de sesión.

Se aíslan aquí (y no dentro de las vistas) para poder probarlas de forma
independiente y reutilizarlas desde el formulario, las señales y el middleware.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger("usuarios")


def obtener_ip(request):
    """Obtiene la IP del cliente considerando un posible proxy inverso.

    Si OPSO se despliega detrás de Nginx, request.META["REMOTE_ADDR"] sería
    la IP del propio Nginx (127.0.0.1). El encabezado X-Forwarded-For guarda
    la cadena real: "ip_cliente, ip_proxy1, ip_proxy2".
    """
    if request is None:
        return None

    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def obtener_user_agent(request):
    """Navegador y sistema operativo declarados por el cliente (para auditoría)."""
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:300]


def registrar_intento(email, exitoso, request=None, usuario=None):
    """Escribe una fila en la bitácora de intentos de acceso."""
    from .models import IntentoAcceso

    intento = IntentoAcceso.objects.create(
        email_ingresado=(email or "")[:254].lower(),
        usuario=usuario,
        exitoso=exitoso,
        ip=obtener_ip(request),
        user_agent=obtener_user_agent(request),
    )

    nivel = logger.info if exitoso else logger.warning
    nivel(
        "Intento de acceso %s | correo=%s | ip=%s",
        "EXITOSO" if exitoso else "FALLIDO",
        intento.email_ingresado,
        intento.ip,
    )
    return intento


def _inicio_ventana():
    """Momento a partir del cual se cuentan los intentos fallidos."""
    return timezone.now() - timedelta(minutes=settings.OPSO_BLOQUEO_LOGIN_MINUTOS)


def intentos_fallidos_recientes(email):
    """Cuenta los fallos del último periodo de bloqueo para ese correo.

    Solo se cuentan los fallos POSTERIORES al último ingreso exitoso: si la
    persona se equivocó tres veces y luego entró bien, el contador se reinicia.
    """
    from .models import IntentoAcceso

    if not email:
        return 0

    email = email.strip().lower()
    consulta = IntentoAcceso.objects.filter(
        email_ingresado=email, ocurrido_en__gte=_inicio_ventana()
    )

    ultimo_exito = (
        consulta.filter(exitoso=True).order_by("-ocurrido_en").values_list("ocurrido_en", flat=True).first()
    )
    fallidos = consulta.filter(exitoso=False)
    if ultimo_exito:
        fallidos = fallidos.filter(ocurrido_en__gt=ultimo_exito)

    return fallidos.count()


def esta_bloqueado(email):
    """True si el correo superó el máximo de intentos fallidos permitidos."""
    return intentos_fallidos_recientes(email) >= settings.OPSO_INTENTOS_MAXIMOS_LOGIN


def intentos_restantes(email):
    """Cuántos intentos le quedan antes del bloqueo (para avisar al usuario)."""
    return max(0, settings.OPSO_INTENTOS_MAXIMOS_LOGIN - intentos_fallidos_recientes(email))


# ==========================================================================
# RECUPERACIÓN DE CONTRASEÑA
# ==========================================================================
# El control de frecuencia se guarda en la CACHÉ, no en PostgreSQL.
#
# ¿Por qué? Porque es un dato efímero: interesa durante 15 minutos y después
# no vale nada. Guardarlo en la base de datos implicaría una escritura por
# cada intento y una tabla que crece indefinidamente sin aportar información
# útil. La caché está pensada exactamente para esto: datos con fecha de
# vencimiento que se pueden perder sin consecuencias.


def _clave_cache(prefijo, valor):
    """Construye una clave de caché segura.

    Se aplica un hash al valor para que la clave no contenga el correo en
    claro (la caché podría inspeccionarse) y para evitar caracteres que
    Memcached no acepta, como espacios o acentos.
    """
    import hashlib

    huella = hashlib.sha256(str(valor).lower().encode("utf-8")).hexdigest()[:32]
    return f"opso:{prefijo}:{huella}"


def _incrementar_contador(clave, ventana_segundos):
    """Suma 1 al contador de la clave y devuelve el total de la ventana.

    cache.add() solo escribe si la clave NO existía: así la primera solicitud
    crea el contador junto con su tiempo de expiración, y las siguientes solo
    incrementan sin renovar el plazo. De esa forma la ventana es fija: 15
    minutos desde la PRIMERA solicitud, no desde la última.
    """
    if cache.add(clave, 1, ventana_segundos):
        return 1
    try:
        return cache.incr(clave)
    except ValueError:
        # La clave expiró entre el add() y el incr(): se reinicia el conteo.
        cache.set(clave, 1, ventana_segundos)
        return 1


def registrar_solicitud_recuperacion(email, request=None):
    """Cuenta una solicitud de recuperación y dice si excede los límites.

    Devuelve (excedido: bool, motivo: str). Se aplican DOS límites:

      - por CORREO: impide usar el formulario para bombardear la casilla de
        una persona con correos que no pidió.
      - por IP: impide que un atacante recorra una lista de correos ajenos
        (y de paso, que sature el servidor SMTP).

    Los dos son necesarios: el límite por correo solo no detiene a quien
    prueba mil correos distintos, y el límite por IP solo no protege a una
    persona atacada desde varias redes.
    """
    ventana = settings.OPSO_VENTANA_RECUPERACION_MINUTOS * 60

    total_email = _incrementar_contador(_clave_cache("recup:email", email), ventana)
    if total_email > settings.OPSO_MAX_SOLICITUDES_RECUPERACION:
        return True, f"límite por correo superado ({total_email} solicitudes)"

    ip = obtener_ip(request)
    if ip:
        total_ip = _incrementar_contador(_clave_cache("recup:ip", ip), ventana)
        if total_ip > settings.OPSO_MAX_SOLICITUDES_RECUPERACION_IP:
            return True, f"límite por IP superado ({total_ip} solicitudes)"

    return False, ""


def notificar_cambio_contrasena(usuario, request=None):
    """Avisa por correo que la contraseña de la cuenta fue cambiada.

    ¿Por qué enviar este segundo correo?
    Es un mecanismo de DETECCIÓN. Si alguien logró restablecer la contraseña
    sin autorización, la persona dueña de la cuenta se entera de inmediato y
    puede avisar al administrador. Sin este aviso, el cambio podría pasar
    inadvertido durante semanas.

    Nunca falla la operación por un problema de correo: la contraseña ya se
    cambió correctamente y sería absurdo mostrar un error por eso.
    """
    contexto = {
        "usuario": usuario,
        "nombre_sistema": settings.OPSO_NOMBRE_SISTEMA,
        "correo_soporte": settings.OPSO_CORREO_SOPORTE,
        "ip": obtener_ip(request),
        "fecha": timezone.localtime(),
    }

    try:
        cuerpo = render_to_string("usuarios/correo/aviso_cambio.txt", contexto)
        mensaje = EmailMultiAlternatives(
            subject=f"{settings.OPSO_NOMBRE_SISTEMA}: tu contraseña fue actualizada",
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[usuario.email],
        )
        mensaje.send(fail_silently=False)
    except Exception:
        # logger.exception registra el error completo con su traza, pero la
        # petición continúa con normalidad.
        logger.exception(
            "No se pudo enviar el aviso de cambio de contraseña a %s", usuario.pk
        )


# ==========================================================================
# ENLACE PARA DEFINIR LA CONTRASEÑA (HU-03: creación de cuentas)
# ==========================================================================
# Cuando el administrador crea una cuenta, la persona necesita una contraseña.
# En lugar de inventar un mecanismo nuevo, se REUTILIZA exactamente la
# maquinaria criptográfica de la HU-02:
#
#   default_token_generator -> genera y verifica el token firmado
#   usuarios:password_reset_confirm -> la vista que ya sabe validar ese token
#
# Lo único distinto es el texto del correo (invitación en vez de recuperación).
# Beneficio: cero criptografía nueva. El código más delicado del sistema sigue
# siendo el de Django, ya auditado, y no una versión escrita a mano.


def generar_clave_aleatoria():
    """Genera una contraseña larga y aleatoria que NADIE conoce.

    ¿Por qué asignar una contraseña que nadie sabe, en vez de dejar la cuenta
    sin contraseña (set_unusable_password)?

    Porque PasswordResetForm.get_users() de Django descarta las cuentas sin
    contraseña utilizable, y entonces el enlace nunca se enviaría. Con una
    contraseña aleatoria de 50 caracteres la cuenta es técnicamente válida pero
    inaccesible en la práctica (adivinarla es imposible), y el flujo de
    recuperación funciona con normalidad.

    get_random_string usa secrets, el generador criptográficamente seguro de
    Python: no es random.random(), que es predecible.
    """
    return get_random_string(50)


def enviar_enlace_contrasena(usuario, request=None, es_nueva_cuenta=False):
    """Envía a la persona un enlace personal para definir su contraseña.

    Devuelve True si el correo salió, False si falló el envío. La vista usa ese
    valor para avisarle al administrador, en vez de dar por hecho que llegó.

    IMPORTANTE: esta función NO modifica la contraseña del usuario. Enviar un
    enlace es una acción inofensiva: si la persona no lo abre, su contraseña
    actual sigue funcionando. Si en cambio se restableciera la clave al enviar
    el correo, un administrador distraído podría dejar fuera a alguien que
    estaba trabajando.
    """
    contexto = {
        "usuario": usuario,
        "nombre_sistema": settings.OPSO_NOMBRE_SISTEMA,
        "correo_soporte": settings.OPSO_CORREO_SOPORTE,
        "minutos_validez": settings.PASSWORD_RESET_TIMEOUT // 60,
        "es_nueva_cuenta": es_nueva_cuenta,
        # uid: el id del usuario codificado en base64 seguro para URL.
        # No es cifrado, solo una forma de poner un número en una dirección.
        "uid": urlsafe_base64_encode(force_bytes(usuario.pk)),
        # token: firma temporal que incluye el hash de la contraseña actual y
        # last_login. Por eso el enlace se invalida solo al usarse una vez.
        "token": default_token_generator.make_token(usuario),
        # Sin django.contrib.sites, el dominio se toma de la petición. Es
        # seguro porque ALLOWED_HOSTS ya rechazó cualquier Host falsificado.
        "protocol": "https" if (request and request.is_secure()) else "http",
        "domain": request.get_host() if request else "127.0.0.1:8000",
    }

    asunto = (
        f"{settings.OPSO_NOMBRE_SISTEMA}: activa tu cuenta y crea tu contraseña"
        if es_nueva_cuenta
        else f"{settings.OPSO_NOMBRE_SISTEMA}: enlace para crear una contraseña nueva"
    )

    try:
        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=render_to_string("usuarios/correo/invitacion.txt", contexto),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[usuario.email],
        )
        mensaje.attach_alternative(
            render_to_string("usuarios/correo/invitacion.html", contexto), "text/html"
        )
        mensaje.send(fail_silently=False)
    except Exception:
        logger.exception(
            "No se pudo enviar el enlace de contraseña a %s", usuario.email
        )
        return False

    logger.info(
        "Enlace de contraseña enviado | usuario=%s | nueva_cuenta=%s | ip=%s",
        usuario.email,
        es_nueva_cuenta,
        obtener_ip(request),
    )
    return True
