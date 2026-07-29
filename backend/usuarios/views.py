"""Vistas de autenticación de OPSO.

Se usan vistas basadas en clases (CBV) heredando de LoginView y LogoutView,
las vistas oficiales de Django. Motivo: ya resuelven correctamente los
detalles delicados de seguridad (rotación del identificador de sesión,
validación del parámetro ?next=, protección CSRF, encabezados anti-caché).
Reescribirlas desde cero sería reintroducir errores ya resueltos.

Solo redefinimos los puntos de extensión que OPSO necesita.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from .forms import EstablecerContrasenaForm, LoginForm, RecuperarContrasenaForm
from .seguridad import (
    intentos_restantes,
    notificar_cambio_contrasena,
    obtener_ip,
    registrar_solicitud_recuperacion,
)

logger = logging.getLogger("usuarios")


# login_not_required: esta vista es la excepción pública del sistema. Como
# activamos LoginRequiredMiddleware (todo exige sesión), hay que declararlo
# explícitamente o nadie podría llegar al formulario de acceso.
@method_decorator(login_not_required, name="dispatch")
class LoginOPSOView(LoginView):
    """Pantalla de inicio de sesión.

    Flujo interno heredado de LoginView:
      GET  -> construye el formulario vacío y renderiza la plantilla.
      POST -> valida el formulario. Si es válido llama a form_valid(); si no,
              vuelve a renderizar la plantilla con los errores.
    """

    template_name = "usuarios/login.html"

    # Formulario propio (con Bootstrap, bloqueo por intentos y textos en español).
    authentication_form = LoginForm

    # Si alguien ya autenticado abre /login/, se le envía a su panel en vez de
    # mostrarle otra vez el formulario.
    redirect_authenticated_user = True

    def form_valid(self, form):
        """Credenciales correctas: aquí nace la sesión."""
        # super() ejecuta django.contrib.auth.login(request, user), que:
        #   1. Genera un identificador de sesión NUEVO (rotación de clave):
        #      neutraliza el ataque de "fijación de sesión".
        #   2. Guarda el id del usuario y el backend usado dentro de la sesión.
        #   3. Emite la señal user_logged_in (nuestra auditoría escucha ahí).
        respuesta = super().form_valid(form)

        if not form.cleaned_data.get("recordarme"):
            # set_expiry(0): la sesión muere al cerrar el navegador.
            # Es lo correcto en equipos compartidos o de uso en terreno.
            self.request.session.set_expiry(0)

        messages.success(
            self.request,
            f"Bienvenido/a, {self.request.user.get_short_name() or self.request.user.email}.",
        )
        return respuesta

    def form_invalid(self, form):
        """Credenciales incorrectas: avisamos cuántos intentos quedan.

        Es un aviso preventivo honesto para el usuario legítimo que se
        equivocó, sin revelar si el correo existe o no.
        """
        email = form.data.get("username", "")
        restantes = intentos_restantes(email)

        if 0 < restantes <= 2:
            messages.warning(
                self.request,
                f"Atención: te queda(n) {restantes} intento(s) antes de que la "
                "cuenta se bloquee temporalmente.",
            )

        return super().form_invalid(form)

    def get_success_url(self):
        """A dónde va el usuario recién autenticado.

        Prioridad:
          1. El ?next= que Django agregó cuando el usuario intentó abrir una
             página protegida. LoginView ya verificó que apunte a este mismo
             sitio (si no, un atacante podría enviarlo a un sitio falso:
             vulnerabilidad de "open redirect").
          2. Su panel según el rol.
        """
        return self.get_redirect_url() or self.request.user.get_dashboard_url()

    def get_context_data(self, **kwargs):
        """Datos extra para la plantilla."""
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Iniciar sesión"
        return contexto


@method_decorator(login_not_required, name="dispatch")
class LogoutOPSOView(LogoutView):
    """Cierre de sesión.

    IMPORTANTE: desde Django 5 solo acepta POST, no GET. ¿Por qué?
    Porque con GET bastaba con que un tercero incrustara
    <img src="https://opso.cl/logout/"> en otra página para desconectar al
    usuario. Al exigir POST + token CSRF, eso es imposible.
    """

    next_page = reverse_lazy("usuarios:login")

    def post(self, request, *args, **kwargs):
        estaba_autenticado = request.user.is_authenticated

        # super().post() llama a auth.logout(): borra la fila de la tabla
        # django_session y vacía la cookie del navegador.
        respuesta = super().post(request, *args, **kwargs)

        # El mensaje se agrega DESPUÉS del logout: si se agregara antes, se
        # borraría junto con la sesión y el usuario no lo vería nunca.
        if estaba_autenticado:
            messages.info(request, "Cerraste sesión correctamente.")

        return respuesta


# ==========================================================================
# RECUPERACIÓN DE CONTRASEÑA (4 pantallas)
# ==========================================================================
# Se heredan las CUATRO vistas nativas de Django. Ninguna de ellas necesita
# @login_not_required: Django ya las trae decoradas así (se puede verificar en
# django/contrib/auth/views.py), porque por definición las usa alguien que no
# puede iniciar sesión.
#
# Lo ÚNICO que es obligatorio redefinir es success_url. Las vistas de Django
# apuntan a reverse_lazy("password_reset_done") SIN espacio de nombres, y en
# OPSO las URLs viven bajo el namespace "usuarios:". Sin este ajuste, Django
# lanzaría NoReverseMatch al enviar el formulario.


class RecuperarContrasenaView(PasswordResetView):
    """PANTALLA 1 — /recuperar-contrasena/

    Pide el correo, genera el token y envía el enlace.
    """

    template_name = "usuarios/password_reset.html"
    form_class = RecuperarContrasenaForm
    success_url = reverse_lazy("usuarios:password_reset_done")

    # Plantillas del correo. Se envía en DOS formatos dentro del mismo mensaje
    # (multipart/alternative): texto plano y HTML. El cliente de correo elige
    # el que puede mostrar; así el mensaje se lee incluso en clientes antiguos
    # o con el HTML deshabilitado por seguridad.
    subject_template_name = "usuarios/correo/recuperacion_asunto.txt"
    email_template_name = "usuarios/correo/recuperacion.txt"
    html_email_template_name = "usuarios/correo/recuperacion.html"

    # Datos adicionales disponibles en las plantillas del correo.
    # También se sobrescribe site_name: sin la app django.contrib.sites,
    # Django usaría el encabezado Host (ej. "127.0.0.1:8000") como nombre del
    # sitio, lo que quedaría feo en el correo.
    extra_email_context = {
        "nombre_sistema": settings.OPSO_NOMBRE_SISTEMA,
        "site_name": settings.OPSO_NOMBRE_SISTEMA,
        "correo_soporte": settings.OPSO_CORREO_SOPORTE,
        "minutos_validez": settings.PASSWORD_RESET_TIMEOUT // 60,
    }

    def form_valid(self, form):
        """El correo tiene formato válido: se decide si enviar el enlace.

        Punto clave de seguridad: el resultado visible es SIEMPRE el mismo,
        haya o no haya enviado correo. Los tres casos posibles —correo
        inexistente, cuenta desactivada y límite de solicitudes superado—
        terminan en la misma pantalla. Un atacante no puede distinguirlos.
        """
        email = form.cleaned_data["email"]
        excedido, motivo = registrar_solicitud_recuperacion(email, self.request)

        if excedido:
            # No se envía el correo, pero tampoco se avisa: se registra en el
            # log del servidor, que es donde el administrador puede verlo.
            logger.warning(
                "Solicitud de recuperación descartada | correo=%s | ip=%s | %s",
                email,
                obtener_ip(self.request),
                motivo,
            )
            # Se omite form.save() (que es quien envía el correo) y se
            # redirige igual que en el caso exitoso.
            return HttpResponseRedirect(self.get_success_url())

        logger.info(
            "Solicitud de recuperación recibida | correo=%s | ip=%s",
            email,
            obtener_ip(self.request),
        )

        # super() de PasswordResetView llama a form.save(), que genera el
        # token y envía el correo.
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Recuperar contraseña"
        contexto["paso"] = 1
        contexto["minutos_validez"] = settings.PASSWORD_RESET_TIMEOUT // 60
        return contexto


class RecuperarContrasenaEnviadoView(PasswordResetDoneView):
    """PANTALLA 2 — /recuperar-contrasena/enviado/

    Confirmación neutra: "si el correo está registrado, recibirás un enlace".
    No confirma ni niega la existencia de la cuenta.
    """

    template_name = "usuarios/password_reset_done.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Revisa tu correo"
        contexto["paso"] = 2
        contexto["minutos_validez"] = settings.PASSWORD_RESET_TIMEOUT // 60
        return contexto


class RestablecerContrasenaView(PasswordResetConfirmView):
    """PANTALLA 3 — /restablecer/<uidb64>/<token>/

    Valida el token y, si es correcto, permite escribir la contraseña nueva.

    Detalle importante que hereda de Django: al abrir el enlace, la vista
    NO muestra el formulario de inmediato. Guarda el token en la sesión y
    redirige a /restablecer/<uidb64>/set-password/. ¿Por qué? Para que el
    token desaparezca de la barra de direcciones y no se filtre por el
    encabezado Referer si la página incluyera algún recurso externo.
    """

    template_name = "usuarios/password_reset_confirm.html"
    form_class = EstablecerContrasenaForm
    success_url = reverse_lazy("usuarios:password_reset_complete")

    # No se inicia sesión automáticamente tras el cambio.
    # Motivo: obligar a escribir la contraseña nueva confirma que la persona
    # la recuerda o la guardó, y mantiene un único camino de autenticación
    # (con su bitácora y su bloqueo por intentos fallidos).
    post_reset_login = False

    def form_valid(self, form):
        """La contraseña nueva es válida: se guarda su hash."""
        # super() ejecuta form.save() -> user.set_password() + user.save(),
        # y borra el token de la sesión.
        respuesta = super().form_valid(form)

        logger.info(
            "Contraseña restablecida | usuario=%s | ip=%s",
            self.user.email,
            obtener_ip(self.request),
        )

        # Aviso de seguridad al titular de la cuenta.
        notificar_cambio_contrasena(self.user, self.request)

        return respuesta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Nueva contraseña"
        contexto["paso"] = 3
        contexto["minutos_validez"] = settings.PASSWORD_RESET_TIMEOUT // 60
        return contexto


class RestablecerContrasenaCompletadoView(PasswordResetCompleteView):
    """PANTALLA 4 — /restablecer/completado/

    Aviso de éxito con el enlace para iniciar sesión.
    """

    template_name = "usuarios/password_reset_complete.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Contraseña actualizada"
        contexto["paso"] = 4
        return contexto


class SinRolView(LoginRequiredMixin, TemplateView):
    """Pantalla para una cuenta válida a la que aún no se le asignó rol.

    Alternativa descartada: impedirle iniciar sesión. Se prefirió dejarlo
    entrar a una pantalla informativa porque el usuario ya demostró tener
    credenciales legítimas y así recibe una instrucción clara en vez de un
    error confuso; además no ve ningún dato del censo (principio de
    privilegio mínimo).
    """

    template_name = "usuarios/sin_rol.html"
