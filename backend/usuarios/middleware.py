"""Middleware propio de OPSO.

Un middleware se ejecuta en TODAS las peticiones. Por eso se usa solo para
reglas transversales, no para permisos de una vista puntual.

Este caso es transversal por naturaleza: "toda pantalla debe cerrarse sola si
la persona se aleja del computador". Un censista puede estar en terreno con el
equipo desatendido y en pantalla hay datos personales de familias.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

CLAVE_ULTIMA_ACTIVIDAD = "ultima_actividad"


class CierreSesionPorInactividadMiddleware:
    """Cierra la sesión tras OPSO_INACTIVIDAD_MINUTOS sin peticiones."""

    def __init__(self, get_response):
        # Se ejecuta UNA vez al arrancar el servidor.
        self.get_response = get_response
        self.limite = settings.OPSO_INACTIVIDAD_MINUTOS * 60

    def __call__(self, request):
        # Se ejecuta en CADA petición, antes de llegar a la vista.
        if request.user.is_authenticated:
            ahora = timezone.now().timestamp()
            ultima = request.session.get(CLAVE_ULTIMA_ACTIVIDAD)

            if ultima and (ahora - ultima) > self.limite:
                logout(request)  # borra la sesión del servidor y la cookie
                messages.warning(
                    request,
                    "Tu sesión se cerró automáticamente por inactividad. "
                    "Vuelve a iniciar sesión para continuar.",
                )
                return redirect(reverse("usuarios:login"))

            # Marca de tiempo de esta actividad.
            request.session[CLAVE_ULTIMA_ACTIVIDAD] = ahora

        return self.get_response(request)
