"""Pruebas automáticas de la HU-04 «Asignar roles y permisos».

Se separan de tests.py (HU-01 y HU-02) y de tests_gestion.py (HU-03) para que
cada historia de usuario tenga su evidencia identificable: en la defensa se puede
ejecutar solo este archivo y mostrar qué cubre.

    python manage.py test usuarios.tests_permisos

Cada prueba sigue el patrón PREPARAR -> ACTUAR -> VERIFICAR y su nombre describe
la regla que comprueba, para que la salida del comando se lea como una lista de
requisitos cumplidos.

Al final del archivo se define un URLconf de prueba con vistas de juguete. Es la
forma de probar PermisoRequeridoMixin y el decorador permiso_requerido sin
ensuciar las URLs reales de OPSO con rutas que solo existen para los test.
"""

from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import path, reverse
from django.views import View

from .auditoria import describir_cambio_permisos, registrar_accion
from .decorators import permiso_requerido
from .forms_permisos import PermisosRolForm
from .mixins import PermisoRequeridoMixin
from .models import (
    AccionAuditoria,
    ModuloPermiso,
    Permiso,
    RegistroAuditoria,
    Rol,
    RolCodigo,
    Usuario,
)

CLAVE_VALIDA = "Censo2026#Opso"

#: URLconf usado por las pruebas del mixin y del decorador (ver el final).
URLCONF_PRUEBA = "usuarios.tests_permisos"


class BasePermisosTest(TestCase):
    """Escenario común: los tres roles con su reparto inicial y una cuenta de cada."""

    @classmethod
    def setUpTestData(cls):
        # Roles y permisos ya existen: los sembraron las migraciones de datos
        # 0002 y 0005. Que las pruebas dependan de ellas es deliberado: si
        # alguien rompe la siembra, estas pruebas lo detectan.
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
        cls.sin_rol = Usuario.objects.create_user(
            email="sinrol@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Sin",
            last_name="Rol",
        )

    def setUp(self):
        self.url_matriz = reverse("usuarios:permisos")

    # -- ayudantes ----------------------------------------------------------

    def datos_matriz(self, **permisos_por_rol):
        """Arma un POST para la matriz a partir de {rol: [codigos]}.

        Los roles no mencionados se envían con su reparto actual, para que la
        prueba solo modifique lo que declara: si se omitiera un rol, el POST lo
        dejaría sin permisos y la prueba estaría midiendo un cambio que no quiso.
        """
        datos = {}
        for rol in Rol.objects.all():
            if rol.concede_todo:
                continue  # no tiene formulario: no se envía
            campo = f"{PermisosRolForm.prefijo_de(rol)}-permisos"
            if rol.codigo in permisos_por_rol:
                codigos = permisos_por_rol[rol.codigo]
                datos[campo] = list(
                    Permiso.objects.filter(codigo__in=codigos).values_list(
                        "pk", flat=True
                    )
                )
            else:
                datos[campo] = list(rol.permisos.values_list("pk", flat=True))
        return datos

    def codigos_de(self, rol):
        rol.refresh_from_db()
        return set(rol.permisos.values_list("codigo", flat=True))


# ==========================================================================
# 1. EL MODELO Permiso
# ==========================================================================


class PermisoModeloTest(BasePermisosTest):
    """El catálogo de permisos y sus restricciones."""

    def test_la_migracion_siembra_el_catalogo_completo(self):
        self.assertEqual(Permiso.objects.count(), 20)

    def test_todos_los_permisos_nacen_activos(self):
        self.assertEqual(Permiso.objects.filter(activo=True).count(), 20)

    def test_el_codigo_es_unico(self):
        with self.assertRaises(IntegrityError):
            # atomic() aísla el fallo: sin esto la transacción de la prueba
            # quedaría abortada y las comprobaciones siguientes fallarían.
            with transaction.atomic():
                Permiso.objects.create(
                    codigo="fichas.validar", nombre="Duplicado", modulo="FICHAS"
                )

    def test_el_modulo_solo_admite_valores_del_catalogo(self):
        """La restricción vive en la BASE DE DATOS, no solo en el formulario."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Permiso.objects.create(
                    codigo="inventado.accion", nombre="Inventado", modulo="INVENTADO"
                )

    def test_str_devuelve_el_nombre_visible(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        self.assertEqual(str(permiso), "Validar o rechazar una ficha levantada")

    def test_etiqueta_modulo_traduce_el_codigo_a_texto_legible(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        self.assertEqual(permiso.etiqueta_modulo, "Fichas de familias")

    def test_todos_los_codigos_siguen_el_formato_modulo_punto_accion(self):
        for codigo in Permiso.objects.values_list("codigo", flat=True):
            self.assertIn(".", codigo, f"El código «{codigo}» no tiene punto.")
            self.assertEqual(codigo, codigo.lower())

    def test_el_orden_por_defecto_agrupa_por_modulo(self):
        modulos = list(Permiso.objects.values_list("modulo", flat=True))
        # Agrupado significa que cada módulo aparece en un solo tramo contiguo.
        tramos = [m for i, m in enumerate(modulos) if i == 0 or modulos[i - 1] != m]
        self.assertEqual(len(tramos), len(set(tramos)))

    def test_dentro_de_un_modulo_se_ordena_por_el_campo_orden(self):
        ordenes = list(
            Permiso.objects.filter(modulo=ModuloPermiso.USUARIOS).values_list(
                "orden", flat=True
            )
        )
        self.assertEqual(ordenes, sorted(ordenes))

    def test_hay_permisos_de_los_seis_modulos(self):
        modulos = set(Permiso.objects.values_list("modulo", flat=True))
        self.assertEqual(modulos, set(ModuloPermiso.values))


# ==========================================================================
# 2. LA RELACIÓN Rol <-> Permiso
# ==========================================================================


class RolPermisosTest(BasePermisosTest):
    """El reparto inicial y los ayudantes del modelo Rol."""

    def test_el_administrador_recibe_todos_los_permisos(self):
        self.assertEqual(self.rol_admin.permisos.count(), Permiso.objects.count())

    def test_el_supervisor_puede_validar_fichas(self):
        self.assertIn("fichas.validar", self.codigos_de(self.rol_supervisor))

    def test_el_supervisor_no_puede_crear_cuentas(self):
        """Mínimo privilegio: coordinar terreno no requiere administrar usuarios."""
        self.assertNotIn("usuarios.crear", self.codigos_de(self.rol_supervisor))

    def test_el_censista_solo_tiene_permisos_de_sus_propias_fichas(self):
        self.assertEqual(
            self.codigos_de(self.rol_censista),
            {"fichas.ver_propias", "fichas.crear", "fichas.editar"},
        )

    def test_el_censista_no_puede_validar_su_propio_trabajo(self):
        """Si validara lo suyo se anularía el control cruzado del censo."""
        self.assertNotIn("fichas.validar", self.codigos_de(self.rol_censista))

    def test_el_censista_no_ve_las_fichas_de_los_demas(self):
        self.assertNotIn("fichas.ver_todas", self.codigos_de(self.rol_censista))

    def test_concede_todo_solo_es_verdadero_para_el_administrador(self):
        self.assertTrue(self.rol_admin.concede_todo)
        self.assertFalse(self.rol_supervisor.concede_todo)
        self.assertFalse(self.rol_censista.concede_todo)

    def test_permisos_activos_excluye_los_desactivados(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        permiso.activo = False
        permiso.save()

        self.assertIn(permiso, self.rol_supervisor.permisos.all())
        self.assertNotIn(permiso, self.rol_supervisor.permisos_activos())

    def test_la_relacion_inversa_dice_que_roles_tienen_un_permiso(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        nombres = set(permiso.roles.values_list("codigo", flat=True))
        self.assertEqual(nombres, {"ADMINISTRADOR", "SUPERVISOR"})

    def test_un_rol_puede_quedarse_sin_ningun_permiso(self):
        """Es un estado válido: un rol creado y todavía sin configurar."""
        self.rol_censista.permisos.clear()
        self.assertEqual(self.rol_censista.permisos.count(), 0)

    def test_borrar_un_permiso_no_borra_el_rol(self):
        permiso = Permiso.objects.get(codigo="fichas.editar")
        permiso.delete()
        self.rol_censista.refresh_from_db()
        self.assertNotIn("fichas.editar", self.codigos_de(self.rol_censista))
        self.assertTrue(Rol.objects.filter(pk=self.rol_censista.pk).exists())


# ==========================================================================
# 3. Usuario.tiene_permiso() — el corazón de la autorización
# ==========================================================================


class UsuarioTienePermisoTest(BasePermisosTest):
    """Las tres reglas de tiene_permiso() y sus casos límite."""

    def test_el_censista_tiene_los_permisos_de_su_rol(self):
        self.assertTrue(self.censista.tiene_permiso("fichas.crear"))

    def test_el_censista_no_tiene_los_permisos_que_su_rol_no_incluye(self):
        self.assertFalse(self.censista.tiene_permiso("fichas.validar"))

    def test_el_supervisor_tiene_los_permisos_de_su_rol(self):
        self.assertTrue(self.supervisor.tiene_permiso("fichas.validar"))

    def test_el_administrador_tiene_todos_los_permisos(self):
        for codigo in Permiso.objects.values_list("codigo", flat=True):
            self.assertTrue(self.admin.tiene_permiso(codigo), codigo)

    def test_el_administrador_pasa_incluso_ante_un_codigo_inexistente(self):
        """Consecuencia documentada de la regla 1: acceso total es acceso total.

        Un código mal escrito en una vista no deja fuera al administrador, pero sí
        bloquearía a todos los demás roles, y eso lo detectan las pruebas de esos
        roles. Se comprueba aquí para que el comportamiento sea explícito y no una
        sorpresa.
        """
        self.assertTrue(self.admin.tiene_permiso("modulo.que.no.existe"))

    def test_el_superusuario_sin_rol_tiene_todos_los_permisos(self):
        """No debe quedarse fuera del sistema por no tener fila de rol."""
        root = Usuario.objects.create_superuser(
            email="root@opso.cl", password=CLAVE_VALIDA, first_name="R", last_name="T"
        )
        self.assertTrue(root.tiene_permiso("fichas.validar"))

    def test_un_usuario_sin_rol_no_tiene_ningun_permiso(self):
        self.assertFalse(self.sin_rol.tiene_permiso("fichas.ver_propias"))

    def test_desactivar_el_rol_corta_todos_sus_permisos(self):
        self.rol_censista.activo = False
        self.rol_censista.save()
        self.censista.refresh_from_db()
        self.assertFalse(self.censista.tiene_permiso("fichas.crear"))

    def test_desactivar_un_permiso_deja_de_concederlo_aunque_siga_marcado(self):
        permiso = Permiso.objects.get(codigo="fichas.crear")
        permiso.activo = False
        permiso.save()

        # Sigue en la tabla intermedia...
        self.assertIn(permiso, self.rol_censista.permisos.all())
        # ...pero ya no autoriza.
        self.assertFalse(self.censista.tiene_permiso("fichas.crear"))

    def test_conceder_un_permiso_surte_efecto_de_inmediato(self):
        """La razón de ser de la historia: cambiar autorización sin desplegar."""
        self.assertFalse(self.censista.tiene_permiso("fichas.validar"))

        self.rol_censista.permisos.add(Permiso.objects.get(codigo="fichas.validar"))

        self.censista.refresh_from_db()
        self.assertTrue(self.censista.tiene_permiso("fichas.validar"))

    def test_revocar_un_permiso_surte_efecto_de_inmediato(self):
        self.rol_censista.permisos.remove(Permiso.objects.get(codigo="fichas.crear"))
        self.censista.refresh_from_db()
        self.assertFalse(self.censista.tiene_permiso("fichas.crear"))

    def test_tiene_algun_permiso_basta_con_uno(self):
        self.assertTrue(
            self.censista.tiene_algun_permiso("fichas.validar", "fichas.crear")
        )

    def test_tiene_algun_permiso_es_falso_si_no_tiene_ninguno(self):
        self.assertFalse(
            self.censista.tiene_algun_permiso("fichas.validar", "reportes.exportar")
        )

    def test_tiene_algun_permiso_sin_rol_es_falso(self):
        self.assertFalse(self.sin_rol.tiene_algun_permiso("fichas.crear"))

    def test_tiene_algun_permiso_es_verdadero_para_el_administrador(self):
        self.assertTrue(self.admin.tiene_algun_permiso("cualquiera.cosa"))

    def test_codigos_permisos_devuelve_los_del_rol(self):
        self.assertEqual(
            self.censista.codigos_permisos(),
            {"fichas.ver_propias", "fichas.crear", "fichas.editar"},
        )

    def test_codigos_permisos_del_administrador_son_todos_los_activos(self):
        permiso = Permiso.objects.get(codigo="reportes.exportar")
        permiso.activo = False
        permiso.save()

        codigos = self.admin.codigos_permisos()
        self.assertEqual(len(codigos), 19)
        self.assertNotIn("reportes.exportar", codigos)

    def test_codigos_permisos_sin_rol_es_un_conjunto_vacio(self):
        self.assertEqual(self.sin_rol.codigos_permisos(), set())

    def test_codigos_permisos_omite_los_desactivados(self):
        permiso = Permiso.objects.get(codigo="fichas.crear")
        permiso.activo = False
        permiso.save()
        self.assertNotIn("fichas.crear", self.censista.codigos_permisos())


# ==========================================================================
# 4. PermisoRequeridoMixin
# ==========================================================================


@override_settings(ROOT_URLCONF=URLCONF_PRUEBA)
class PermisoRequeridoMixinTest(BasePermisosTest):
    """El control de acceso por permiso en vistas basadas en clases."""

    def setUp(self):
        super().setUp()
        self.url_validar = reverse("prueba_permiso_mixin")
        self.url_dos = reverse("prueba_permiso_todos")
        self.url_sin_declarar = reverse("prueba_permiso_sin_declarar")

    def test_deja_pasar_a_quien_tiene_el_permiso(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url_validar).status_code, 200)

    def test_bloquea_a_quien_no_tiene_el_permiso(self):
        self.client.force_login(self.censista)
        respuesta = self.client.get(self.url_validar)
        self.assertEqual(respuesta.status_code, 302)

    def test_al_bloquear_redirige_al_panel_propio(self):
        self.client.force_login(self.censista)
        respuesta = self.client.get(self.url_validar)
        self.assertRedirects(respuesta, reverse("dashboards:censista"))

    def test_al_bloquear_deja_un_mensaje_de_error(self):
        self.client.force_login(self.censista)
        respuesta = self.client.get(self.url_validar, follow=True)
        mensajes = [str(m) for m in respuesta.context["messages"]]
        self.assertTrue(any("permiso" in m.lower() for m in mensajes), mensajes)

    def test_el_administrador_pasa_siempre(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_validar).status_code, 200)

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url_validar)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_conceder_el_permiso_abre_la_vista_sin_tocar_codigo(self):
        """La demostración de la historia de usuario, de punta a punta."""
        self.client.force_login(self.censista)
        self.assertEqual(self.client.get(self.url_validar).status_code, 302)

        self.rol_censista.permisos.add(Permiso.objects.get(codigo="fichas.validar"))

        self.assertEqual(self.client.get(self.url_validar).status_code, 200)

    def test_exigir_todos_pide_los_dos_permisos(self):
        self.client.force_login(self.censista)
        # El censista tiene fichas.editar pero no fichas.validar.
        self.assertEqual(self.client.get(self.url_dos).status_code, 302)

        self.rol_censista.permisos.add(Permiso.objects.get(codigo="fichas.validar"))
        self.assertEqual(self.client.get(self.url_dos).status_code, 200)

    def test_una_vista_sin_permisos_declarados_falla_en_vez_de_abrirse(self):
        """Seguro por defecto: el descuido del programador no abre la puerta."""
        self.client.force_login(self.censista)
        with self.assertRaises(ImproperlyConfigured):
            self.client.get(self.url_sin_declarar)

    def test_desactivar_el_rol_cierra_la_vista(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url_validar).status_code, 200)

        self.rol_supervisor.activo = False
        self.rol_supervisor.save()

        self.assertEqual(self.client.get(self.url_validar).status_code, 302)


# ==========================================================================
# 5. El decorador permiso_requerido
# ==========================================================================


@override_settings(ROOT_URLCONF=URLCONF_PRUEBA)
class PermisoRequeridoDecoradorTest(BasePermisosTest):
    """Mismo comportamiento que el mixin, para vistas escritas como función."""

    def setUp(self):
        super().setUp()
        self.url = reverse("prueba_permiso_decorador")

    def test_deja_pasar_a_quien_tiene_el_permiso(self):
        self.client.force_login(self.censista)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_responde_403_a_quien_no_lo_tiene(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_el_administrador_pasa_siempre(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_sin_codigos_falla_al_declararse(self):
        with self.assertRaises(ImproperlyConfigured):
            permiso_requerido()

    def test_exigir_todos_pide_los_dos_permisos(self):
        @permiso_requerido("fichas.crear", "fichas.validar", exigir_todos=True)
        def vista(request):
            return HttpResponse("ok")

        peticion = self.client.request().wsgi_request
        peticion.user = self.censista
        with self.assertRaises(PermissionDenied):
            vista(peticion)


# ==========================================================================
# 6. La matriz: control de acceso
# ==========================================================================


class MatrizAccesoTest(BasePermisosTest):
    """Quién puede abrir /roles/permisos/ y quién no."""

    def test_el_administrador_entra(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_matriz).status_code, 200)

    def test_el_supervisor_es_rechazado(self):
        self.client.force_login(self.supervisor)
        self.assertRedirects(
            self.client.get(self.url_matriz), reverse("dashboards:supervisor")
        )

    def test_el_censista_es_rechazado(self):
        self.client.force_login(self.censista)
        self.assertRedirects(
            self.client.get(self.url_matriz), reverse("dashboards:censista")
        )

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url_matriz)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_el_superusuario_entra(self):
        root = Usuario.objects.create_superuser(
            email="root@opso.cl", password=CLAVE_VALIDA, first_name="R", last_name="T"
        )
        self.client.force_login(root)
        self.assertEqual(self.client.get(self.url_matriz).status_code, 200)

    def test_el_supervisor_tampoco_puede_guardar(self):
        """No basta con esconder el botón: el POST también se rechaza."""
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(self.url_matriz, self.datos_matriz())
        self.assertEqual(respuesta.status_code, 302)
        # Y nada cambió.
        self.assertIn("fichas.validar", self.codigos_de(self.rol_supervisor))

    def test_la_matriz_no_se_protege_con_un_permiso_del_catalogo(self):
        """La llave no se guarda dentro de la caja que abre.

        Quitarle a un rol el permiso roles.asignar_permisos no debe poder cerrar
        la matriz para el administrador: su acceso depende del ROL, no de una
        casilla que él mismo podría desmarcar.
        """
        self.rol_admin.permisos.remove(
            Permiso.objects.get(codigo="roles.asignar_permisos")
        )
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_matriz).status_code, 200)

    def test_el_post_exige_token_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        respuesta = cliente.post(self.url_matriz, self.datos_matriz())
        self.assertEqual(respuesta.status_code, 403)


# ==========================================================================
# 7. La matriz: GET
# ==========================================================================


class MatrizGetTest(BasePermisosTest):
    """Qué muestra la pantalla."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.respuesta = self.client.get(self.url_matriz)

    def test_usa_la_plantilla_de_la_matriz(self):
        self.assertTemplateUsed(
            self.respuesta, "usuarios/gestion/permisos_matriz.html"
        )

    def test_muestra_los_tres_roles_como_columnas(self):
        nombres = [rol.nombre for rol in self.respuesta.context["roles"]]
        self.assertEqual(sorted(nombres), ["Administrador", "Censista", "Supervisor"])

    def test_agrupa_los_permisos_por_modulo(self):
        modulos = [g["modulo"] for g in self.respuesta.context["grupos"]]
        self.assertEqual(len(modulos), len(ModuloPermiso.values))

    def test_los_modulos_implementados_van_primero(self):
        modulos = [g["modulo"] for g in self.respuesta.context["grupos"]]
        self.assertEqual(modulos[0], "Usuarios")
        self.assertEqual(modulos[-1], "Reportes")

    def test_muestra_los_veinte_permisos(self):
        total = sum(len(g["filas"]) for g in self.respuesta.context["grupos"])
        self.assertEqual(total, 20)
        self.assertEqual(self.respuesta.context["total_permisos"], 20)

    def test_solo_hay_formulario_para_los_roles_editables(self):
        """El Administrador no tiene formulario: concede todo implícitamente."""
        formularios = list(self.respuesta.context["formularios"])
        self.assertEqual(len(formularios), 2)
        self.assertNotIn(
            RolCodigo.ADMINISTRADOR, [f.rol.codigo for f in formularios]
        )

    def test_las_celdas_del_administrador_no_son_editables(self):
        fila = self.respuesta.context["grupos"][0]["filas"][0]
        celda_admin = next(
            c for c in fila["celdas"] if c["rol"].codigo == RolCodigo.ADMINISTRADOR
        )
        self.assertFalse(celda_admin["editable"])
        self.assertTrue(celda_admin["marcado"])

    def test_las_celdas_reflejan_el_reparto_real(self):
        for grupo in self.respuesta.context["grupos"]:
            for fila in grupo["filas"]:
                for celda in fila["celdas"]:
                    if celda["rol"].codigo != RolCodigo.CENSISTA:
                        continue
                    esperado = fila["permiso"].codigo in self.codigos_de(
                        self.rol_censista
                    )
                    self.assertEqual(celda["marcado"], esperado, fila["permiso"].codigo)

    def test_no_muestra_los_permisos_desactivados(self):
        permiso = Permiso.objects.get(codigo="reportes.exportar")
        permiso.activo = False
        permiso.save()

        respuesta = self.client.get(self.url_matriz)
        codigos = [
            fila["permiso"].codigo
            for grupo in respuesta.context["grupos"]
            for fila in grupo["filas"]
        ]
        self.assertNotIn("reportes.exportar", codigos)
        self.assertEqual(len(codigos), 19)

    def test_incluye_los_roles_desactivados_con_su_marca(self):
        self.rol_censista.activo = False
        self.rol_censista.save()

        respuesta = self.client.get(self.url_matriz)
        censista = next(
            r for r in respuesta.context["roles"] if r.codigo == RolCodigo.CENSISTA
        )
        self.assertFalse(censista.activo)
        self.assertContains(respuesta, "rol desactivado")


# ==========================================================================
# 8. La matriz: POST
# ==========================================================================


class MatrizPostTest(BasePermisosTest):
    """Guardar la matriz: efecto, auditoría y casos límite."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_conceder_un_permiso_lo_guarda(self):
        datos = self.datos_matriz(
            CENSISTA=["fichas.ver_propias", "fichas.crear", "fichas.editar", "fichas.validar"]
        )
        self.client.post(self.url_matriz, datos)
        self.assertIn("fichas.validar", self.codigos_de(self.rol_censista))

    def test_revocar_un_permiso_lo_quita(self):
        datos = self.datos_matriz(CENSISTA=["fichas.ver_propias", "fichas.crear"])
        self.client.post(self.url_matriz, datos)
        self.assertNotIn("fichas.editar", self.codigos_de(self.rol_censista))

    def test_enviar_un_rol_sin_permisos_lo_deja_vacio(self):
        datos = self.datos_matriz(CENSISTA=[])
        self.client.post(self.url_matriz, datos)
        self.assertEqual(self.codigos_de(self.rol_censista), set())

    def test_redirige_a_la_matriz_tras_guardar(self):
        """POST-redirect-GET: recargar no reenvía el formulario."""
        respuesta = self.client.post(self.url_matriz, self.datos_matriz(CENSISTA=[]))
        self.assertRedirects(respuesta, self.url_matriz)

    def test_avisa_del_exito_nombrando_el_rol_modificado(self):
        datos = self.datos_matriz(CENSISTA=["fichas.crear"])
        respuesta = self.client.post(self.url_matriz, datos, follow=True)
        mensajes = [str(m) for m in respuesta.context["messages"]]
        self.assertTrue(any("Censista" in m for m in mensajes), mensajes)

    def test_no_altera_los_roles_que_no_se_tocaron(self):
        antes = self.codigos_de(self.rol_supervisor)
        self.client.post(self.url_matriz, self.datos_matriz(CENSISTA=[]))
        self.assertEqual(self.codigos_de(self.rol_supervisor), antes)

    def test_no_puede_modificar_los_permisos_del_administrador(self):
        """Su campo no existe en el formulario, así que el POST se ignora."""
        campo = f"{PermisosRolForm.prefijo_de(self.rol_admin)}-permisos"
        datos = self.datos_matriz()
        datos[campo] = []  # intento de dejarlo sin permisos

        self.client.post(self.url_matriz, datos)

        self.assertEqual(self.rol_admin.permisos.count(), Permiso.objects.count())

    # -- auditoría ----------------------------------------------------------

    def test_registra_el_cambio_en_la_bitacora(self):
        datos = self.datos_matriz(CENSISTA=["fichas.crear"])
        self.client.post(self.url_matriz, datos)

        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertIsNotNone(registro)
        self.assertEqual(registro.administrador, self.admin)
        self.assertEqual(registro.rol_afectado, self.rol_censista)

    def test_la_bitacora_guarda_el_nombre_del_rol_como_texto(self):
        self.client.post(self.url_matriz, self.datos_matriz(CENSISTA=[]))
        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertEqual(registro.rol_afectado_nombre, "Censista")

    def test_la_bitacora_no_apunta_a_ningun_usuario(self):
        """Cambiar permisos no recae sobre una persona concreta."""
        self.client.post(self.url_matriz, self.datos_matriz(CENSISTA=[]))
        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertIsNone(registro.usuario_afectado)
        self.assertEqual(registro.usuario_afectado_email, "")

    def test_el_detalle_dice_que_se_concedio(self):
        datos = self.datos_matriz(
            CENSISTA=["fichas.ver_propias", "fichas.crear", "fichas.editar", "fichas.validar"]
        )
        self.client.post(self.url_matriz, datos)
        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertIn("concedidos", registro.detalle)
        self.assertIn("Validar o rechazar una ficha levantada", registro.detalle)

    def test_el_detalle_dice_que_se_revoco(self):
        datos = self.datos_matriz(CENSISTA=["fichas.ver_propias", "fichas.crear"])
        self.client.post(self.url_matriz, datos)
        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertIn("revocados", registro.detalle)
        self.assertIn("Corregir una ficha", registro.detalle)

    def test_la_bitacora_guarda_la_ip(self):
        self.client.post(
            self.url_matriz, self.datos_matriz(CENSISTA=[]), REMOTE_ADDR="10.1.2.3"
        )
        registro = RegistroAuditoria.objects.filter(
            accion=AccionAuditoria.CAMBIAR_PERMISOS
        ).first()
        self.assertEqual(registro.ip, "10.1.2.3")

    def test_guardar_sin_cambios_no_escribe_en_la_bitacora(self):
        """Una bitácora llena de filas vacías esconde las que importan."""
        self.client.post(self.url_matriz, self.datos_matriz())
        self.assertEqual(
            RegistroAuditoria.objects.filter(
                accion=AccionAuditoria.CAMBIAR_PERMISOS
            ).count(),
            0,
        )

    def test_guardar_sin_cambios_avisa_que_no_hubo_cambios(self):
        respuesta = self.client.post(self.url_matriz, self.datos_matriz(), follow=True)
        mensajes = [str(m) for m in respuesta.context["messages"]]
        self.assertTrue(any("ningún cambio" in m for m in mensajes), mensajes)

    def test_escribe_una_fila_por_cada_rol_modificado(self):
        datos = self.datos_matriz(CENSISTA=[], SUPERVISOR=["fichas.validar"])
        self.client.post(self.url_matriz, datos)
        self.assertEqual(
            RegistroAuditoria.objects.filter(
                accion=AccionAuditoria.CAMBIAR_PERMISOS
            ).count(),
            2,
        )

    # -- casos límite -------------------------------------------------------

    def test_un_identificador_inexistente_rechaza_todo_el_post(self):
        datos = self.datos_matriz()
        campo = f"{PermisosRolForm.prefijo_de(self.rol_censista)}-permisos"
        datos[campo] = [999999]

        antes = self.codigos_de(self.rol_censista)
        respuesta = self.client.post(self.url_matriz, datos)

        self.assertEqual(respuesta.status_code, 200)  # se queda en la pantalla
        self.assertEqual(self.codigos_de(self.rol_censista), antes)

    def test_un_identificador_inexistente_no_deja_rastro_en_la_bitacora(self):
        datos = self.datos_matriz()
        campo = f"{PermisosRolForm.prefijo_de(self.rol_censista)}-permisos"
        datos[campo] = [999999]
        self.client.post(self.url_matriz, datos)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_no_se_puede_conceder_un_permiso_desactivado(self):
        """No está en el queryset del formulario, así que el POST se rechaza."""
        permiso = Permiso.objects.get(codigo="reportes.exportar")
        permiso.activo = False
        permiso.save()

        datos = self.datos_matriz()
        campo = f"{PermisosRolForm.prefijo_de(self.rol_censista)}-permisos"
        datos[campo] = list(datos[campo]) + [permiso.pk]

        respuesta = self.client.post(self.url_matriz, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("reportes.exportar", self.codigos_de(self.rol_censista))

    def test_guardar_no_revoca_un_permiso_desactivado_que_ya_estaba_concedido(self):
        """La matriz no lo muestra, así que tampoco puede quitarlo sin más.

        Sin esta salvaguarda, abrir la pantalla y pulsar «Guardar» borraría en
        silencio permisos que nadie decidió retirar.
        """
        permiso = Permiso.objects.get(codigo="fichas.crear")
        permiso.activo = False
        permiso.save()

        self.client.post(self.url_matriz, self.datos_matriz())

        self.assertIn(permiso, self.rol_censista.permisos.all())

    def test_si_falla_la_auditoria_no_se_guarda_el_cambio(self):
        """Transacción: o se guardan permisos y bitácora, o no se guarda nada."""
        datos = self.datos_matriz(CENSISTA=[])
        antes = self.codigos_de(self.rol_censista)

        with patch(
            "usuarios.views_permisos.registrar_accion",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url_matriz, datos)

        self.assertEqual(self.codigos_de(self.rol_censista), antes)
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_el_cambio_afecta_de_inmediato_a_los_usuarios_del_rol(self):
        """El efecto extremo a extremo: de la casilla al permiso del usuario."""
        self.assertFalse(self.censista.tiene_permiso("fichas.validar"))

        datos = self.datos_matriz(CENSISTA=["fichas.validar"])
        self.client.post(self.url_matriz, datos)

        self.censista.refresh_from_db()
        self.assertTrue(self.censista.tiene_permiso("fichas.validar"))


# ==========================================================================
# 9. El formulario PermisosRolForm por separado
# ==========================================================================


class PermisosRolFormTest(BasePermisosTest):
    """El formulario probado aislado, sin pasar por una petición HTTP."""

    def test_el_prefijo_se_deriva_del_rol(self):
        self.assertEqual(
            PermisosRolForm.prefijo_de(self.rol_censista), f"rol{self.rol_censista.pk}"
        )

    def test_el_nombre_del_campo_html_lleva_el_prefijo(self):
        formulario = PermisosRolForm(rol=self.rol_censista)
        self.assertEqual(
            formulario.nombre_campo_html, f"rol{self.rol_censista.pk}-permisos"
        )

    def test_sin_datos_el_estado_inicial_es_el_de_la_base(self):
        formulario = PermisosRolForm(rol=self.rol_censista)
        self.assertEqual(
            formulario.pks_seleccionados(),
            set(self.rol_censista.permisos.values_list("pk", flat=True)),
        )

    def test_con_datos_el_estado_es_el_enviado(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        formulario = PermisosRolForm(
            {f"rol{self.rol_censista.pk}-permisos": [str(permiso.pk)]},
            rol=self.rol_censista,
        )
        self.assertEqual(formulario.pks_seleccionados(), {permiso.pk})

    def test_un_formulario_vacio_es_valido(self):
        """Un rol sin permisos es un estado legítimo."""
        formulario = PermisosRolForm({}, rol=self.rol_censista)
        self.assertTrue(formulario.is_valid())
        self.assertEqual(list(formulario.cleaned_data["permisos"]), [])

    def test_un_identificador_inexistente_invalida_el_formulario(self):
        formulario = PermisosRolForm(
            {f"rol{self.rol_censista.pk}-permisos": ["999999"]}, rol=self.rol_censista
        )
        self.assertFalse(formulario.is_valid())

    def test_guardar_devuelve_el_antes_y_el_despues(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        formulario = PermisosRolForm(
            {f"rol{self.rol_censista.pk}-permisos": [str(permiso.pk)]},
            rol=self.rol_censista,
        )
        self.assertTrue(formulario.is_valid())
        antes, despues = formulario.guardar()

        self.assertEqual(len(antes), 3)
        self.assertEqual([p.codigo for p in despues], ["fichas.validar"])

    def test_solo_se_ofrecen_los_permisos_activos(self):
        permiso = Permiso.objects.get(codigo="fichas.validar")
        permiso.activo = False
        permiso.save()

        formulario = PermisosRolForm(rol=self.rol_censista)
        self.assertNotIn(permiso, formulario.fields["permisos"].queryset)


# ==========================================================================
# 10. La auditoría de roles
# ==========================================================================


class AuditoriaRolTest(BasePermisosTest):
    """registrar_accion() con un rol, y la lectura de la bitácora."""

    def test_registra_una_accion_sobre_un_rol(self):
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CAMBIAR_PERMISOS,
            rol_afectado=self.rol_censista,
            detalle="concedidos: X",
        )
        self.assertEqual(registro.rol_afectado, self.rol_censista)
        self.assertEqual(registro.rol_afectado_nombre, "Censista")

    def test_sin_objeto_afectado_falla_en_vez_de_escribir_una_fila_incompleta(self):
        with self.assertRaises(ValueError):
            registrar_accion(
                administrador=self.admin, accion=AccionAuditoria.CAMBIAR_PERMISOS
            )
        self.assertEqual(RegistroAuditoria.objects.count(), 0)

    def test_objetivo_muestra_el_correo_cuando_afecta_a_una_cuenta(self):
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.EDITAR,
            usuario_afectado=self.censista,
        )
        self.assertEqual(registro.objetivo, "censista@opso.cl")

    def test_objetivo_muestra_el_rol_cuando_afecta_a_un_rol(self):
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CAMBIAR_PERMISOS,
            rol_afectado=self.rol_censista,
        )
        self.assertEqual(registro.objetivo, "Rol: Censista")

    def test_la_fila_sobrevive_al_borrado_del_rol(self):
        """SET_NULL más la copia de texto: la bitácora no queda ilegible.

        No se crea un rol nuevo para la prueba porque el CheckConstraint
        rol_codigo_valido solo admite los tres códigos del catálogo y los tres
        están ocupados. Se usa uno real: primero se traslada a su único usuario
        (la clave foránea es PROTECT y el borrado fallaría) y después se borra.
        """
        self.censista.rol = self.rol_supervisor
        self.censista.save()

        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CAMBIAR_PERMISOS,
            rol_afectado=self.rol_censista,
        )
        self.rol_censista.delete()

        registro.refresh_from_db()
        self.assertIsNone(registro.rol_afectado)
        self.assertEqual(registro.rol_afectado_nombre, "Censista")
        self.assertEqual(registro.objetivo, "Rol: Censista")

    def test_str_del_registro_incluye_el_objetivo(self):
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CAMBIAR_PERMISOS,
            rol_afectado=self.rol_censista,
        )
        self.assertIn("Rol: Censista", str(registro))

    # -- describir_cambio_permisos ------------------------------------------

    def test_describe_lo_concedido(self):
        antes = list(Permiso.objects.filter(codigo="fichas.crear"))
        despues = list(
            Permiso.objects.filter(codigo__in=["fichas.crear", "fichas.validar"])
        )
        texto = describir_cambio_permisos(antes, despues)
        self.assertIn("concedidos", texto)
        self.assertIn("Validar o rechazar una ficha levantada", texto)
        self.assertNotIn("revocados", texto)

    def test_describe_lo_revocado(self):
        antes = list(
            Permiso.objects.filter(codigo__in=["fichas.crear", "fichas.validar"])
        )
        despues = list(Permiso.objects.filter(codigo="fichas.crear"))
        texto = describir_cambio_permisos(antes, despues)
        self.assertIn("revocados", texto)
        self.assertNotIn("concedidos", texto)

    def test_describe_las_dos_cosas_a_la_vez(self):
        antes = list(Permiso.objects.filter(codigo="fichas.crear"))
        despues = list(Permiso.objects.filter(codigo="fichas.validar"))
        texto = describir_cambio_permisos(antes, despues)
        self.assertIn("concedidos", texto)
        self.assertIn("revocados", texto)

    def test_sin_cambios_devuelve_cadena_vacia(self):
        permisos = list(Permiso.objects.filter(codigo="fichas.crear"))
        self.assertEqual(describir_cambio_permisos(permisos, permisos), "")

    def test_usa_el_nombre_visible_y_no_el_codigo(self):
        antes = []
        despues = list(Permiso.objects.filter(codigo="fichas.validar"))
        texto = describir_cambio_permisos(antes, despues)
        self.assertNotIn("fichas.validar", texto)

    def test_el_orden_es_estable_alfabetico(self):
        despues = list(
            Permiso.objects.filter(
                codigo__in=["fichas.validar", "fichas.crear", "reportes.ver"]
            )
        )
        texto = describir_cambio_permisos([], despues)
        nombres = texto.replace("concedidos: ", "").split(", ")
        self.assertEqual(nombres, sorted(nombres))


# ==========================================================================
# 11. Integración con el resto del sistema
# ==========================================================================


class IntegracionPermisosTest(BasePermisosTest):
    """Que la HU-04 no rompa lo que ya funcionaba."""

    def test_el_panel_del_administrador_enlaza_a_la_matriz(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("dashboards:administrador"))
        self.assertContains(respuesta, self.url_matriz)

    def test_la_auditoria_muestra_los_cambios_de_permisos(self):
        self.client.force_login(self.admin)
        self.client.post(self.url_matriz, self.datos_matriz(CENSISTA=[]))

        respuesta = self.client.get(reverse("usuarios:auditoria"))
        self.assertContains(respuesta, "Cambió los permisos del rol")
        self.assertContains(respuesta, "Censista")

    def test_la_auditoria_sigue_mostrando_las_acciones_sobre_usuarios(self):
        registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.EDITAR,
            usuario_afectado=self.censista,
            detalle="teléfono",
        )
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("usuarios:auditoria"))
        self.assertContains(respuesta, "censista@opso.cl")

    def test_los_paneles_por_rol_siguen_funcionando(self):
        """El control por rol de la HU-01 no se tocó."""
        self.client.force_login(self.censista)
        self.assertEqual(
            self.client.get(reverse("dashboards:censista")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("dashboards:administrador")).status_code, 302
        )

    def test_la_administracion_de_usuarios_sigue_cerrada_a_quien_no_la_tenia(self):
        """El reparto inicial no abre nada que antes estuviera cerrado.

        Antes de la HU-04 el censista era rechazado por no tener el ROL; ahora lo
        es por no tener el PERMISO. Lo que no cambia —y es lo que esta prueba
        protege— es el resultado observable.
        """
        self.client.force_login(self.censista)
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 302)


# ==========================================================================
# 9. EL MÓDULO DE USUARIOS, AHORA PROTEGIDO POR PERMISO
# ==========================================================================


class ModuloUsuariosPermisosTest(BasePermisosTest):
    """Cada vista de la HU-03 exige el permiso que declara (ModuloUsuariosMixin).

    Es la prueba de que la HU-04 no se quedó en una pantalla bonita: la matriz
    gobierna de verdad el acceso a las vistas que ya existían. Sin estas pruebas,
    alguien podría dejar una vista con la puerta anterior y nadie lo notaría,
    porque el acceso resultante para los roles iniciales es idéntico.
    """

    def setUp(self):
        super().setUp()
        # (nombre de la ruta, kwargs, método, permiso que debe exigir)
        self.rutas = [
            ("usuarios:lista", {}, "get", "usuarios.ver"),
            ("usuarios:detalle", {"pk": self.censista.pk}, "get", "usuarios.ver"),
            ("usuarios:crear", {}, "get", "usuarios.crear"),
            ("usuarios:editar", {"pk": self.censista.pk}, "get", "usuarios.editar"),
            (
                "usuarios:deshabilitar",
                {"pk": self.censista.pk},
                "get",
                "usuarios.cambiar_estado",
            ),
            (
                "usuarios:habilitar",
                {"pk": self.censista.pk},
                "get",
                "usuarios.cambiar_estado",
            ),
            (
                "usuarios:enviar_enlace",
                {"pk": self.censista.pk},
                "post",
                "usuarios.enviar_enlace",
            ),
            ("usuarios:auditoria", {}, "get", "auditoria.ver"),
        ]

    def conceder(self, rol, *codigos):
        rol.permisos.add(*Permiso.objects.filter(codigo__in=codigos))

    # -- el reparto inicial no cambia quién entra --------------------------

    def test_sin_el_permiso_ninguna_ruta_del_modulo_se_abre(self):
        self.client.force_login(self.supervisor)
        for nombre, kwargs, metodo, permiso in self.rutas:
            with self.subTest(ruta=nombre):
                respuesta = getattr(self.client, metodo)(reverse(nombre, kwargs=kwargs))
                self.assertEqual(
                    respuesta.status_code,
                    302,
                    f"{nombre} se abrió sin el permiso {permiso}",
                )

    def test_el_administrador_entra_a_todas(self):
        """concede_todo: no depende de que la matriz tenga las casillas marcadas."""
        self.client.force_login(self.admin)
        for nombre, kwargs, metodo, _ in self.rutas:
            with self.subTest(ruta=nombre):
                respuesta = getattr(self.client, metodo)(reverse(nombre, kwargs=kwargs))
                self.assertIn(respuesta.status_code, (200, 302))
                self.assertNotEqual(respuesta.status_code, 403)

    # -- lo que la HU-04 hace posible -------------------------------------

    def test_conceder_el_permiso_abre_la_vista_sin_tocar_codigo(self):
        """El objetivo de la historia, comprobado sobre una vista real."""
        url = reverse("usuarios:lista")
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 302)

        self.conceder(self.rol_supervisor, "usuarios.ver")

        self.assertEqual(self.client.get(url).status_code, 200)

    def test_conceder_desde_la_matriz_abre_la_vista(self):
        """Igual que el anterior, pero pasando por la pantalla de verdad."""
        self.client.force_login(self.admin)
        codigos = self.codigos_de(self.rol_supervisor) | {"usuarios.ver"}
        self.client.post(self.url_matriz, self.datos_matriz(SUPERVISOR=list(codigos)))

        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)

    def test_revocar_el_permiso_cierra_la_vista(self):
        self.conceder(self.rol_supervisor, "usuarios.ver")
        url = reverse("usuarios:lista")
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.rol_supervisor.permisos.remove(
            Permiso.objects.get(codigo="usuarios.ver")
        )

        self.assertEqual(self.client.get(url).status_code, 302)

    # -- mínimo privilegio: un permiso abre una puerta, no el módulo ------

    def test_ver_no_alcanza_para_crear_ni_editar(self):
        """Delegar la consulta no delega la escritura."""
        self.conceder(self.rol_supervisor, "usuarios.ver")
        self.client.force_login(self.supervisor)

        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)
        for nombre, kwargs in [
            ("usuarios:crear", {}),
            ("usuarios:editar", {"pk": self.censista.pk}),
            ("usuarios:deshabilitar", {"pk": self.censista.pk}),
        ]:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 302)

    def test_la_auditoria_se_delega_sin_entregar_la_gestion_de_cuentas(self):
        """Su permiso es del módulo AUDITORÍA, no del de usuarios."""
        self.conceder(self.rol_supervisor, "auditoria.ver")
        self.client.force_login(self.supervisor)

        self.assertEqual(
            self.client.get(reverse("usuarios:auditoria")).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 302)

    def test_el_permiso_de_usuarios_no_abre_la_auditoria(self):
        self.conceder(self.rol_supervisor, "usuarios.ver")
        self.client.force_login(self.supervisor)
        self.assertEqual(
            self.client.get(reverse("usuarios:auditoria")).status_code, 302
        )

    # -- las reglas por objeto sobreviven al cambio de puerta -------------

    def test_ningun_permiso_permite_editar_un_superusuario(self):
        """VerificarSuperusuarioMixin se evalúa después de conceder el acceso."""
        raiz = Usuario.objects.create_superuser(
            email="raiz@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Raíz",
            last_name="Sistema",
        )
        self.conceder(self.rol_supervisor, "usuarios.ver", "usuarios.editar")
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(reverse("usuarios:editar", kwargs={"pk": raiz.pk}))
        self.assertEqual(respuesta.status_code, 403)

    def test_desactivar_el_rol_cierra_el_modulo_aunque_tenga_el_permiso(self):
        self.conceder(self.rol_supervisor, "usuarios.ver")
        self.rol_supervisor.activo = False
        self.rol_supervisor.save()

        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 302)

    # -- la llave maestra no se delega ------------------------------------

    def test_delegar_el_modulo_de_usuarios_no_entrega_la_matriz(self):
        """La matriz se protege por ROL: ningún permiso de usuarios la abre."""
        self.conceder(
            self.rol_supervisor,
            "usuarios.ver",
            "usuarios.crear",
            "usuarios.editar",
            "roles.asignar_permisos",
        )
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url_matriz).status_code, 302)


# ==========================================================================
# URLconf DE PRUEBA
# ==========================================================================
# Las vistas de abajo existen solo para probar el mixin y el decorador. Se
# declaran aquí, en el archivo de pruebas, y no en usuarios/urls.py: las URLs
# reales del sistema no deben contener rutas que nadie usa en producción.
#
# El URLconf incluye las urlpatterns REALES además de las de prueba, porque
# handle_no_permission redirige al panel del usuario y necesita poder resolver
# "dashboards:censista" y "usuarios:login".


class _VistaPermisoMixin(PermisoRequeridoMixin, View):
    permisos_requeridos = ("fichas.validar",)

    def get(self, request, *args, **kwargs):
        return HttpResponse("autorizado")


class _VistaPermisoTodos(PermisoRequeridoMixin, View):
    permisos_requeridos = ("fichas.editar", "fichas.validar")
    exigir_todos = True

    def get(self, request, *args, **kwargs):
        return HttpResponse("autorizado")


class _VistaSinDeclararPermisos(PermisoRequeridoMixin, View):
    """A propósito no declara permisos_requeridos: debe fallar, no abrirse."""

    def get(self, request, *args, **kwargs):
        return HttpResponse("esto no debería verse")


@permiso_requerido("fichas.crear")
def _vista_con_decorador(request):
    return HttpResponse("autorizado")


from config.urls import urlpatterns as _urlpatterns_reales  # noqa: E402

urlpatterns = _urlpatterns_reales + [
    path("prueba/mixin/", _VistaPermisoMixin.as_view(), name="prueba_permiso_mixin"),
    path("prueba/todos/", _VistaPermisoTodos.as_view(), name="prueba_permiso_todos"),
    path(
        "prueba/sin-declarar/",
        _VistaSinDeclararPermisos.as_view(),
        name="prueba_permiso_sin_declarar",
    ),
    path(
        "prueba/decorador/", _vista_con_decorador, name="prueba_permiso_decorador"
    ),
]
