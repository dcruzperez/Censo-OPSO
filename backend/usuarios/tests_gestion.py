"""Pruebas automáticas de la HU-03 «Administración de usuarios».

Se separan de tests.py (que cubre la HU-01 y la HU-02) para que cada historia
de usuario tenga su evidencia identificable: en la defensa se puede ejecutar
solo este archivo y mostrar qué cubre.

    python manage.py test usuarios.tests_gestion

Cada prueba sigue el patrón PREPARAR -> ACTUAR -> VERIFICAR y su nombre describe
la regla que comprueba, para que la salida del comando se lea como una lista de
requisitos cumplidos.
"""

from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from .forms_gestion import EditarUsuarioForm
from .models import AccionAuditoria, RegistroAuditoria, Rol, RolCodigo, Usuario

CLAVE_VALIDA = "Censo2026#Opso"


class BaseGestionTest(TestCase):
    """Escenario común: un administrador, un supervisor y un censista."""

    @classmethod
    def setUpTestData(cls):
        # Los roles ya existen: los sembró la migración de datos 0002.
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
        # Un segundo administrador: sin él, cualquier prueba que intente
        # deshabilitar al primero chocaría con la regla del "último
        # administrador activo" y estaríamos probando otra cosa.
        cls.admin2 = Usuario.objects.create_user(
            email="admin2@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Bruno",
            last_name="Vega",
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
        self.url_lista = reverse("usuarios:lista")
        self.url_crear = reverse("usuarios:crear")

    # -- ayudantes ----------------------------------------------------------

    def autenticar(self, usuario):
        self.client.force_login(usuario)

    def datos_creacion(self, **cambios):
        """Devuelve un POST válido para el formulario de creación."""
        datos = {
            "first_name": "Nuevo",
            "last_name": "Censista",
            "email": "nuevo@opso.cl",
            "nombre_usuario": "ncensista",
            "rut": "",
            "telefono": "",
            "rol": self.rol_censista.pk,
            "is_active": "True",
            "metodo_clave": "enlace",
            "password1": "",
            "password2": "",
        }
        datos.update(cambios)
        return datos

    def datos_edicion(self, usuario, **cambios):
        """Devuelve un POST válido para el formulario de edición."""
        datos = {
            "first_name": usuario.first_name,
            "last_name": usuario.last_name,
            "email": usuario.email,
            "nombre_usuario": usuario.nombre_usuario or "",
            "rut": usuario.rut or "",
            "telefono": usuario.telefono,
            "rol": usuario.rol_id or "",
            "is_active": "True" if usuario.is_active else "False",
        }
        datos.update(cambios)
        return datos


# ==========================================================================
# 1. CONTROL DE ACCESO
# ==========================================================================


class AccesoAlModuloTest(BaseGestionTest):
    """Requisito: solo el rol Administrador administra usuarios."""

    def test_visitante_anonimo_es_enviado_al_login(self):
        respuesta = self.client.get(self.url_lista)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta.url)
        # El ?next= permite volver a la página pedida después de autenticarse.
        self.assertIn("next=", respuesta.url)

    def test_administrador_accede_al_listado(self):
        self.autenticar(self.admin)

        respuesta = self.client.get(self.url_lista)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "usuarios/gestion/usuarios_list.html")

    def test_censista_no_accede_al_listado(self):
        self.autenticar(self.censista)

        respuesta = self.client.get(self.url_lista)

        # RolRequeridoMixin lo devuelve a SU panel con un mensaje de error.
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("dashboards:censista"))

    def test_supervisor_no_accede_al_listado(self):
        self.autenticar(self.supervisor)

        respuesta = self.client.get(self.url_lista)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("dashboards:supervisor"))

    def test_censista_no_puede_crear_usuarios_por_url(self):
        """Escribir la URL a mano no sirve: la protección está en la vista."""
        self.autenticar(self.censista)
        antes = Usuario.objects.count()

        respuesta = self.client.post(self.url_crear, self.datos_creacion())

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Usuario.objects.count(), antes)

    def test_censista_no_puede_deshabilitar_por_url(self):
        """El ataque más obvio: adivinar /usuarios/<id>/deshabilitar/."""
        self.autenticar(self.censista)
        url = reverse("usuarios:deshabilitar", kwargs={"pk": self.supervisor.pk})

        respuesta = self.client.post(url)

        self.assertEqual(respuesta.status_code, 302)
        self.supervisor.refresh_from_db()
        self.assertTrue(self.supervisor.is_active)

    def test_todas_las_rutas_del_modulo_exigen_rol_administrador(self):
        """Barrido completo: ninguna ruta del módulo queda desprotegida."""
        self.autenticar(self.censista)

        rutas = [
            reverse("usuarios:lista"),
            reverse("usuarios:crear"),
            reverse("usuarios:auditoria"),
            reverse("usuarios:detalle", kwargs={"pk": self.admin.pk}),
            reverse("usuarios:editar", kwargs={"pk": self.admin.pk}),
            reverse("usuarios:deshabilitar", kwargs={"pk": self.admin.pk}),
            reverse("usuarios:habilitar", kwargs={"pk": self.admin.pk}),
        ]

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertIn(respuesta.status_code, (302, 403))


class ProteccionCSRFTest(BaseGestionTest):
    """Requisito: protección CSRF en todas las operaciones de escritura."""

    def test_post_sin_token_csrf_es_rechazado(self):
        # enforce_csrf_checks=True desactiva la exención que el cliente de
        # pruebas aplica por comodidad, para poder comprobar la defensa real.
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        url = reverse("usuarios:deshabilitar", kwargs={"pk": self.censista.pk})

        respuesta = cliente.post(url)

        self.assertEqual(respuesta.status_code, 403)
        self.censista.refresh_from_db()
        self.assertTrue(self.censista.is_active)


# ==========================================================================
# 2. CREAR USUARIO
# ==========================================================================


class CrearUsuarioTest(BaseGestionTest):
    """Requisito: crear cuentas indicando nombre, correo, rol y estado."""

    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)

    def test_crea_el_usuario_y_lo_guarda_en_la_base_de_datos(self):
        respuesta = self.client.post(self.url_crear, self.datos_creacion())

        self.assertRedirects(respuesta, self.url_lista)

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        self.assertEqual(creado.first_name, "Nuevo")
        self.assertEqual(creado.rol, self.rol_censista)
        self.assertTrue(creado.is_active)

    def test_la_contrasena_nunca_se_guarda_en_texto_plano(self):
        self.client.post(
            self.url_crear,
            self.datos_creacion(
                metodo_clave="manual",
                password1="ClaveInicial2026#",
                password2="ClaveInicial2026#",
            ),
        )

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        self.assertNotIn("ClaveInicial2026#", creado.password)
        # Formato de Django: algoritmo$parámetros$sal$hash
        self.assertTrue(creado.password.startswith("argon2$"))
        # Y la contraseña definida sí funciona.
        self.assertTrue(creado.check_password("ClaveInicial2026#"))

    def test_con_el_metodo_enlace_se_envia_un_correo_de_activacion(self):
        self.client.post(self.url_crear, self.datos_creacion())

        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, ["nuevo@opso.cl"])
        self.assertIn("activa tu cuenta", mensaje.subject.lower())
        # El enlace apunta a la vista de la HU-02 que ya sabe validar el token.
        self.assertIn("/restablecer/", mensaje.body)

    def test_con_el_metodo_enlace_la_clave_asignada_es_inutilizable_en_la_practica(self):
        self.client.post(self.url_crear, self.datos_creacion())

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        # La cuenta tiene una contraseña VÁLIDA (para que el flujo de
        # recuperación la acepte) pero aleatoria: nadie la conoce.
        self.assertTrue(creado.has_usable_password())
        self.assertFalse(creado.check_password(CLAVE_VALIDA))

    def test_registra_la_creacion_en_la_bitacora_de_auditoria(self):
        self.client.post(self.url_crear, self.datos_creacion())

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        registro = RegistroAuditoria.objects.get(usuario_afectado=creado)

        self.assertEqual(registro.accion, AccionAuditoria.CREAR)
        self.assertEqual(registro.administrador, self.admin)
        self.assertEqual(registro.administrador_email, self.admin.email)
        self.assertIn("Censista", registro.detalle)

    def test_rechaza_un_correo_duplicado(self):
        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(email="censista@opso.cl")
        )

        self.assertEqual(respuesta.status_code, 200)  # vuelve al formulario
        self.assertFormError(
            respuesta.context["form"],
            "email",
            "Ya existe una cuenta registrada con este correo electrónico.",
        )

    def test_rechaza_un_correo_duplicado_escrito_con_mayusculas(self):
        """PostgreSQL distingue mayúsculas: la validación no debe hacerlo."""
        antes = Usuario.objects.count()

        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(email="CENSISTA@OPSO.CL")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Usuario.objects.count(), antes)

    def test_rechaza_un_nombre_de_usuario_duplicado(self):
        Usuario.objects.filter(pk=self.censista.pk).update(nombre_usuario="msoto")

        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(nombre_usuario="msoto")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFormError(
            respuesta.context["form"],
            "nombre_usuario",
            "Este nombre de usuario ya está en uso. Elige otro.",
        )

    def test_exige_nombre_y_apellido(self):
        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(first_name="", last_name="")
        )

        self.assertEqual(respuesta.status_code, 200)
        formulario = respuesta.context["form"]
        self.assertIn("first_name", formulario.errors)
        self.assertIn("last_name", formulario.errors)

    def test_rechaza_un_correo_con_formato_invalido(self):
        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(email="esto-no-es-un-correo")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("email", respuesta.context["form"].errors)

    def test_rechaza_un_rut_con_digito_verificador_invalido(self):
        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(rut="12345678-0")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("rut", respuesta.context["form"].errors)

    def test_rechaza_una_contrasena_demasiado_corta(self):
        """MinimumLengthValidator: mínimo 10 caracteres (settings.py)."""
        respuesta = self.client.post(
            self.url_crear,
            self.datos_creacion(metodo_clave="manual", password1="Ab3#", password2="Ab3#"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("password1", respuesta.context["form"].errors)

    def test_rechaza_una_contrasena_comun(self):
        """CommonPasswordValidator: lista de las 20.000 más usadas."""
        respuesta = self.client.post(
            self.url_crear,
            self.datos_creacion(
                metodo_clave="manual", password1="password123", password2="password123"
            ),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("password1", respuesta.context["form"].errors)

    def test_rechaza_contrasenas_que_no_coinciden(self):
        respuesta = self.client.post(
            self.url_crear,
            self.datos_creacion(
                metodo_clave="manual",
                password1="ClaveInicial2026#",
                password2="OtraClave2026#",
            ),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFormError(
            respuesta.context["form"], "password2", "Las dos contraseñas no coinciden."
        )

    def test_exige_la_contrasena_si_se_eligio_definirla_manualmente(self):
        respuesta = self.client.post(
            self.url_crear, self.datos_creacion(metodo_clave="manual")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("password1", respuesta.context["form"].errors)

    def test_propone_un_nombre_de_usuario_cuando_se_deja_vacio(self):
        self.client.post(
            self.url_crear,
            self.datos_creacion(
                first_name="Carla", last_name="Núñez", nombre_usuario=""
            ),
        )

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        # "Carla Núñez" -> "cnuez" (se descartan los caracteres no ASCII).
        self.assertTrue(creado.nombre_usuario)
        self.assertNotIn(" ", creado.nombre_usuario)
        self.assertEqual(creado.nombre_usuario, creado.nombre_usuario.lower())

    def test_normaliza_el_correo_a_minusculas(self):
        self.client.post(self.url_crear, self.datos_creacion(email="Nuevo@OPSO.CL"))

        self.assertTrue(Usuario.objects.filter(email="nuevo@opso.cl").exists())

    def test_puede_crear_el_usuario_directamente_inactivo(self):
        self.client.post(self.url_crear, self.datos_creacion(is_active="False"))

        creado = Usuario.objects.get(email="nuevo@opso.cl")
        self.assertFalse(creado.is_active)


# ==========================================================================
# 3. EDITAR USUARIO
# ==========================================================================


class EditarUsuarioTest(BaseGestionTest):
    """Requisito: modificar nombre, apellido, correo, rol y estado."""

    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)
        self.url = reverse("usuarios:editar", kwargs={"pk": self.censista.pk})

    def test_guarda_los_cambios_en_postgresql(self):
        respuesta = self.client.post(
            self.url,
            self.datos_edicion(
                self.censista, first_name="Marta Elena", telefono="+56911112222"
            ),
        )

        self.assertRedirects(
            respuesta, reverse("usuarios:detalle", kwargs={"pk": self.censista.pk})
        )
        self.censista.refresh_from_db()
        self.assertEqual(self.censista.first_name, "Marta Elena")
        self.assertEqual(self.censista.telefono, "+56911112222")

    def test_permite_cambiar_el_rol(self):
        self.client.post(
            self.url, self.datos_edicion(self.censista, rol=self.rol_supervisor.pk)
        )

        self.censista.refresh_from_db()
        self.assertEqual(self.censista.rol, self.rol_supervisor)

    def test_el_cambio_de_rol_se_registra_como_accion_propia(self):
        self.client.post(
            self.url, self.datos_edicion(self.censista, rol=self.rol_supervisor.pk)
        )

        registro = RegistroAuditoria.objects.get(
            usuario_afectado=self.censista, accion=AccionAuditoria.CAMBIAR_ROL
        )
        self.assertIn("Censista", registro.detalle)
        self.assertIn("Supervisor", registro.detalle)

    def test_registra_en_la_auditoria_el_valor_anterior_y_el_nuevo(self):
        self.client.post(
            self.url, self.datos_edicion(self.censista, first_name="Marta Elena")
        )

        registro = RegistroAuditoria.objects.get(
            usuario_afectado=self.censista, accion=AccionAuditoria.EDITAR
        )
        self.assertIn("Marta", registro.detalle)
        self.assertIn("Marta Elena", registro.detalle)

    def test_no_registra_nada_si_no_cambio_ningun_dato(self):
        self.client.post(self.url, self.datos_edicion(self.censista))

        self.assertFalse(
            RegistroAuditoria.objects.filter(usuario_afectado=self.censista).exists()
        )

    def test_rechaza_un_correo_que_ya_usa_otra_persona(self):
        respuesta = self.client.post(
            self.url, self.datos_edicion(self.censista, email="supervisor@opso.cl")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("email", respuesta.context["form"].errors)
        self.censista.refresh_from_db()
        self.assertEqual(self.censista.email, "censista@opso.cl")

    def test_puede_conservar_su_propio_correo_sin_error_de_duplicado(self):
        """Al editar, la comprobación de unicidad debe excluir al propio usuario."""
        respuesta = self.client.post(
            self.url, self.datos_edicion(self.censista, first_name="Marta E.")
        )

        self.assertEqual(respuesta.status_code, 302)

    def test_no_puede_cambiar_su_propio_rol(self):
        """Protección contra la autodegradación (lockout)."""
        url_propia = reverse("usuarios:editar", kwargs={"pk": self.admin.pk})

        self.client.post(
            url_propia, self.datos_edicion(self.admin, rol=self.rol_censista.pk)
        )

        self.admin.refresh_from_db()
        # El campo está disabled: Django ignora el valor enviado y conserva el
        # original. La protección no depende del HTML del navegador.
        self.assertEqual(self.admin.rol, self.rol_admin)

    def test_no_puede_desactivarse_a_si_mismo_desde_el_formulario(self):
        url_propia = reverse("usuarios:editar", kwargs={"pk": self.admin.pk})

        self.client.post(url_propia, self.datos_edicion(self.admin, is_active="False"))

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_un_administrador_comun_no_puede_editar_a_un_superusuario(self):
        superusuario = Usuario.objects.create_superuser(
            email="root@opso.cl", password=CLAVE_VALIDA
        )
        url = reverse("usuarios:editar", kwargs={"pk": superusuario.pk})

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 403)

    def test_devuelve_404_si_el_usuario_no_existe(self):
        respuesta = self.client.get(reverse("usuarios:editar", kwargs={"pk": 99999}))

        self.assertEqual(respuesta.status_code, 404)


# ==========================================================================
# 4. DESHABILITAR Y HABILITAR (borrado lógico)
# ==========================================================================


class DeshabilitarUsuarioTest(BaseGestionTest):
    """Requisito: deshabilitación lógica, nunca borrado físico."""

    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)
        self.url = reverse("usuarios:deshabilitar", kwargs={"pk": self.censista.pk})

    def test_el_get_muestra_la_pantalla_de_confirmacion_sin_modificar_nada(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(
            respuesta, "usuarios/gestion/usuario_confirmar_estado.html"
        )
        self.censista.refresh_from_db()
        self.assertTrue(self.censista.is_active)  # el GET no cambió nada

    def test_el_post_desactiva_la_cuenta(self):
        respuesta = self.client.post(self.url)

        self.assertRedirects(
            respuesta, reverse("usuarios:detalle", kwargs={"pk": self.censista.pk})
        )
        self.censista.refresh_from_db()
        self.assertFalse(self.censista.is_active)

    def test_no_borra_la_fila_ni_pierde_ningun_dato(self):
        total_antes = Usuario.objects.count()

        self.client.post(self.url)

        self.assertEqual(Usuario.objects.count(), total_antes)
        conservado = Usuario.objects.get(pk=self.censista.pk)
        self.assertEqual(conservado.email, "censista@opso.cl")
        self.assertEqual(conservado.first_name, "Marta")
        self.assertEqual(conservado.rol, self.rol_censista)

    def test_registra_la_deshabilitacion_en_la_auditoria(self):
        self.client.post(self.url)

        registro = RegistroAuditoria.objects.get(usuario_afectado=self.censista)
        self.assertEqual(registro.accion, AccionAuditoria.DESHABILITAR)
        self.assertEqual(registro.administrador, self.admin)

    def test_el_usuario_deshabilitado_no_puede_iniciar_sesion(self):
        self.client.post(self.url)
        self.client.logout()

        respuesta = self.client.post(
            reverse("usuarios:login"),
            {"username": "censista@opso.cl", "password": CLAVE_VALIDA},
        )

        self.assertEqual(respuesta.status_code, 200)  # se queda en el login
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_el_usuario_deshabilitado_no_puede_recuperar_su_contrasena(self):
        """Django excluye las cuentas inactivas del flujo de recuperación."""
        self.client.post(self.url)
        self.client.logout()
        mail.outbox.clear()

        self.client.post(
            reverse("usuarios:password_reset"), {"email": "censista@opso.cl"}
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_no_puede_deshabilitarse_a_si_mismo(self):
        url_propia = reverse("usuarios:deshabilitar", kwargs={"pk": self.admin.pk})

        respuesta = self.client.post(url_propia)

        self.assertEqual(respuesta.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_un_administrador_comun_no_puede_deshabilitar_a_un_superusuario(self):
        superusuario = Usuario.objects.create_superuser(
            email="root@opso.cl", password=CLAVE_VALIDA
        )
        url = reverse("usuarios:deshabilitar", kwargs={"pk": superusuario.pk})

        respuesta = self.client.post(url)

        self.assertEqual(respuesta.status_code, 403)
        superusuario.refresh_from_db()
        self.assertTrue(superusuario.is_active)

    def test_deshabilitar_una_cuenta_ya_inactiva_no_duplica_la_auditoria(self):
        self.client.post(self.url)  # primera vez: sí registra
        self.client.post(self.url)  # segunda vez: la validación lo impide

        self.assertEqual(
            RegistroAuditoria.objects.filter(
                usuario_afectado=self.censista, accion=AccionAuditoria.DESHABILITAR
            ).count(),
            1,
        )


class HabilitarUsuarioTest(BaseGestionTest):
    """Requisito: reactivar una cuenta deshabilitada."""

    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)
        Usuario.objects.filter(pk=self.censista.pk).update(is_active=False)
        self.censista.refresh_from_db()
        self.url = reverse("usuarios:habilitar", kwargs={"pk": self.censista.pk})

    def test_el_post_reactiva_la_cuenta(self):
        self.client.post(self.url)

        self.censista.refresh_from_db()
        self.assertTrue(self.censista.is_active)

    def test_registra_la_habilitacion_en_la_auditoria(self):
        self.client.post(self.url)

        registro = RegistroAuditoria.objects.get(usuario_afectado=self.censista)
        self.assertEqual(registro.accion, AccionAuditoria.HABILITAR)

    def test_tras_reactivarla_puede_volver_a_iniciar_sesion_con_su_clave_de_siempre(self):
        self.client.post(self.url)
        self.client.logout()

        respuesta = self.client.post(
            reverse("usuarios:login"),
            {"username": "censista@opso.cl", "password": CLAVE_VALIDA},
        )

        self.assertEqual(respuesta.status_code, 302)  # entró
        self.assertTrue(respuesta.wsgi_request.user.is_authenticated)


# ==========================================================================
# 5. LISTADO: BÚSQUEDA, FILTROS Y PAGINACIÓN
# ==========================================================================


class ListadoUsuariosTest(BaseGestionTest):
    """Requisitos de usabilidad: buscar, filtrar y paginar."""

    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)

    def test_muestra_todos_los_usuarios_sin_filtros(self):
        respuesta = self.client.get(self.url_lista)

        self.assertEqual(respuesta.context["total_usuarios"], Usuario.objects.count())

    def test_busca_por_apellido(self):
        respuesta = self.client.get(self.url_lista, {"q": "Soto"})

        encontrados = list(respuesta.context["usuarios"])
        self.assertEqual(encontrados, [self.censista])

    def test_busca_por_correo_sin_distinguir_mayusculas(self):
        respuesta = self.client.get(self.url_lista, {"q": "SUPERVISOR@"})

        self.assertIn(self.supervisor, list(respuesta.context["usuarios"]))

    def test_filtra_por_rol(self):
        respuesta = self.client.get(self.url_lista, {"rol": self.rol_censista.pk})

        for usuario in respuesta.context["usuarios"]:
            self.assertEqual(usuario.rol, self.rol_censista)

    def test_filtra_por_estado_inactivo(self):
        Usuario.objects.filter(pk=self.censista.pk).update(is_active=False)

        respuesta = self.client.get(self.url_lista, {"estado": "inactivos"})

        encontrados = list(respuesta.context["usuarios"])
        self.assertEqual(encontrados, [self.censista])

    def test_un_filtro_invalido_no_rompe_la_pagina(self):
        """?rol=abc no es un id válido: el formulario lo descarta."""
        respuesta = self.client.get(self.url_lista, {"rol": "abc"})

        self.assertEqual(respuesta.status_code, 200)

    def test_pagina_los_resultados_de_diez_en_diez(self):
        # Ya hay 4 usuarios; se agregan 12 más para superar dos páginas.
        for numero in range(12):
            Usuario.objects.create_user(
                email=f"censista{numero}@opso.cl",
                password=CLAVE_VALIDA,
                first_name=f"Persona{numero:02d}",
                last_name="Prueba",
                rol=self.rol_censista,
            )

        respuesta = self.client.get(self.url_lista)

        self.assertTrue(respuesta.context["is_paginated"])
        self.assertEqual(len(respuesta.context["usuarios"]), 10)
        self.assertEqual(respuesta.context["page_obj"].paginator.count, 16)

    def test_la_paginacion_conserva_los_filtros(self):
        respuesta = self.client.get(self.url_lista, {"q": "Prueba", "page": 1})

        # "parametros" es el querystring sin el número de página.
        self.assertIn("q=Prueba", respuesta.context["parametros"])
        self.assertNotIn("page", respuesta.context["parametros"])


# ==========================================================================
# 6. FICHA, ENVÍO DE ENLACE Y AUDITORÍA
# ==========================================================================


class FichaUsuarioTest(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)

    def test_la_ficha_muestra_los_datos_y_el_historial(self):
        url = reverse("usuarios:detalle", kwargs={"pk": self.censista.pk})

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["usuario"], self.censista)
        self.assertIn("accesos", respuesta.context)
        self.assertIn("auditoria", respuesta.context)

    def test_la_ficha_nunca_muestra_el_hash_de_la_contrasena(self):
        url = reverse("usuarios:detalle", kwargs={"pk": self.censista.pk})

        respuesta = self.client.get(url)

        self.assertNotContains(respuesta, self.censista.password)


class EnviarEnlaceTest(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)
        self.url = reverse("usuarios:enviar_enlace", kwargs={"pk": self.censista.pk})

    def test_envia_el_correo_y_lo_registra_en_la_auditoria(self):
        self.client.post(self.url)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["censista@opso.cl"])
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                usuario_afectado=self.censista, accion=AccionAuditoria.ENVIAR_ENLACE
            ).exists()
        )

    def test_no_cambia_la_contrasena_del_usuario(self):
        """Enviar el enlace es inofensivo: la clave actual sigue sirviendo."""
        hash_antes = Usuario.objects.get(pk=self.censista.pk).password

        self.client.post(self.url)

        self.assertEqual(Usuario.objects.get(pk=self.censista.pk).password, hash_antes)

    def test_no_envia_el_enlace_a_una_cuenta_deshabilitada(self):
        Usuario.objects.filter(pk=self.censista.pk).update(is_active=False)

        self.client.post(self.url)

        self.assertEqual(len(mail.outbox), 0)


class UltimoAdministradorTest(BaseGestionTest):
    """Requisito implícito pero crítico: el sistema no puede quedar sin administradores.

    NOTA HONESTA SOBRE ESTA REGLA: por la interfaz web es muy difícil llegar a
    ella, porque quien administra ES un administrador activo, así que nunca hay
    "un único administrador" distinto de él mismo (y desactivarse a sí mismo ya
    está bloqueado por otra regla anterior). Se mantiene igual como SEGUNDA
    BARRERA: protege ante manipulación directa de la base de datos, ante un
    comando de gestión futuro y ante cambios de código que hoy no existen.

    Por eso estas pruebas atacan el modelo y el formulario directamente, que es
    donde la regla vive, en vez de simular una petición HTTP imposible.
    """

    def test_detecta_correctamente_al_ultimo_administrador_activo(self):
        Usuario.objects.filter(pk=self.admin2.pk).update(is_active=False)
        self.admin.refresh_from_db()

        self.assertTrue(self.admin.es_ultimo_administrador_activo())
        self.assertFalse(self.censista.es_ultimo_administrador_activo())

    def test_con_dos_administradores_activos_ninguno_es_el_ultimo(self):
        self.assertFalse(self.admin.es_ultimo_administrador_activo())
        self.assertFalse(self.admin2.es_ultimo_administrador_activo())

    def test_el_formulario_impide_desactivar_al_ultimo_administrador(self):
        Usuario.objects.filter(pk=self.admin2.pk).update(is_active=False)
        self.admin.refresh_from_db()

        formulario = EditarUsuarioForm(
            data=self.datos_edicion(self.admin, is_active="False"),
            instance=self.admin,
            usuario_actual=self.admin2,  # otro administrador, no él mismo
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("is_active", formulario.errors)

    def test_el_formulario_impide_degradar_al_ultimo_administrador(self):
        Usuario.objects.filter(pk=self.admin2.pk).update(is_active=False)
        self.admin.refresh_from_db()

        formulario = EditarUsuarioForm(
            data=self.datos_edicion(self.admin, rol=self.rol_censista.pk),
            instance=self.admin,
            usuario_actual=self.admin2,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("rol", formulario.errors)


class BitacoraAuditoriaTest(BaseGestionTest):
    def setUp(self):
        super().setUp()
        self.autenticar(self.admin)

    def test_la_bitacora_lista_las_acciones_registradas(self):
        self.client.post(self.url_crear, self.datos_creacion())

        respuesta = self.client.get(reverse("usuarios:auditoria"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_registros"], 1)

    def test_la_bitacora_guarda_la_ip_de_origen(self):
        self.client.post(
            self.url_crear, self.datos_creacion(), REMOTE_ADDR="192.168.10.25"
        )

        registro = RegistroAuditoria.objects.first()
        self.assertEqual(registro.ip, "192.168.10.25")

    def test_el_registro_sobrevive_a_la_eliminacion_del_usuario_afectado(self):
        """SET_NULL + copia del correo: la evidencia no se pierde."""
        self.client.post(self.url_crear, self.datos_creacion())
        creado = Usuario.objects.get(email="nuevo@opso.cl")

        creado.delete()  # borrado físico, solo para probar la resistencia

        registro = RegistroAuditoria.objects.get(accion=AccionAuditoria.CREAR)
        self.assertIsNone(registro.usuario_afectado)
        self.assertEqual(registro.usuario_afectado_email, "nuevo@opso.cl")
