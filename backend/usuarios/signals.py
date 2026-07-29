"""Señales de autenticación.

Una señal es un aviso que Django emite cuando ocurre algo. En vez de
ensuciar la vista de login con código de auditoría, "nos suscribimos" a los
eventos y reaccionamos aparte. Esto se llama bajo acoplamiento: si mañana el
inicio de sesión cambia (por ejemplo, se agrega una API), la auditoría sigue
funcionando sin tocar nada, porque el evento se emite igual.
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .seguridad import registrar_intento

logger = logging.getLogger("usuarios")


@receiver(user_logged_in)
def registrar_ingreso_exitoso(sender, request, user, **kwargs):
    """Se dispara cuando Django completa un login (función auth.login)."""
    registrar_intento(
        email=user.get_username(), exitoso=True, request=request, usuario=user
    )


@receiver(user_login_failed)
def registrar_ingreso_fallido(sender, credentials, request=None, **kwargs):
    """Se dispara cuando authenticate() rechaza las credenciales.

    "credentials" viene con la contraseña ya enmascarada por Django
    (muestra "********"), justamente para que no termine en un log por error.
    """
    email = credentials.get("username") or credentials.get("email") or ""

    # Vinculamos la cuenta si existe, para poder revisar su historial.
    Usuario = get_user_model()
    usuario = Usuario.objects.filter(email__iexact=email).first()

    registrar_intento(email=email, exitoso=False, request=request, usuario=usuario)


@receiver(user_logged_out)
def registrar_salida(sender, request, user, **kwargs):
    """Deja rastro del cierre de sesión."""
    if user is not None:
        logger.info("Cierre de sesión | correo=%s", user.get_username())
