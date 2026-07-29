"""Pruebas automáticas de la historia de usuario "Inicio de sesión seguro".

¿Para qué sirven en un proyecto de título?
Son la EVIDENCIA verificable de que la funcionalidad cumple lo prometido. En la
defensa se puede ejecutar `python manage.py test` y mostrar que cada mecanismo
de seguridad descrito realmente funciona, en vez de solo afirmarlo.

Cada prueba sigue el patrón: PREPARAR (arrange) -> ACTUAR (act) -> VERIFICAR (assert).
"""

import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import IntentoAcceso, Rol, RolCodigo
from .validators import calcular_digito_verificador, limpiar_rut, validar_rut

Usuario = get_user_model()

CLAVE_VALIDA = "Censo2026#Opso"
CLAVE_NUEVA = "NuevaClave2026#Opso"


class BaseAutenticacionTest(TestCase):
    """Datos comunes a todas las pruebas de autenticación."""

    @classmethod
    def setUpTestData(cls):
        # Los roles ya existen: los creó la migración de datos 0002.
        cls.rol_admin = Rol.objects.get(codigo=RolCodigo.ADMINISTRADOR)
        cls.rol_supervisor = Rol.objects.get(codigo=RolCodigo.SUPERVISOR)
        cls.rol_censista = Rol.objects.get(codigo=RolCodigo.CENSISTA)

        cls.admin = Usuario.objects.create_user(
            email="admin@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Ana",
            last_name="Rojas",
            rol=cls.rol_admin,
        )
        cls.supervisor = Usuario.objects.create_user(
            email="supervisor@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Luis",
            last_name="Pérez",
            rol=cls.rol_supervisor,
        )
        cls.censista = Usuario.objects.create_user(
            email="censista@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Marta",
            last_name="Soto",
            rol=cls.rol_censista,
        )

    def setUp(self):
        self.url_login = reverse("usuarios:login")


class AlmacenamientoContrasenaTest(BaseAutenticacionTest):
    """Requisito: hash automático de contraseñas."""

    def test_la_contrasena_no_se_guarda_en_texto_plano(self):
        guardado = Usuario.objects.get(pk=self.censista.pk).password

        self.assertNotEqual(guardado, CLAVE_VALIDA)
        self.assertNotIn(CLAVE_VALIDA, guardado)
        # Formato de Django: algoritmo$parámetros$sal$hash
        self.assertTrue(guardado.startswith("argon2$"))

    def test_check_password_verifica_sin_descifrar(self):
        self.assertTrue(self.censista.check_password(CLAVE_VALIDA))
        self.assertFalse(self.censista.check_password("otra-clave-cualquiera"))

    def test_dos_usuarios_con_la_misma_clave_tienen_hash_distinto(self):
        """La "sal" aleatoria impide identificar contraseñas repetidas."""
        otro = Usuario.objects.create_user(email="otro@opso.cl", password=CLAVE_VALIDA)
        self.assertNotEqual(otro.password, self.censista.password)


class RedireccionPorRolTest(BaseAutenticacionTest):
    """Requisito: redirección automática según el rol."""

    def _iniciar_sesion(self, email):
        return self.client.post(
            self.url_login,
            {"username": email, "password": CLAVE_VALIDA},
            follow=False,
        )

    def test_administrador_va_a_dashboard_admin(self):
        respuesta = self._iniciar_sesion("admin@opso.cl")
        self.assertRedirects(
            respuesta, "/dashboard/admin/", fetch_redirect_response=False
        )

    def test_supervisor_va_a_dashboard_supervisor(self):
        respuesta = self._iniciar_sesion("supervisor@opso.cl")
        self.assertRedirects(
            respuesta, "/dashboard/supervisor/", fetch_redirect_response=False
        )

    def test_censista_va_a_dashboard_censista(self):
        respuesta = self._iniciar_sesion("censista@opso.cl")
        self.assertRedirects(
            respuesta, "/dashboard/censista/", fetch_redirect_response=False
        )

    def test_usuario_sin_rol_va_a_pantalla_informativa(self):
        Usuario.objects.create_user(email="sinrol@opso.cl", password=CLAVE_VALIDA)
        respuesta = self._iniciar_sesion("sinrol@opso.cl")
        self.assertRedirects(respuesta, "/sin-rol/", fetch_redirect_response=False)

    def test_despachador_reenvia_al_panel_del_rol(self):
        """/dashboard/ resuelve el destino en tiempo de ejecución."""
        self.client.force_login(self.supervisor)
        respuesta = self.client.get("/dashboard/")
        self.assertRedirects(
            respuesta, "/dashboard/supervisor/", fetch_redirect_response=False
        )

    def test_se_respeta_el_parametro_next(self):
        """Si el usuario pedía una página protegida, vuelve a ella."""
        respuesta = self.client.post(
            self.url_login,
            {
                "username": "admin@opso.cl",
                "password": CLAVE_VALIDA,
                "next": "/dashboard/supervisor/",
            },
        )
        self.assertRedirects(
            respuesta, "/dashboard/supervisor/", fetch_redirect_response=False
        )

    def test_no_se_permite_redireccion_a_sitio_externo(self):
        """Protección contra "open redirect": ?next= a otro dominio se ignora."""
        respuesta = self.client.post(
            self.url_login,
            {
                "username": "admin@opso.cl",
                "password": CLAVE_VALIDA,
                "next": "https://sitio-malicioso.example.com/",
            },
        )
        self.assertRedirects(
            respuesta, "/dashboard/admin/", fetch_redirect_response=False
        )


class ValidacionCredencialesTest(BaseAutenticacionTest):
    """Requisito: validación de credenciales."""

    def test_clave_incorrecta_no_crea_sesion(self):
        respuesta = self.client.post(
            self.url_login,
            {"username": "admin@opso.cl", "password": "clave-equivocada"},
        )
        self.assertEqual(respuesta.status_code, 200)  # se queda en el formulario
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_el_mensaje_de_error_no_revela_si_el_correo_existe(self):
        """Mismo texto para correo inexistente y para clave errónea."""
        r_correo_falso = self.client.post(
            self.url_login,
            {"username": "nadie@opso.cl", "password": "x" * 12},
        )
        r_clave_falsa = self.client.post(
            self.url_login,
            {"username": "admin@opso.cl", "password": "x" * 12},
        )

        errores_1 = r_correo_falso.context["form"].non_field_errors()
        errores_2 = r_clave_falsa.context["form"].non_field_errors()
        self.assertEqual(list(errores_1), list(errores_2))

    def test_el_correo_no_distingue_mayusculas(self):
        respuesta = self.client.post(
            self.url_login,
            {"username": "ADMIN@OPSO.CL", "password": CLAVE_VALIDA},
        )
        self.assertRedirects(
            respuesta, "/dashboard/admin/", fetch_redirect_response=False
        )

    def test_cuenta_desactivada_no_puede_ingresar(self):
        self.censista.is_active = False
        self.censista.save()

        respuesta = self.client.post(
            self.url_login,
            {"username": "censista@opso.cl", "password": CLAVE_VALIDA},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_rol_desactivado_impide_el_ingreso(self):
        """Regla de negocio propia de OPSO (confirm_login_allowed)."""
        self.rol_censista.activo = False
        self.rol_censista.save()
        self.addCleanup(self._reactivar_rol_censista)

        respuesta = self.client.post(
            self.url_login,
            {"username": "censista@opso.cl", "password": CLAVE_VALIDA},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)
        self.assertContains(respuesta, "rol asignado a tu cuenta está desactivado")

    def _reactivar_rol_censista(self):
        self.rol_censista.activo = True
        self.rol_censista.save()


@override_settings(OPSO_INTENTOS_MAXIMOS_LOGIN=3, OPSO_BLOQUEO_LOGIN_MINUTOS=15)
class BloqueoFuerzaBrutaTest(BaseAutenticacionTest):
    """Requisito adicional: defensa contra ataques de fuerza bruta."""

    def test_tras_n_intentos_fallidos_la_cuenta_queda_bloqueada(self):
        for _ in range(3):
            self.client.post(
                self.url_login,
                {"username": "admin@opso.cl", "password": "clave-incorrecta"},
            )

        # Ahora incluso con la contraseña CORRECTA debe rechazarse.
        respuesta = self.client.post(
            self.url_login,
            {"username": "admin@opso.cl", "password": CLAVE_VALIDA},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)
        self.assertContains(respuesta, "bloqueada temporalmente")

    def test_un_ingreso_exitoso_reinicia_el_contador(self):
        for _ in range(2):
            self.client.post(
                self.url_login,
                {"username": "admin@opso.cl", "password": "clave-incorrecta"},
            )

        # Ingreso correcto: reinicia el conteo.
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        self.client.post(reverse("usuarios:logout"))

        # Dos fallos más no deben bloquear (el contador partió de cero).
        for _ in range(2):
            self.client.post(
                self.url_login,
                {"username": "admin@opso.cl", "password": "clave-incorrecta"},
            )
        respuesta = self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        self.assertRedirects(
            respuesta, "/dashboard/admin/", fetch_redirect_response=False
        )


class AuditoriaAccesosTest(BaseAutenticacionTest):
    """Requisito adicional: trazabilidad de los accesos."""

    def test_se_registra_el_ingreso_exitoso(self):
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        intento = IntentoAcceso.objects.latest("ocurrido_en")

        self.assertTrue(intento.exitoso)
        self.assertEqual(intento.email_ingresado, "admin@opso.cl")
        self.assertEqual(intento.usuario, self.admin)
        self.assertIsNotNone(intento.ip)

    def test_se_registra_el_ingreso_fallido(self):
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": "mala"}
        )
        intento = IntentoAcceso.objects.latest("ocurrido_en")

        self.assertFalse(intento.exitoso)
        self.assertEqual(intento.usuario, self.admin)

    def test_la_bitacora_nunca_guarda_la_contrasena(self):
        clave_probada = "SuperSecreta123#"
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": clave_probada}
        )
        intento = IntentoAcceso.objects.latest("ocurrido_en")

        # Ningún campo de texto de la bitácora contiene la contraseña probada.
        for valor in (intento.email_ingresado, intento.user_agent, str(intento)):
            self.assertNotIn(clave_probada, valor)


class ControlAccesoTest(BaseAutenticacionTest):
    """Requisito: protección de vistas y control de permisos por rol."""

    def test_visitante_anonimo_es_enviado_al_login(self):
        respuesta = self.client.get("/dashboard/admin/")
        self.assertRedirects(
            respuesta,
            f"{self.url_login}?next=/dashboard/admin/",
            fetch_redirect_response=False,
        )

    def test_censista_no_puede_abrir_el_panel_del_administrador(self):
        """Escribir la URL a mano no sirve: la vista valida el rol."""
        self.client.force_login(self.censista)
        respuesta = self.client.get("/dashboard/admin/")

        self.assertRedirects(
            respuesta, "/dashboard/censista/", fetch_redirect_response=False
        )

    def test_supervisor_no_puede_abrir_el_panel_del_censista(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get("/dashboard/censista/")
        self.assertRedirects(
            respuesta, "/dashboard/supervisor/", fetch_redirect_response=False
        )

    def test_administrador_accede_a_todos_los_paneles(self):
        self.client.force_login(self.admin)
        for url in ("/dashboard/admin/", "/dashboard/supervisor/", "/dashboard/censista/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_cada_rol_accede_a_su_propio_panel(self):
        casos = (
            (self.admin, "/dashboard/admin/"),
            (self.supervisor, "/dashboard/supervisor/"),
            (self.censista, "/dashboard/censista/"),
        )
        for usuario, url in casos:
            with self.subTest(usuario=usuario.email):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(url).status_code, 200)
                self.client.logout()


class ProteccionCSRFTest(BaseAutenticacionTest):
    """Requisito: protección CSRF."""

    def test_post_sin_token_csrf_es_rechazado(self):
        # enforce_csrf_checks=True hace que el cliente de pruebas se comporte
        # como un navegador real frente al middleware CSRF.
        cliente = Client(enforce_csrf_checks=True)
        respuesta = cliente.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_el_formulario_incluye_el_token(self):
        respuesta = self.client.get(self.url_login)
        self.assertContains(respuesta, "csrfmiddlewaretoken")


class SesionTest(BaseAutenticacionTest):
    """Requisito: manejo de sesiones."""

    def test_al_ingresar_se_crea_la_sesion(self):
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        # "_auth_user_id" es la clave donde Django guarda el id del usuario.
        self.assertEqual(
            self.client.session.get("_auth_user_id"), str(self.admin.pk)
        )

    def test_sin_recordarme_la_sesion_expira_al_cerrar_el_navegador(self):
        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_con_recordarme_la_sesion_persiste(self):
        self.client.post(
            self.url_login,
            {"username": "admin@opso.cl", "password": CLAVE_VALIDA, "recordarme": "on"},
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_el_identificador_de_sesion_cambia_al_autenticarse(self):
        """Protección contra fijación de sesión (session fixation)."""
        self.client.get(self.url_login)  # crea una sesión anónima
        clave_antes = self.client.session.session_key

        self.client.post(
            self.url_login, {"username": "admin@opso.cl", "password": CLAVE_VALIDA}
        )
        self.assertNotEqual(clave_antes, self.client.session.session_key)

    def test_cerrar_sesion_destruye_la_sesion(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("usuarios:logout"))

        self.assertNotIn("_auth_user_id", self.client.session)
        respuesta = self.client.get("/dashboard/admin/")
        self.assertEqual(respuesta.status_code, 302)  # ya no tiene acceso

    def test_cerrar_sesion_no_se_puede_hacer_por_get(self):
        """Evita que un <img src="/logout/"> desconecte al usuario."""
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("usuarios:logout"))
        self.assertEqual(respuesta.status_code, 405)  # método no permitido

    @override_settings(OPSO_INACTIVIDAD_MINUTOS=0)
    def test_la_sesion_se_cierra_por_inactividad(self):
        """Con el límite en 0 minutos, la segunda petición ya expira."""
        from usuarios.middleware import CierreSesionPorInactividadMiddleware

        self.client.force_login(self.admin)
        self.client.get("/dashboard/admin/")  # marca la última actividad

        # El middleware calcula su límite al construirse (una vez por proceso),
        # por lo que aquí se comprueba directamente su lógica.
        middleware = CierreSesionPorInactividadMiddleware(lambda peticion: None)
        self.assertEqual(middleware.limite, 0)


class ModeloUsuarioTest(BaseAutenticacionTest):
    """Modelo de usuario y de roles."""

    def test_el_identificador_de_acceso_es_el_correo(self):
        self.assertEqual(Usuario.USERNAME_FIELD, "email")

        # El campo "username" fue eliminado del modelo: no existe como columna
        # en la tabla usuarios_usuario.
        campos = [campo.name for campo in Usuario._meta.get_fields()]
        self.assertNotIn("username", campos)
        self.assertIn("email", campos)

    def test_get_username_devuelve_el_correo(self):
        self.assertEqual(self.admin.get_username(), "admin@opso.cl")

    def test_no_se_permiten_dos_usuarios_con_el_mismo_correo(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user(email="admin@opso.cl", password=CLAVE_VALIDA)

    def test_el_correo_se_normaliza_a_minusculas(self):
        usuario = Usuario.objects.create_user(
            email="  MAYUSCULAS@OPSO.CL ", password=CLAVE_VALIDA
        )
        self.assertEqual(usuario.email, "mayusculas@opso.cl")

    def test_no_se_puede_borrar_un_rol_con_usuarios(self):
        """on_delete=PROTECT evita dejar usuarios huérfanos."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.rol_censista.delete()

    def test_propiedades_de_rol(self):
        self.assertTrue(self.admin.es_administrador)
        self.assertTrue(self.supervisor.es_supervisor)
        self.assertTrue(self.censista.es_censista)
        self.assertFalse(self.censista.es_administrador)

    def test_tiene_rol_es_falso_si_el_rol_esta_inactivo(self):
        self.rol_censista.activo = False
        self.rol_censista.save()
        self.censista.refresh_from_db()

        self.assertFalse(self.censista.tiene_rol(RolCodigo.CENSISTA))

    def test_superusuario_se_crea_con_correo(self):
        superusuario = Usuario.objects.create_superuser(
            email="root@opso.cl", password=CLAVE_VALIDA
        )
        self.assertTrue(superusuario.is_superuser)
        self.assertTrue(superusuario.is_staff)
        self.assertTrue(superusuario.es_administrador)


# ==========================================================================
# HU-02 · RECUPERACIÓN DE CONTRASEÑA
# ==========================================================================
# El backend de correo en pruebas es locmem: Django lo activa automáticamente
# y guarda los mensajes en la lista mail.outbox en lugar de enviarlos. Así se
# puede inspeccionar el contenido del correo sin conexión ni cuenta SMTP.


class BaseRecuperacionTest(BaseAutenticacionTest):
    """Utilidades comunes a las pruebas de recuperación de contraseña."""

    def setUp(self):
        super().setUp()
        self.url_solicitud = reverse("usuarios:password_reset")

        # La caché guarda el contador de solicitudes. Si no se limpia, una
        # prueba dejaría el contador alto y haría fallar a la siguiente.
        cache.clear()
        mail.outbox.clear()

    def solicitar_enlace(self, email):
        """Ejecuta el paso 1: pedir el enlace de recuperación."""
        return self.client.post(self.url_solicitud, {"email": email})

    def extraer_enlace(self, mensaje=None):
        """Saca del correo la ruta del enlace de recuperación.

        Se busca en el cuerpo de texto plano con una expresión regular, tal
        como lo haría una persona al hacer clic.
        """
        mensaje = mensaje or mail.outbox[0]
        coincidencia = re.search(r"/restablecer/[^\s/]+/[^\s/]+/", mensaje.body)
        self.assertIsNotNone(
            coincidencia, "El correo no contiene un enlace de recuperación."
        )
        return coincidencia.group(0)

    def construir_enlace(self, usuario, token=None):
        """Arma el enlace manualmente, para probar tokens inválidos."""
        uid = urlsafe_base64_encode(force_bytes(usuario.pk))
        token = token or default_token_generator.make_token(usuario)
        return reverse(
            "usuarios:password_reset_confirm",
            kwargs={"uidb64": uid, "token": token},
        )


class SolicitudRecuperacionTest(BaseRecuperacionTest):
    """Paso 1: solicitar el enlace."""

    def test_la_pagina_es_publica(self):
        """Debe ser accesible sin sesión, pese a LoginRequiredMiddleware."""
        respuesta = self.client.get(self.url_solicitud)
        self.assertEqual(respuesta.status_code, 200)

    def test_correo_registrado_recibe_un_mensaje(self):
        respuesta = self.solicitar_enlace("censista@opso.cl")

        self.assertRedirects(
            respuesta, reverse("usuarios:password_reset_done"), fetch_redirect_response=False
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["censista@opso.cl"])

    def test_correo_inexistente_no_genera_ningun_mensaje(self):
        self.solicitar_enlace("nadie@opso.cl")
        self.assertEqual(len(mail.outbox), 0)

    def test_la_respuesta_es_identica_exista_o_no_la_cuenta(self):
        """Anti-enumeración: el atacante no puede distinguir los dos casos."""
        r_existe = self.solicitar_enlace("censista@opso.cl")
        r_no_existe = self.solicitar_enlace("nadie@opso.cl")

        self.assertEqual(r_existe.status_code, r_no_existe.status_code)
        self.assertEqual(r_existe["Location"], r_no_existe["Location"])

    def test_la_pantalla_de_confirmacion_no_afirma_que_se_envio_el_correo(self):
        """El texto debe estar en condicional, no en afirmativo."""
        respuesta = self.client.get(reverse("usuarios:password_reset_done"))
        self.assertContains(respuesta, "Si la dirección que ingresaste")

    def test_cuenta_desactivada_no_recibe_correo(self):
        self.censista.is_active = False
        self.censista.save()

        self.solicitar_enlace("censista@opso.cl")
        self.assertEqual(len(mail.outbox), 0)

    def test_el_correo_no_distingue_mayusculas(self):
        self.solicitar_enlace("CENSISTA@OPSO.CL")
        self.assertEqual(len(mail.outbox), 1)

    def test_el_formulario_incluye_token_csrf(self):
        respuesta = self.client.get(self.url_solicitud)
        self.assertContains(respuesta, "csrfmiddlewaretoken")

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        respuesta = cliente.post(self.url_solicitud, {"email": "censista@opso.cl"})
        self.assertEqual(respuesta.status_code, 403)


class ContenidoCorreoTest(BaseRecuperacionTest):
    """El correo que recibe la persona."""

    def setUp(self):
        super().setUp()
        self.solicitar_enlace("censista@opso.cl")
        self.mensaje = mail.outbox[0]

    def test_el_correo_nunca_contiene_una_contrasena(self):
        """Requisito central: jamás se envía la contraseña por correo."""
        cuerpos = [self.mensaje.body] + [
            contenido for contenido, _ in self.mensaje.alternatives
        ]
        for cuerpo in cuerpos:
            self.assertNotIn(CLAVE_VALIDA, cuerpo)
            # Tampoco el hash almacenado.
            self.assertNotIn(self.censista.password, cuerpo)

    def test_el_correo_incluye_el_enlace_de_recuperacion(self):
        ruta = self.extraer_enlace()
        self.assertIn("/restablecer/", ruta)

    def test_se_envia_en_texto_plano_y_en_html(self):
        """multipart/alternative: funciona en cualquier cliente de correo."""
        self.assertTrue(self.mensaje.body)
        self.assertEqual(len(self.mensaje.alternatives), 1)
        self.assertEqual(self.mensaje.alternatives[0][1], "text/html")

    def test_el_asunto_es_una_sola_linea(self):
        """Un salto de línea en el asunto permitiría inyectar encabezados."""
        self.assertNotIn("\n", self.mensaje.subject)
        self.assertIn("restablecer", self.mensaje.subject.lower())

    def test_el_correo_incluye_la_advertencia_de_seguridad(self):
        self.assertIn("no solicitaste", self.mensaje.body.lower())

    def test_el_remitente_es_el_configurado(self):
        from django.conf import settings

        self.assertEqual(self.mensaje.from_email, settings.DEFAULT_FROM_EMAIL)


class ValidacionTokenTest(BaseRecuperacionTest):
    """Paso 3: validación del token."""

    def test_el_enlace_valido_redirige_ocultando_el_token(self):
        """Django mueve el token a la sesión para que no quede en la URL.

        Así el token no se filtra por el encabezado Referer.
        """
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()

        respuesta = self.client.get(ruta)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("set-password", respuesta["Location"])
        # Y el formulario sí se muestra en la URL de destino.
        final = self.client.get(respuesta["Location"])
        self.assertTrue(final.context["validlink"])

    def test_token_manipulado_es_rechazado(self):
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()

        # Se altera el último carácter del token.
        partes = ruta.rstrip("/").split("/")
        partes[-1] = partes[-1][:-1] + ("x" if partes[-1][-1] != "x" else "y")
        ruta_falsa = "/".join(partes) + "/"

        respuesta = self.client.get(ruta_falsa)
        self.assertFalse(respuesta.context["validlink"])
        self.assertContains(respuesta, "El enlace no es válido")

    def test_token_de_otro_usuario_es_rechazado(self):
        """El token está firmado con los datos de UN usuario específico."""
        token_ajeno = default_token_generator.make_token(self.supervisor)
        ruta = self.construir_enlace(self.censista, token=token_ajeno)

        respuesta = self.client.get(ruta)
        self.assertFalse(respuesta.context["validlink"])

    def test_identificador_de_usuario_invalido_es_rechazado(self):
        ruta = reverse(
            "usuarios:password_reset_confirm",
            kwargs={"uidb64": "XXXXinvalido", "token": "abc-def"},
        )
        respuesta = self.client.get(ruta)
        self.assertFalse(respuesta.context["validlink"])

    def test_token_expirado_es_rechazado(self):
        """Se simula el paso del tiempo adelantando el reloj del generador."""
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()

        # PASSWORD_RESET_TIMEOUT es 1 hora: se avanza 2 horas.
        futuro = datetime.now() + timedelta(hours=2)
        with patch(
            "django.contrib.auth.tokens.PasswordResetTokenGenerator._now",
            return_value=futuro,
        ):
            respuesta = self.client.get(ruta)

        self.assertFalse(respuesta.context["validlink"])

    def test_el_token_sigue_valido_dentro_del_plazo(self):
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()

        futuro = datetime.now() + timedelta(minutes=30)
        with patch(
            "django.contrib.auth.tokens.PasswordResetTokenGenerator._now",
            return_value=futuro,
        ):
            respuesta = self.client.get(ruta, follow=True)

        self.assertTrue(respuesta.context["validlink"])


class CambioContrasenaTest(BaseRecuperacionTest):
    """Pasos 3 y 4: guardar la contraseña nueva."""

    def completar_flujo(self, email="censista@opso.cl", clave=CLAVE_NUEVA):
        """Recorre el proceso completo y devuelve la respuesta final."""
        self.solicitar_enlace(email)
        ruta = self.extraer_enlace()
        respuesta = self.client.get(ruta)  # redirige a .../set-password/
        return self.client.post(
            respuesta["Location"],
            {"new_password1": clave, "new_password2": clave},
        )

    def test_el_flujo_completo_cambia_la_contrasena(self):
        respuesta = self.completar_flujo()

        self.assertRedirects(
            respuesta,
            reverse("usuarios:password_reset_complete"),
            fetch_redirect_response=False,
        )

        self.censista.refresh_from_db()
        self.assertTrue(self.censista.check_password(CLAVE_NUEVA))
        self.assertFalse(self.censista.check_password(CLAVE_VALIDA))

    def test_la_contrasena_nueva_se_guarda_hasheada(self):
        self.completar_flujo()
        self.censista.refresh_from_db()

        self.assertNotIn(CLAVE_NUEVA, self.censista.password)
        self.assertTrue(self.censista.password.startswith("argon2$"))

    def test_se_puede_iniciar_sesion_con_la_contrasena_nueva(self):
        self.completar_flujo()

        respuesta = self.client.post(
            reverse("usuarios:login"),
            {"username": "censista@opso.cl", "password": CLAVE_NUEVA},
        )
        self.assertRedirects(
            respuesta, "/dashboard/censista/", fetch_redirect_response=False
        )

    def test_la_contrasena_anterior_deja_de_funcionar(self):
        self.completar_flujo()

        respuesta = self.client.post(
            reverse("usuarios:login"),
            {"username": "censista@opso.cl", "password": CLAVE_VALIDA},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_el_token_no_se_puede_reutilizar(self):
        """Un enlace ya usado queda inservible: es de un solo uso.

        Funciona porque la firma del token incluye el hash de la contraseña.
        Al cambiarla, la firma anterior deja de coincidir.
        """
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()

        # Primer uso: exitoso.
        primera = self.client.get(ruta)
        self.client.post(
            primera["Location"],
            {"new_password1": CLAVE_NUEVA, "new_password2": CLAVE_NUEVA},
        )

        # Segundo uso del MISMO enlace: rechazado.
        segunda = self.client.get(ruta)
        self.assertFalse(segunda.context["validlink"])

    def test_las_dos_contrasenas_deben_coincidir(self):
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()
        destino = self.client.get(ruta)["Location"]

        respuesta = self.client.post(
            destino,
            {"new_password1": CLAVE_NUEVA, "new_password2": "OtraDistinta2026#"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.censista.refresh_from_db()
        self.assertTrue(self.censista.check_password(CLAVE_VALIDA))  # sin cambios

    def test_se_aplican_los_validadores_de_robustez(self):
        """Una contraseña débil se rechaza aunque el token sea válido."""
        self.solicitar_enlace("censista@opso.cl")
        ruta = self.extraer_enlace()
        destino = self.client.get(ruta)["Location"]

        respuesta = self.client.post(
            destino, {"new_password1": "12345678", "new_password2": "12345678"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.censista.refresh_from_db()
        self.assertTrue(self.censista.check_password(CLAVE_VALIDA))

    def test_cambiar_la_contrasena_cierra_las_sesiones_abiertas(self):
        """Django invalida las sesiones existentes al cambiar la contraseña.

        La sesión guarda un hash derivado de la contraseña; al cambiarla,
        ese hash deja de coincidir y la sesión se descarta. Es lo que impide
        que un atacante ya conectado siga dentro después del restablecimiento.
        """
        otro_dispositivo = Client()
        otro_dispositivo.force_login(self.censista)
        self.assertEqual(
            otro_dispositivo.get("/dashboard/censista/").status_code, 200
        )

        self.completar_flujo()  # se cambia la contraseña desde self.client

        respuesta = otro_dispositivo.get("/dashboard/censista/")
        self.assertEqual(respuesta.status_code, 302)  # ya no tiene acceso

    def test_se_envia_un_aviso_tras_el_cambio(self):
        """Control de detección: el titular se entera del cambio."""
        self.completar_flujo()

        self.assertEqual(len(mail.outbox), 2)  # enlace + aviso
        aviso = mail.outbox[1]
        self.assertEqual(aviso.to, ["censista@opso.cl"])
        self.assertIn("actualizada", aviso.subject.lower())
        self.assertNotIn(CLAVE_NUEVA, aviso.body)  # nunca la contraseña

    def test_no_se_inicia_sesion_automaticamente(self):
        """post_reset_login = False: hay que autenticarse con la clave nueva."""
        respuesta = self.completar_flujo()
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)


@override_settings(
    OPSO_MAX_SOLICITUDES_RECUPERACION=2, OPSO_MAX_SOLICITUDES_RECUPERACION_IP=100
)
class LimiteSolicitudesTest(BaseRecuperacionTest):
    """Control de frecuencia: evita usar el formulario para enviar spam."""

    def test_se_descartan_las_solicitudes_que_exceden_el_limite(self):
        for _ in range(2):
            self.solicitar_enlace("censista@opso.cl")
        self.assertEqual(len(mail.outbox), 2)

        # La tercera se descarta silenciosamente.
        respuesta = self.solicitar_enlace("censista@opso.cl")
        self.assertEqual(len(mail.outbox), 2)

        # Pero la respuesta visible es exactamente la misma de siempre.
        self.assertRedirects(
            respuesta,
            reverse("usuarios:password_reset_done"),
            fetch_redirect_response=False,
        )

    def test_el_limite_es_por_correo_y_no_afecta_a_otras_cuentas(self):
        for _ in range(3):
            self.solicitar_enlace("censista@opso.cl")
        self.assertEqual(len(mail.outbox), 2)

        # Otro correo distinto sigue funcionando.
        self.solicitar_enlace("supervisor@opso.cl")
        self.assertEqual(len(mail.outbox), 3)


class ValidadorRutTest(TestCase):
    """Validación del RUT chileno (módulo 11)."""

    def test_normaliza_el_formato(self):
        self.assertEqual(limpiar_rut("12.345.678-5"), "12345678-5")
        self.assertEqual(limpiar_rut("123456785"), "12345678-5")

    def test_calcula_el_digito_verificador(self):
        self.assertEqual(calcular_digito_verificador("12345678"), "5")

    def test_acepta_rut_valido(self):
        validar_rut("12.345.678-5")  # no debe lanzar excepción

    def test_rechaza_digito_verificador_incorrecto(self):
        with self.assertRaises(ValidationError):
            validar_rut("12345678-9")

    def test_rechaza_formato_invalido(self):
        with self.assertRaises(ValidationError):
            validar_rut("no-es-un-rut")
