"""Pruebas automáticas de la HU-06 «Asignar sectores a los encuestadores».

Se separan de tests.py (HU-05) siguiendo la convención del proyecto: cada historia
de usuario tiene su archivo de evidencia y en la defensa se puede ejecutar solo el
que corresponda.

    python manage.py test operativos.tests_asignaciones

Cada prueba sigue el patrón PREPARAR -> ACTUAR -> VERIFICAR y su nombre describe la
regla que comprueba, para que la salida del comando se lea como una lista de
requisitos cumplidos.
"""

from datetime import date

from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from usuarios.auditoria import describir_cambio_asignaciones, registrar_accion
from usuarios.models import (
    AccionAuditoria,
    Permiso,
    RegistroAuditoria,
    Rol,
    RolCodigo,
    TipoObjetoAuditoria,
    Usuario,
)

from .forms_asignaciones import AsignarSectorForm
from .models import AsignacionSector, Comuna, EstadoOperativo, Operativo, Region, Sector, Zona

CLAVE_VALIDA = "Censo2026#Opso"


class BaseAsignacionTest(TestCase):
    """Escenario común: un operativo con dos sectores y tres censistas."""

    @classmethod
    def setUpTestData(cls):
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
        cls.marta = Usuario.objects.create_user(
            email="marta@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Marta",
            last_name="Soto",
            rol=cls.rol_censista,
        )
        cls.juan = Usuario.objects.create_user(
            email="juan@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Juan",
            last_name="Vera",
            rol=cls.rol_censista,
        )
        cls.biobio = Region.objects.get(codigo="08")

    def setUp(self):
        self.concepcion = Comuna.objects.create(region=self.biobio, nombre="Concepción")
        self.operativo = Operativo.objects.create(
            nombre="Censo Social 2026",
            fecha_inicio=date(2026, 3, 1),
            fecha_termino=date(2026, 3, 31),
        )
        self.boldos = Sector.objects.create(
            operativo=self.operativo, comuna=self.concepcion, nombre="Los Boldos"
        )
        self.norte = Sector.objects.create(
            operativo=self.operativo, comuna=self.concepcion, nombre="Barrio Norte"
        )
        Zona.objects.create(
            sector=self.boldos, nombre="Zona 1", viviendas_estimadas=100
        )
        Zona.objects.create(sector=self.boldos, nombre="Zona 2", viviendas_estimadas=50)

        self.url_panel = reverse(
            "operativos:asignaciones_panel", kwargs={"pk": self.operativo.pk}
        )
        self.url_asignar = reverse(
            "operativos:sector_asignar", kwargs={"pk": self.boldos.pk}
        )

    # -- ayudantes ---------------------------------------------------------

    def asignar(self, sector=None, censista=None, **extra):
        return AsignacionSector.objects.create(
            sector=sector or self.boldos,
            censista=censista or self.marta,
            asignado_por=self.supervisor,
            **extra,
        )

    def datos(self, *censistas, observaciones=""):
        """POST para el formulario de asignación."""
        return {
            "censistas": [c.pk for c in censistas],
            "observaciones": observaciones,
        }


# ==========================================================================
# 1. EL MODELO AsignacionSector
# ==========================================================================


class AsignacionModeloTest(BaseAsignacionTest):
    def test_una_asignacion_nace_activa_y_sin_fecha_de_baja(self):
        asignacion = self.asignar()

        self.assertTrue(asignacion.activa)
        self.assertIsNone(asignacion.desasignado_en)

    def test_no_se_puede_asignar_dos_veces_a_la_misma_persona(self):
        """El índice único parcial impide duplicar una asignación vigente."""
        self.asignar()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.asignar()

    def test_si_se_puede_reasignar_a_alguien_que_ya_estuvo(self):
        """Es lo que el índice único PARCIAL hace posible.

        Con un unique(sector, censista) normal, la fila histórica bloquearía para
        siempre la reasignación de esa persona a ese sector.
        """
        primera = self.asignar()
        primera.desactivar()

        segunda = self.asignar()

        self.assertTrue(segunda.activa)
        self.assertEqual(
            AsignacionSector.objects.filter(
                sector=self.boldos, censista=self.marta
            ).count(),
            2,
        )

    def test_una_persona_puede_tener_varios_sectores(self):
        self.asignar(sector=self.boldos)
        self.asignar(sector=self.norte)

        self.assertEqual(self.marta.asignaciones_sector.filter(activa=True).count(), 2)

    def test_un_sector_puede_tener_varias_personas(self):
        self.asignar(censista=self.marta)
        self.asignar(censista=self.juan)

        self.assertEqual(self.boldos.asignaciones_activas().count(), 2)

    def test_desactivar_anota_la_fecha_de_baja(self):
        asignacion = self.asignar()
        asignacion.desactivar()
        asignacion.refresh_from_db()

        self.assertFalse(asignacion.activa)
        self.assertIsNotNone(asignacion.desasignado_en)

    def test_desactivar_no_borra_la_fila(self):
        asignacion = self.asignar()
        asignacion.desactivar()

        self.assertTrue(AsignacionSector.objects.filter(pk=asignacion.pk).exists())

    def test_la_base_rechaza_una_activa_con_fecha_de_baja(self):
        """CheckConstraint: una fila no puede contradecirse consigo misma."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsignacionSector.objects.create(
                    sector=self.boldos,
                    censista=self.marta,
                    activa=True,
                    desasignado_en=timezone.now(),
                )

    def test_la_base_rechaza_una_inactiva_sin_fecha_de_baja(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AsignacionSector.objects.create(
                    sector=self.boldos,
                    censista=self.marta,
                    activa=False,
                    desasignado_en=None,
                )

    def test_borrar_el_sector_arrastra_sus_asignaciones(self):
        """CASCADE: una asignación no significa nada sin su sector."""
        self.asignar()
        self.boldos.delete()

        self.assertEqual(AsignacionSector.objects.count(), 0)

    def test_no_se_puede_borrar_un_censista_con_asignaciones(self):
        """PROTECT: borrarlo dejaría el reparto sin explicación."""
        self.asignar()

        with self.assertRaises(ProtectedError):
            self.marta.delete()

    def test_la_asignacion_conoce_su_operativo(self):
        self.assertEqual(self.asignar().operativo, self.operativo)

    def test_str_se_lee_como_una_frase(self):
        self.assertIn("→", str(self.asignar()))


# ==========================================================================
# 2. CONSULTAS DEL MODELO
# ==========================================================================


class ConsultasModeloTest(BaseAsignacionTest):
    def test_censistas_asignados_solo_devuelve_los_vigentes(self):
        self.asignar(censista=self.marta)
        retirada = self.asignar(censista=self.juan)
        retirada.desactivar()

        self.assertEqual(list(self.boldos.censistas_asignados()), [self.marta])

    def test_esta_asignado_es_falso_sin_nadie(self):
        self.assertFalse(self.boldos.esta_asignado)

    def test_esta_asignado_es_verdadero_con_alguien(self):
        self.asignar()
        self.assertTrue(self.boldos.esta_asignado)

    def test_viviendas_estimadas_suma_las_zonas_activas(self):
        self.assertEqual(self.boldos.viviendas_estimadas(), 150)

    def test_una_zona_desactivada_no_cuenta_en_la_carga(self):
        zona = self.boldos.zonas.first()
        zona.activa = False
        zona.save()

        self.assertEqual(self.boldos.viviendas_estimadas(), 50)

    def test_un_sector_sin_estimaciones_tiene_carga_cero(self):
        self.assertEqual(self.norte.viviendas_estimadas(), 0)

    def test_total_sectores_asignados_no_cuenta_dos_veces_el_mismo(self):
        """Un sector con dos censistas es UN sector asignado, no dos."""
        self.asignar(censista=self.marta)
        self.asignar(censista=self.juan)

        self.assertEqual(self.operativo.total_sectores_asignados(), 1)

    def test_total_sectores_sin_asignar(self):
        self.asignar(sector=self.boldos)

        self.assertEqual(self.operativo.total_sectores_sin_asignar(), 1)

    def test_un_sector_desactivado_no_cuenta_como_sin_asignar(self):
        """Ya no es parte del territorio vigente: no es un hueco de cobertura."""
        self.asignar(sector=self.boldos)
        self.norte.activo = False
        self.norte.save()

        self.assertEqual(self.operativo.total_sectores_sin_asignar(), 0)

    def test_censistas_desplegados_no_repite_a_quien_tiene_dos_sectores(self):
        self.asignar(sector=self.boldos, censista=self.marta)
        self.asignar(sector=self.norte, censista=self.marta)

        self.assertEqual(list(self.operativo.censistas_desplegados()), [self.marta])

    def test_censistas_desplegados_excluye_a_los_retirados(self):
        asignacion = self.asignar()
        asignacion.desactivar()

        self.assertEqual(list(self.operativo.censistas_desplegados()), [])


# ==========================================================================
# 3. REGLAS DE NEGOCIO DEL SECTOR
# ==========================================================================


class PuedeRecibirAsignacionesTest(BaseAsignacionTest):
    def test_un_sector_activo_en_operativo_abierto_si_puede(self):
        permitido, motivo = self.boldos.puede_recibir_asignaciones()

        self.assertTrue(permitido)
        self.assertEqual(motivo, "")

    def test_un_operativo_cerrado_no_admite_reparto(self):
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        permitido, motivo = self.boldos.puede_recibir_asignaciones()

        self.assertFalse(permitido)
        self.assertIn("cerrado", motivo)

    def test_un_sector_desactivado_no_admite_reparto(self):
        """Mandar a alguien a un sector que el operativo dejó fuera no tiene sentido."""
        self.boldos.activo = False
        self.boldos.save()

        permitido, motivo = self.boldos.puede_recibir_asignaciones()

        self.assertFalse(permitido)
        self.assertIn("desactivado", motivo)

    def test_el_motivo_explica_que_hacer(self):
        self.boldos.activo = False
        self.boldos.save()

        _, motivo = self.boldos.puede_recibir_asignaciones()
        self.assertIn("Actívalo", motivo)


# ==========================================================================
# 4. CONTROL DE ACCESO
# ==========================================================================


class AccesoTest(BaseAsignacionTest):
    """La historia se apoya en el permiso que la HU-04 ya había sembrado."""

    def setUp(self):
        super().setUp()
        self.asignacion = self.asignar()
        self.url_retirar = reverse(
            "operativos:asignacion_retirar", kwargs={"pk": self.asignacion.pk}
        )

    def test_la_historia_no_agrego_permisos_al_catalogo(self):
        """Tercera historia seguida sin tocar el catálogo de la HU-04."""
        self.assertTrue(
            Permiso.objects.filter(codigo="operativos.asignar_sector").exists()
        )
        self.assertEqual(Permiso.objects.filter(modulo="OPERATIVOS").count(), 3)

    def test_el_supervisor_reparte_sin_que_nadie_le_conceda_nada(self):
        """El reparto inicial de la HU-04 ya le dio operativos.asignar_sector."""
        self.client.force_login(self.supervisor)

        for url in (self.url_panel, self.url_asignar, self.url_retirar):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_administrador_tambien_entra(self):
        self.client.force_login(self.admin)

        for url in (self.url_panel, self.url_asignar, self.url_retirar):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_censista_no_puede_repartir(self):
        self.client.force_login(self.marta)

        for url in (self.url_asignar, self.url_retirar):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_el_censista_tampoco_ve_el_panel_de_reparto(self):
        """No tiene operativos.ver: el panel es una pantalla de supervisión."""
        self.client.force_login(self.marta)
        self.assertEqual(self.client.get(self.url_panel).status_code, 302)

    def test_consultar_el_panel_no_exige_el_permiso_de_asignar(self):
        """Mirar cómo quedó el reparto no es modificarlo."""
        self.rol_supervisor.permisos.remove(
            Permiso.objects.get(codigo="operativos.asignar_sector")
        )
        self.client.force_login(self.supervisor)

        self.assertEqual(self.client.get(self.url_panel).status_code, 200)
        self.assertEqual(self.client.get(self.url_asignar).status_code, 302)

    def test_el_supervisor_no_puede_redibujar_el_territorio(self):
        """Repartir no es planificar: no tiene operativos.gestionar."""
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse(
                "operativos:sector_crear", kwargs={"operativo_pk": self.operativo.pk}
            )
        )
        self.assertEqual(respuesta.status_code, 302)

    def test_revocar_asignar_sector_cierra_el_reparto(self):
        self.rol_supervisor.permisos.remove(
            Permiso.objects.get(codigo="operativos.asignar_sector")
        )
        self.client.force_login(self.supervisor)

        self.assertEqual(self.client.get(self.url_asignar).status_code, 302)

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url_panel)
        self.assertIn(reverse("usuarios:login"), respuesta.url)


# ==========================================================================
# 5. ASIGNAR: EL FORMULARIO DE CONJUNTO
# ==========================================================================


class AsignarTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)

    def test_asignar_a_una_persona(self):
        self.client.post(self.url_asignar, self.datos(self.marta))

        self.assertEqual(list(self.boldos.censistas_asignados()), [self.marta])

    def test_asignar_a_varias_personas_a_la_vez(self):
        self.client.post(self.url_asignar, self.datos(self.marta, self.juan))

        self.assertEqual(self.boldos.asignaciones_activas().count(), 2)

    def test_se_guarda_quien_hizo_el_reparto(self):
        self.client.post(self.url_asignar, self.datos(self.marta))
        asignacion = AsignacionSector.objects.get(sector=self.boldos)

        self.assertEqual(asignacion.asignado_por, self.supervisor)

    def test_desmarcar_a_alguien_lo_retira(self):
        self.asignar(censista=self.marta)
        self.asignar(censista=self.juan)

        self.client.post(self.url_asignar, self.datos(self.marta))

        self.assertEqual(list(self.boldos.censistas_asignados()), [self.marta])

    def test_desmarcar_conserva_la_fila_como_historial(self):
        self.asignar(censista=self.juan)

        self.client.post(self.url_asignar, self.datos())

        self.assertEqual(
            AsignacionSector.objects.filter(
                sector=self.boldos, censista=self.juan, activa=False
            ).count(),
            1,
        )

    def test_enviar_el_conjunto_vacio_deja_el_sector_sin_nadie(self):
        """Es una decisión válida: puede que todavía no haya a quién asignarle."""
        self.asignar()

        self.client.post(self.url_asignar, self.datos())

        self.assertFalse(self.boldos.esta_asignado)

    def test_una_reasignacion_reactiva_la_fila_historica(self):
        """No se acumula una fila por cada ida y vuelta."""
        primera = self.asignar(censista=self.marta)
        primera.desactivar()

        self.client.post(self.url_asignar, self.datos(self.marta))

        self.assertEqual(
            AsignacionSector.objects.filter(
                sector=self.boldos, censista=self.marta
            ).count(),
            1,
        )
        primera.refresh_from_db()
        self.assertTrue(primera.activa)
        self.assertIsNone(primera.desasignado_en)

    def test_a_quien_ya_estaba_no_se_le_cambia_la_fecha(self):
        """Guardar otro cambio no debe reiniciar la antigüedad de los demás."""
        asignacion = self.asignar(censista=self.marta)
        fecha_original = asignacion.asignado_en

        self.client.post(self.url_asignar, self.datos(self.marta, self.juan))

        asignacion.refresh_from_db()
        self.assertEqual(asignacion.asignado_en, fecha_original)

    def test_las_observaciones_se_guardan_en_las_nuevas(self):
        self.client.post(
            self.url_asignar,
            self.datos(self.marta, observaciones="Empezar por el pasaje sur"),
        )
        asignacion = AsignacionSector.objects.get(sector=self.boldos)

        self.assertEqual(asignacion.observaciones, "Empezar por el pasaje sur")

    def test_las_observaciones_de_los_que_ya_estaban_no_se_pisan(self):
        asignacion = self.asignar(censista=self.marta, observaciones="Instrucción vieja")

        self.client.post(
            self.url_asignar, self.datos(self.marta, self.juan, observaciones="Nueva")
        )

        asignacion.refresh_from_db()
        self.assertEqual(asignacion.observaciones, "Instrucción vieja")

    def test_redirige_al_panel_tras_guardar(self):
        respuesta = self.client.post(self.url_asignar, self.datos(self.marta))
        self.assertRedirects(respuesta, self.url_panel)

    def test_el_post_exige_token_csrf(self):
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.supervisor)

        respuesta = cliente.post(self.url_asignar, self.datos(self.marta))

        self.assertEqual(respuesta.status_code, 403)


class QuienPuedeSerAsignadoTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)

    def disponibles(self):
        respuesta = self.client.get(self.url_asignar)
        return list(respuesta.context["form"].fields["censistas"].queryset)

    def test_solo_aparecen_los_censistas(self):
        """Asignar terreno a un supervisor rompería el control cruzado."""
        disponibles = self.disponibles()

        self.assertIn(self.marta, disponibles)
        self.assertNotIn(self.supervisor, disponibles)
        self.assertNotIn(self.admin, disponibles)

    def test_no_aparece_un_censista_deshabilitado(self):
        """No puede iniciar sesión: el sector parecería cubierto y no lo estaría."""
        self.juan.is_active = False
        self.juan.save()

        self.assertNotIn(self.juan, self.disponibles())

    def test_un_censista_deshabilitado_que_ya_tenia_el_sector_si_aparece(self):
        """El caso borde: si no apareciera, cualquier guardado lo retiraría en silencio."""
        self.asignar(censista=self.juan)
        self.juan.is_active = False
        self.juan.save()

        self.assertIn(self.juan, self.disponibles())

    def test_no_se_puede_asignar_a_alguien_fuera_de_la_lista(self):
        """Petición manipulada: se rechaza el POST completo."""
        respuesta = self.client.post(self.url_asignar, self.datos(self.supervisor))

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(self.boldos.esta_asignado)

    def test_el_rechazo_no_aplica_ningun_cambio_parcial(self):
        self.asignar(censista=self.marta)

        self.client.post(
            self.url_asignar,
            {"censistas": [self.marta.pk, self.supervisor.pk], "observaciones": ""},
        )

        # Marta sigue asignada: no se aplicó nada, ni siquiera la parte válida.
        self.assertEqual(list(self.boldos.censistas_asignados()), [self.marta])

    def test_avisa_cuando_no_hay_ningun_censista(self):
        Usuario.objects.filter(rol=self.rol_censista).update(is_active=False)

        respuesta = self.client.get(self.url_asignar)
        self.assertFalse(respuesta.context["hay_censistas"])


class EstadoInicialFormularioTest(BaseAsignacionTest):
    def test_el_formulario_llega_con_los_actuales_marcados(self):
        self.asignar(censista=self.marta)

        formulario = AsignarSectorForm(sector=self.boldos)

        self.assertEqual(formulario.fields["censistas"].initial, [self.marta.pk])

    def test_con_datos_enviados_no_se_pisa_lo_que_marco_el_usuario(self):
        """Tras un error de validación debe conservarse lo enviado, no la base."""
        self.asignar(censista=self.marta)

        formulario = AsignarSectorForm(
            {"censistas": [self.juan.pk]}, sector=self.boldos
        )

        self.assertTrue(formulario.is_valid())
        self.assertEqual(formulario.censistas_seleccionados(), [self.juan])

    def test_sin_datos_los_seleccionados_son_los_de_la_base(self):
        self.asignar(censista=self.marta)

        formulario = AsignarSectorForm(sector=self.boldos)

        self.assertEqual(formulario.censistas_seleccionados(), [self.marta])


# ==========================================================================
# 6. AUDITORÍA DEL REPARTO
# ==========================================================================


class AuditoriaRepartoTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)

    def test_asignar_registra_una_fila(self):
        self.client.post(self.url_asignar, self.datos(self.marta))
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.CAMBIAR_ASIGNACIONES)
        self.assertEqual(registro.administrador, self.supervisor)

    def test_la_fila_apunta_al_sector(self):
        """El reparto recae sobre un sector: reutiliza el tipo de la HU-05."""
        self.client.post(self.url_asignar, self.datos(self.marta))
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.objeto_tipo, TipoObjetoAuditoria.SECTOR)
        self.assertEqual(registro.objeto_nombre, "Los Boldos · Concepción")

    def test_el_detalle_dice_a_quien_se_asigno(self):
        self.client.post(self.url_asignar, self.datos(self.marta))
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertIn("asignados", registro.detalle)
        self.assertIn("Marta Soto", registro.detalle)
        self.assertIn("marta@opso.cl", registro.detalle)

    def test_el_detalle_dice_a_quien_se_retiro(self):
        self.asignar(censista=self.marta)

        self.client.post(self.url_asignar, self.datos())
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertIn("desasignados", registro.detalle)
        self.assertIn("Marta Soto", registro.detalle)

    def test_una_reasignacion_queda_en_UNA_sola_fila(self):
        """Entra uno y sale otro: es un hecho, no dos que haya que correlacionar."""
        self.asignar(censista=self.marta)
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url_asignar, self.datos(self.juan))

        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)
        registro = RegistroAuditoria.objects.latest("ocurrido_en")
        self.assertIn("asignados", registro.detalle)
        self.assertIn("desasignados", registro.detalle)

    def test_guardar_sin_cambios_no_escribe_en_la_bitacora(self):
        self.asignar(censista=self.marta)
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url_asignar, self.datos(self.marta))

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_si_falla_la_auditoria_no_se_guarda_el_reparto(self):
        """transaction.atomic: no puede quedar un reparto sin registrar."""
        from unittest.mock import patch

        with patch(
            "operativos.views_asignaciones.registrar_accion",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url_asignar, self.datos(self.marta))

        self.assertFalse(self.boldos.esta_asignado)

    def test_la_bitacora_muestra_el_cambio(self):
        self.client.post(self.url_asignar, self.datos(self.marta))
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("usuarios:auditoria"))
        self.assertContains(respuesta, "Cambió las asignaciones del sector")
        self.assertContains(respuesta, "Los Boldos")


class DescribirCambioAsignacionesTest(BaseAsignacionTest):
    def test_describe_lo_asignado(self):
        detalle = describir_cambio_asignaciones([], [self.marta])

        self.assertIn("asignados: Marta Soto (marta@opso.cl)", detalle)
        self.assertNotIn("desasignados", detalle)

    def test_describe_lo_retirado(self):
        detalle = describir_cambio_asignaciones([self.marta], [])

        # Se compara el valor EXACTO y no con assertNotIn("asignados:"): la palabra
        # «desasignados» contiene esa subcadena, así que esa comprobación pasaría
        # siempre o fallaría siempre por el motivo equivocado.
        self.assertEqual(detalle, "desasignados: Marta Soto (marta@opso.cl)")

    def test_describe_las_dos_cosas_a_la_vez(self):
        detalle = describir_cambio_asignaciones([self.marta], [self.juan])

        self.assertIn("asignados", detalle)
        self.assertIn("desasignados", detalle)

    def test_sin_cambios_devuelve_cadena_vacia(self):
        self.assertEqual(describir_cambio_asignaciones([self.marta], [self.marta]), "")

    def test_el_orden_es_estable_alfabetico(self):
        """Dos cambios idénticos deben leerse idénticos."""
        uno = describir_cambio_asignaciones([], [self.marta, self.juan])
        otro = describir_cambio_asignaciones([], [self.juan, self.marta])

        self.assertEqual(uno, otro)

    def test_usa_el_correo_para_desambiguar_homonimos(self):
        gemela = Usuario.objects.create_user(
            email="otra.marta@opso.cl",
            password=CLAVE_VALIDA,
            first_name="Marta",
            last_name="Soto",
            rol=self.rol_censista,
        )
        detalle = describir_cambio_asignaciones([], [self.marta, gemela])

        self.assertIn("marta@opso.cl", detalle)
        self.assertIn("otra.marta@opso.cl", detalle)

    def test_la_funcion_de_la_hu04_sigue_funcionando_igual(self):
        """La generalización no cambió el comportamiento de describir_cambio_permisos."""
        from usuarios.auditoria import describir_cambio_permisos

        permisos = list(Permiso.objects.filter(codigo="operativos.ver"))
        detalle = describir_cambio_permisos([], permisos)

        self.assertEqual(detalle, "concedidos: Consultar los operativos y sectores")


# ==========================================================================
# 7. RETIRAR UNA ASIGNACIÓN
# ==========================================================================


class RetirarTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)
        self.asignacion = self.asignar(censista=self.marta)
        self.url = reverse(
            "operativos:asignacion_retirar", kwargs={"pk": self.asignacion.pk}
        )

    def test_retirar_desactiva_la_asignacion(self):
        self.client.post(self.url)
        self.asignacion.refresh_from_db()

        self.assertFalse(self.asignacion.activa)
        self.assertIsNotNone(self.asignacion.desasignado_en)

    def test_retirar_no_borra_la_fila(self):
        self.client.post(self.url)

        self.assertTrue(AsignacionSector.objects.filter(pk=self.asignacion.pk).exists())

    def test_retirar_registra_la_accion(self):
        self.client.post(self.url)
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.CAMBIAR_ASIGNACIONES)
        self.assertIn("desasignados", registro.detalle)

    def test_el_get_no_modifica_nada(self):
        """Las peticiones GET deben ser seguras: es la regla que evita el CSRF."""
        self.client.get(self.url)
        self.asignacion.refresh_from_db()

        self.assertTrue(self.asignacion.activa)

    def test_retirar_dos_veces_no_escribe_dos_filas(self):
        self.client.post(self.url)
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_pantalla_avisa_si_el_sector_queda_sin_nadie(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(list(respuesta.context["otros"]), [])
        self.assertContains(respuesta, "sin personal")

    def test_la_pantalla_dice_quien_sigue_cubriendo(self):
        self.asignar(censista=self.juan)

        respuesta = self.client.get(self.url)

        self.assertEqual(len(respuesta.context["otros"]), 1)
        self.assertContains(respuesta, "sigue cubierto")

    def test_el_post_exige_token_csrf(self):
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.supervisor)

        self.assertEqual(cliente.post(self.url).status_code, 403)


# ==========================================================================
# 8. UN OPERATIVO CERRADO CONGELA EL REPARTO
# ==========================================================================


class RepartoCerradoTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)
        self.asignacion = self.asignar(censista=self.marta)

        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        self.url_retirar = reverse(
            "operativos:asignacion_retirar", kwargs={"pk": self.asignacion.pk}
        )

    def test_no_se_puede_abrir_la_pantalla_de_asignar(self):
        respuesta = self.client.get(self.url_asignar)
        self.assertRedirects(respuesta, self.url_panel)

    def test_no_se_puede_asignar_por_post_a_mano(self):
        """Ocultar el botón no es una validación: la URL se puede enviar."""
        self.client.post(self.url_asignar, self.datos(self.juan))

        self.assertEqual(list(self.boldos.censistas_asignados()), [self.marta])

    def test_no_se_puede_retirar_por_post_a_mano(self):
        self.client.post(self.url_retirar)
        self.asignacion.refresh_from_db()

        self.assertTrue(self.asignacion.activa)

    def test_el_rechazo_no_deja_rastro_en_la_bitacora(self):
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url_asignar, self.datos(self.juan))
        self.client.post(self.url_retirar)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_el_panel_si_se_puede_consultar(self):
        """El reparto histórico es información legítima: solo no se puede cambiar."""
        respuesta = self.client.get(self.url_panel)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["reparto_abierto"])

    def test_reabrir_el_operativo_devuelve_el_acceso(self):
        self.operativo.estado = EstadoOperativo.EN_CURSO
        self.operativo.save()

        self.assertEqual(self.client.get(self.url_asignar).status_code, 200)


class SectorDesactivadoTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)
        self.boldos.activo = False
        self.boldos.save()

    def test_no_se_puede_asignar_a_un_sector_desactivado(self):
        respuesta = self.client.get(self.url_asignar)
        self.assertRedirects(respuesta, self.url_panel)

    def test_tampoco_por_post(self):
        self.client.post(self.url_asignar, self.datos(self.marta))
        self.assertFalse(self.boldos.esta_asignado)


# ==========================================================================
# 9. EL PANEL DE REPARTO
# ==========================================================================


class PanelTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)

    def test_muestra_todos_los_sectores(self):
        respuesta = self.client.get(self.url_panel)
        self.assertEqual(len(respuesta.context["sectores"]), 2)

    def test_los_contadores_de_cobertura_son_correctos(self):
        self.asignar(sector=self.boldos)

        contexto = self.client.get(self.url_panel).context

        self.assertEqual(contexto["total_sectores"], 2)
        self.assertEqual(contexto["total_asignados"], 1)
        self.assertEqual(contexto["total_sin_asignar"], 1)

    def test_el_equipo_llega_filtrado_a_los_vigentes(self):
        retirada = self.asignar(censista=self.juan)
        retirada.desactivar()
        self.asignar(censista=self.marta)

        respuesta = self.client.get(self.url_panel)
        sector = next(
            s for s in respuesta.context["sectores"] if s.pk == self.boldos.pk
        )

        self.assertEqual([a.censista for a in sector.equipo], [self.marta])

    def test_el_contador_de_asignados_no_se_infla_con_las_zonas(self):
        """El sector tiene 2 zonas: el conteo de censistas debe seguir siendo 1."""
        self.asignar(censista=self.marta)

        respuesta = self.client.get(self.url_panel)
        sector = next(
            s for s in respuesta.context["sectores"] if s.pk == self.boldos.pk
        )

        self.assertEqual(sector.n_asignados, 1)

    def test_la_carga_del_sector_viene_anotada(self):
        respuesta = self.client.get(self.url_panel)
        sector = next(
            s for s in respuesta.context["sectores"] if s.pk == self.boldos.pk
        )

        self.assertEqual(sector.carga, 150)

    def test_filtra_los_sectores_sin_asignar(self):
        self.asignar(sector=self.boldos)

        respuesta = self.client.get(self.url_panel, {"cobertura": "sin_asignar"})

        self.assertEqual(
            [s.pk for s in respuesta.context["sectores"]], [self.norte.pk]
        )

    def test_filtra_los_sectores_ya_asignados(self):
        self.asignar(sector=self.boldos)

        respuesta = self.client.get(self.url_panel, {"cobertura": "asignados"})

        self.assertEqual(
            [s.pk for s in respuesta.context["sectores"]], [self.boldos.pk]
        )

    def test_filtra_por_censista(self):
        self.asignar(sector=self.boldos, censista=self.marta)
        self.asignar(sector=self.norte, censista=self.juan)

        respuesta = self.client.get(self.url_panel, {"censista": self.marta.pk})

        self.assertEqual(
            [s.pk for s in respuesta.context["sectores"]], [self.boldos.pk]
        )

    def test_busca_por_nombre_de_sector(self):
        respuesta = self.client.get(self.url_panel, {"q": "Boldos"})

        self.assertEqual(
            [s.pk for s in respuesta.context["sectores"]], [self.boldos.pk]
        )

    def test_un_filtro_invalido_no_rompe_el_panel(self):
        respuesta = self.client.get(self.url_panel, {"cobertura": "INVENTADO"})
        self.assertEqual(respuesta.status_code, 200)

    def test_el_filtro_de_censistas_solo_ofrece_los_desplegados(self):
        """Filtrar por alguien que no trabaja aquí daría siempre lista vacía."""
        self.asignar(censista=self.marta)

        respuesta = self.client.get(self.url_panel)
        opciones = list(respuesta.context["filtro"].fields["censista"].queryset)

        self.assertEqual(opciones, [self.marta])

    def test_la_carga_por_censista_suma_sus_sectores(self):
        self.asignar(sector=self.boldos, censista=self.marta)
        self.asignar(sector=self.norte, censista=self.marta)

        contexto = self.client.get(self.url_panel).context
        carga = contexto["carga_por_censista"][0]

        self.assertEqual(carga.n_sectores, 2)
        self.assertEqual(carga.viviendas, 150)

    def test_la_carga_por_censista_esta_vacia_sin_asignaciones(self):
        contexto = self.client.get(self.url_panel).context
        self.assertEqual(contexto["carga_por_censista"], [])


class PanelConsultasTest(BaseAsignacionTest):
    """El panel no debe pagar una consulta por sector.

    Mismo enfoque que OperativoDetalleConsultasTest de la HU-05: no se fija un
    número exacto —sería frágil— sino que se comprueba que el coste NO CREZCA con
    la cantidad de sectores y de asignaciones.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.supervisor)

    def poblar(self, cuantos, desde=0):
        for numero in range(desde, desde + cuantos):
            sector = Sector.objects.create(
                operativo=self.operativo,
                comuna=self.concepcion,
                nombre=f"Sector {numero}",
            )
            Zona.objects.create(
                sector=sector, nombre="Zona 1", viviendas_estimadas=10
            )
            AsignacionSector.objects.create(sector=sector, censista=self.marta)

    def contar_consultas(self):
        with CaptureQueriesContext(connection) as captura:
            self.client.get(self.url_panel)
        return len(captura.captured_queries)

    def test_el_numero_de_consultas_no_crece_con_los_sectores(self):
        self.poblar(2)
        con_dos = self.contar_consultas()

        self.poblar(4, desde=2)
        con_seis = self.contar_consultas()

        self.assertEqual(con_dos, con_seis)


# ==========================================================================
# 10. LO QUE VE EL CENSISTA
# ==========================================================================


class MisSectoresTest(BaseAsignacionTest):
    def setUp(self):
        super().setUp()
        self.url = reverse("operativos:mis_sectores")

    def test_el_censista_ve_sus_sectores_sin_ningun_permiso(self):
        """No tiene ningún permiso de operativos, y aun así debe poder entrar."""
        self.asignar(censista=self.marta)
        self.client.force_login(self.marta)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            [a.sector for a in respuesta.context["asignaciones"]], [self.boldos]
        )

    def test_no_ve_los_sectores_de_otra_persona(self):
        """La regla central: la vista filtra por request.user y no es parametrizable."""
        self.asignar(censista=self.juan)
        self.client.force_login(self.marta)

        respuesta = self.client.get(self.url)

        self.assertEqual(list(respuesta.context["asignaciones"]), [])

    def test_no_ve_los_sectores_que_ya_le_retiraron(self):
        asignacion = self.asignar(censista=self.marta)
        asignacion.desactivar()
        self.client.force_login(self.marta)

        respuesta = self.client.get(self.url)

        self.assertEqual(list(respuesta.context["asignaciones"]), [])

    def test_los_operativos_cerrados_van_aparte(self):
        """Mezclarlos obligaría a distinguir el trabajo pendiente leyendo fechas."""
        self.asignar(censista=self.marta)
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()
        self.client.force_login(self.marta)

        contexto = self.client.get(self.url).context

        self.assertEqual(list(contexto["asignaciones"]), [])
        self.assertEqual(len(contexto["historicas"]), 1)

    def test_muestra_su_carga_de_trabajo(self):
        self.asignar(censista=self.marta)
        self.client.force_login(self.marta)

        contexto = self.client.get(self.url).context

        self.assertEqual(contexto["total_sectores"], 1)
        self.assertEqual(contexto["total_viviendas"], 150)

    def test_sin_asignaciones_explica_que_hacer(self):
        self.client.force_login(self.marta)

        respuesta = self.client.get(self.url)

        self.assertEqual(contexto := list(respuesta.context["asignaciones"]), [])
        self.assertContains(respuesta, "Tu supervisor")

    def test_las_observaciones_del_supervisor_se_muestran(self):
        self.asignar(censista=self.marta, observaciones="Empezar por el pasaje sur")
        self.client.force_login(self.marta)

        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, "Empezar por el pasaje sur")

    def test_un_supervisor_sin_asignaciones_ve_su_propia_lista_vacia(self):
        """La vista no es solo para censistas: muestra el trabajo de quien entre."""
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["asignaciones"]), [])

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(self.url)
        self.assertIn(reverse("usuarios:login"), respuesta.url)


# ==========================================================================
# 11. INTEGRACIÓN CON EL RESTO DEL SISTEMA
# ==========================================================================


class IntegracionTest(BaseAsignacionTest):
    def test_el_panel_del_censista_muestra_sus_sectores(self):
        self.asignar(censista=self.marta)
        self.client.force_login(self.marta)

        respuesta = self.client.get(reverse("dashboards:censista"))

        self.assertContains(respuesta, "Los Boldos")

    def test_el_panel_del_censista_no_muestra_los_de_otro(self):
        self.asignar(censista=self.juan)
        self.client.force_login(self.marta)

        respuesta = self.client.get(reverse("dashboards:censista"))

        self.assertEqual(list(respuesta.context["mis_asignaciones"]), [])

    def test_el_panel_del_supervisor_cuenta_los_sectores_sin_asignar(self):
        self.asignar(sector=self.boldos)
        self.client.force_login(self.supervisor)

        contexto = self.client.get(reverse("dashboards:supervisor")).context

        self.assertEqual(contexto["sectores_asignados"], 1)
        self.assertEqual(contexto["sectores_sin_asignar"], 1)

    def test_el_panel_del_supervisor_enlaza_al_operativo_vigente(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(reverse("dashboards:supervisor"))

        self.assertEqual(respuesta.context["operativo_actual"], self.operativo)
        self.assertContains(respuesta, self.url_panel)

    def test_el_panel_del_supervisor_ignora_los_operativos_cerrados(self):
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()
        self.client.force_login(self.supervisor)

        contexto = self.client.get(reverse("dashboards:supervisor")).context

        self.assertEqual(contexto["sectores_sin_asignar"], 0)
        self.assertIsNone(contexto["operativo_actual"])

    def test_el_menu_ofrece_mis_sectores_a_quien_tiene_territorio(self):
        self.asignar(censista=self.marta)
        self.client.force_login(self.marta)

        respuesta = self.client.get(reverse("dashboards:censista"))

        self.assertContains(respuesta, reverse("operativos:mis_sectores"))

    def test_el_menu_lo_oculta_a_quien_no_tiene_territorio(self):
        self.client.force_login(self.juan)

        respuesta = self.client.get(reverse("dashboards:censista"))

        self.assertNotContains(respuesta, reverse("operativos:mis_sectores"))

    def test_la_ficha_del_operativo_muestra_quien_cubre_cada_sector(self):
        self.asignar(censista=self.marta)
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(self.operativo.get_absolute_url())

        self.assertContains(respuesta, "Marta Soto")

    def test_la_ficha_avisa_de_los_sectores_sin_nadie(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(self.operativo.get_absolute_url())

        self.assertContains(respuesta, "sin nadie a cargo")

    def test_el_reparto_no_rompe_la_desactivacion_de_una_comuna(self):
        """Las reglas de la HU-05 siguen valiendo con asignaciones encima."""
        self.asignar()

        permitido, _ = self.concepcion.puede_desactivarse()
        self.assertFalse(permitido)

    def test_las_historias_anteriores_siguen_funcionando(self):
        self.client.force_login(self.admin)

        for nombre in ("usuarios:lista", "usuarios:permisos", "operativos:operativo_lista"):
            with self.subTest(ruta=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_registrar_accion_sigue_exigiendo_un_objeto_afectado(self):
        with self.assertRaises(ValueError):
            registrar_accion(
                administrador=self.supervisor,
                accion=AccionAuditoria.CAMBIAR_ASIGNACIONES,
            )
