"""Pruebas automáticas de la HU-05 «Administrar comunas, sectores y zonas».

Se separan por app, igual que las historias anteriores separaron tests.py,
tests_gestion.py y tests_permisos.py: en la defensa se puede ejecutar solo esto y
mostrar qué cubre.

    python manage.py test operativos

Cada prueba sigue el patrón PREPARAR -> ACTUAR -> VERIFICAR y su nombre describe
la regla que comprueba, para que la salida del comando se lea como una lista de
requisitos cumplidos.
"""

from datetime import date, timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from usuarios.auditoria import registrar_accion
from usuarios.models import (
    AccionAuditoria,
    Permiso,
    RegistroAuditoria,
    Rol,
    RolCodigo,
    TipoObjetoAuditoria,
    Usuario,
)
from usuarios.templatetags.permisos import tiene_algun_permiso, tiene_permiso

from .forms import CambiarEstadoOperativoForm
from .models import Comuna, EstadoOperativo, Operativo, Region, Sector, Zona

CLAVE_VALIDA = "Censo2026#Opso"


class BaseTerritorialTest(TestCase):
    """Escenario común: los tres roles, las regiones sembradas y un operativo."""

    @classmethod
    def setUpTestData(cls):
        # Roles, permisos y regiones ya existen: los sembraron las migraciones de
        # datos. Que las pruebas dependan de ellas es deliberado: si alguien rompe
        # la siembra, estas pruebas lo detectan.
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

        cls.biobio = Region.objects.get(codigo="08")
        cls.metropolitana = Region.objects.get(codigo="13")

    def setUp(self):
        self.concepcion = Comuna.objects.create(region=self.biobio, nombre="Concepción")
        self.operativo = Operativo.objects.create(
            nombre="Censo Social 2026",
            fecha_inicio=date(2026, 3, 1),
            fecha_termino=date(2026, 3, 31),
        )

    # -- ayudantes ---------------------------------------------------------

    def crear_sector(self, nombre="Los Boldos", operativo=None, comuna=None):
        return Sector.objects.create(
            operativo=operativo or self.operativo,
            comuna=comuna or self.concepcion,
            nombre=nombre,
        )

    def conceder(self, rol, *codigos):
        rol.permisos.add(*Permiso.objects.filter(codigo__in=codigos))


# ==========================================================================
# 1. LA SIEMBRA DE REGIONES
# ==========================================================================


class RegionSiembraTest(BaseTerritorialTest):
    """La migración 0002 dejó el catálogo geográfico correcto."""

    def test_se_sembraron_las_dieciseis_regiones(self):
        self.assertEqual(Region.objects.count(), 16)

    def test_los_codigos_son_unicos(self):
        codigos = list(Region.objects.values_list("codigo", flat=True))
        self.assertEqual(len(codigos), len(set(codigos)))

    def test_el_orden_es_geografico_de_norte_a_sur(self):
        """Arica primero y Magallanes al final, no orden alfabético."""
        nombres = list(Region.objects.values_list("nombre", flat=True))
        self.assertEqual(nombres[0], "Región de Arica y Parinacota")
        self.assertEqual(nombres[-1], "Región de Magallanes y de la Antártica Chilena")

    def test_el_orden_no_coincide_con_el_codigo(self):
        """La Metropolitana (13) va antes que O'Higgins (06): es geografía, no código."""
        codigos = list(Region.objects.values_list("codigo", flat=True))
        self.assertLess(codigos.index("13"), codigos.index("06"))

    def test_nuble_va_entre_maule_y_biobio(self):
        """Ñuble se creó en 2018 con el código 16, pero geográficamente va décima."""
        codigos = list(Region.objects.values_list("codigo", flat=True))
        self.assertLess(codigos.index("07"), codigos.index("16"))
        self.assertLess(codigos.index("16"), codigos.index("08"))

    def test_el_codigo_conserva_el_cero_a_la_izquierda(self):
        """Guardado como texto: un entero perdería el 0 de «08»."""
        self.assertTrue(Region.objects.filter(codigo="08").exists())

    def test_str_devuelve_el_nombre(self):
        self.assertEqual(str(self.biobio), "Región del Biobío")


# ==========================================================================
# 2. EL MODELO COMUNA
# ==========================================================================


class ComunaModeloTest(BaseTerritorialTest):
    def test_una_comuna_nace_activa(self):
        self.assertTrue(self.concepcion.activa)

    def test_no_puede_haber_dos_comunas_homonimas_en_la_misma_region(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Comuna.objects.create(region=self.biobio, nombre="Concepción")

    def test_si_puede_haber_homonimas_en_regiones_distintas(self):
        """En Chile hay nombres de comuna repetidos entre regiones."""
        gemela = Comuna.objects.create(region=self.metropolitana, nombre="Concepción")
        self.assertNotEqual(gemela.pk, self.concepcion.pk)

    def test_nombre_completo_incluye_la_region(self):
        """Desambigua las homónimas en los desplegables."""
        self.assertEqual(
            self.concepcion.nombre_completo, "Concepción (Región del Biobío)"
        )

    def test_no_se_puede_borrar_una_region_con_comunas(self):
        """PROTECT: borrarla dejaría comunas sin ubicación."""
        with self.assertRaises(ProtectedError):
            self.biobio.delete()

    def test_una_comuna_sin_sectores_se_puede_desactivar(self):
        permitido, motivo = self.concepcion.puede_desactivarse()
        self.assertTrue(permitido)
        self.assertEqual(motivo, "")

    def test_una_comuna_con_sectores_vigentes_no_se_puede_desactivar(self):
        self.crear_sector()
        permitido, motivo = self.concepcion.puede_desactivarse()

        self.assertFalse(permitido)
        self.assertIn("1 sector", motivo)

    def test_si_el_operativo_esta_cerrado_la_comuna_si_se_puede_desactivar(self):
        """Sin trabajo vivo apuntando a ella, desactivarla es lo correcto."""
        self.crear_sector()
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        permitido, _ = self.concepcion.puede_desactivarse()
        self.assertTrue(permitido)

    def test_el_motivo_del_rechazo_explica_que_hacer(self):
        """No basta un booleano: la vista tiene que poder explicar el rechazo."""
        self.crear_sector()
        _, motivo = self.concepcion.puede_desactivarse()

        self.assertIn("Cierra esos operativos", motivo)


# ==========================================================================
# 3. EL MODELO OPERATIVO
# ==========================================================================


class OperativoModeloTest(BaseTerritorialTest):
    def test_un_operativo_nace_en_planificacion(self):
        self.assertEqual(self.operativo.estado, EstadoOperativo.PLANIFICACION)

    def test_el_nombre_es_unico(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Operativo.objects.create(
                    nombre="Censo Social 2026",
                    fecha_inicio=date(2027, 1, 1),
                    fecha_termino=date(2027, 1, 5),
                )

    def test_la_base_de_datos_rechaza_fechas_incoherentes(self):
        """El CheckConstraint protege incluso a un script que no use el formulario."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Operativo.objects.create(
                    nombre="Operativo imposible",
                    fecha_inicio=date(2026, 5, 10),
                    fecha_termino=date(2026, 5, 1),
                )

    def test_duracion_dias_cuenta_los_dos_extremos(self):
        """Del 1 al 31 de marzo son 31 días, no 30."""
        self.assertEqual(self.operativo.duracion_dias, 31)

    def test_un_operativo_de_un_solo_dia_dura_un_dia(self):
        corto = Operativo.objects.create(
            nombre="Jornada única",
            fecha_inicio=date(2026, 6, 1),
            fecha_termino=date(2026, 6, 1),
        )
        self.assertEqual(corto.duracion_dias, 1)

    def test_en_planificacion_admite_cambios_de_territorio(self):
        self.assertTrue(self.operativo.admite_cambios_de_territorio)

    def test_en_curso_admite_cambios_de_territorio(self):
        """En terreno aparecen realidades que la planificación no previó."""
        self.operativo.estado = EstadoOperativo.EN_CURSO
        self.assertTrue(self.operativo.admite_cambios_de_territorio)

    def test_cerrado_no_admite_cambios_de_territorio(self):
        self.operativo.estado = EstadoOperativo.CERRADO

        self.assertFalse(self.operativo.admite_cambios_de_territorio)
        self.assertTrue(self.operativo.esta_cerrado)

    def test_clean_rechaza_termino_anterior_al_inicio(self):
        operativo = Operativo(
            nombre="Otro",
            fecha_inicio=date(2026, 5, 10),
            fecha_termino=date(2026, 5, 1),
        )
        with self.assertRaises(ValidationError) as contexto:
            operativo.full_clean()

        self.assertIn("fecha_termino", contexto.exception.error_dict)

    def test_comunas_cubiertas_no_repite_la_misma_comuna(self):
        """Dos sectores en la misma comuna cuentan como una sola comuna."""
        self.crear_sector("Los Boldos")
        self.crear_sector("Barrio Norte")

        self.assertEqual(self.operativo.comunas_cubiertas().count(), 1)

    def test_total_zonas_cuenta_a_traves_de_los_sectores(self):
        sector = self.crear_sector()
        Zona.objects.create(sector=sector, nombre="Zona 1")
        Zona.objects.create(sector=sector, nombre="Zona 2")

        self.assertEqual(self.operativo.total_zonas(), 2)

    def test_vigente_es_falso_si_esta_en_planificacion(self):
        """Aunque hoy cayera dentro de las fechas: nadie está en terreno."""
        hoy = date.today()
        operativo = Operativo.objects.create(
            nombre="Operativo de hoy",
            fecha_inicio=hoy - timedelta(days=1),
            fecha_termino=hoy + timedelta(days=1),
        )
        self.assertFalse(operativo.vigente)

    def test_vigente_es_verdadero_en_curso_y_dentro_de_las_fechas(self):
        hoy = date.today()
        operativo = Operativo.objects.create(
            nombre="Operativo vigente",
            fecha_inicio=hoy - timedelta(days=1),
            fecha_termino=hoy + timedelta(days=1),
            estado=EstadoOperativo.EN_CURSO,
        )
        self.assertTrue(operativo.vigente)

    def test_vigente_es_falso_fuera_de_las_fechas(self):
        hoy = date.today()
        operativo = Operativo.objects.create(
            nombre="Operativo pasado",
            fecha_inicio=hoy - timedelta(days=30),
            fecha_termino=hoy - timedelta(days=20),
            estado=EstadoOperativo.EN_CURSO,
        )
        self.assertFalse(operativo.vigente)


# ==========================================================================
# 4. LOS MODELOS SECTOR Y ZONA
# ==========================================================================


class SectorZonaModeloTest(BaseTerritorialTest):
    def test_un_sector_nace_activo(self):
        self.assertTrue(self.crear_sector().activo)

    def test_no_se_repite_el_sector_en_el_mismo_operativo_y_comuna(self):
        self.crear_sector("Los Boldos")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.crear_sector("Los Boldos")

    def test_dos_operativos_si_pueden_tener_un_sector_con_el_mismo_nombre(self):
        """Son divisiones distintas del mismo lugar, hechas en momentos distintos.

        Es la consecuencia práctica de que el territorio cuelgue del operativo, y
        la razón por la que la restricción es la terna y no el nombre.
        """
        self.crear_sector("Los Boldos")
        otro = Operativo.objects.create(
            nombre="Censo Social 2027",
            fecha_inicio=date(2027, 3, 1),
            fecha_termino=date(2027, 3, 31),
        )

        gemelo = self.crear_sector("Los Boldos", operativo=otro)
        self.assertEqual(gemelo.nombre, "Los Boldos")

    def test_borrar_el_operativo_arrastra_sus_sectores(self):
        """CASCADE: un sector no significa nada sin su operativo."""
        self.crear_sector()
        self.operativo.delete()

        self.assertEqual(Sector.objects.count(), 0)

    def test_no_se_puede_borrar_una_comuna_con_sectores(self):
        """PROTECT: la comuna es geografía compartida."""
        self.crear_sector()
        with self.assertRaises(ProtectedError):
            self.concepcion.delete()

    def test_nombre_completo_del_sector_incluye_la_comuna(self):
        self.assertEqual(self.crear_sector().nombre_completo, "Los Boldos · Concepción")

    def test_no_se_repite_la_zona_dentro_del_sector(self):
        sector = self.crear_sector()
        Zona.objects.create(sector=sector, nombre="Zona 1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Zona.objects.create(sector=sector, nombre="Zona 1")

    def test_dos_sectores_si_pueden_tener_una_zona_1(self):
        """Casi todos los sectores tienen una «Zona 1»."""
        uno = self.crear_sector("Los Boldos")
        otro = self.crear_sector("Barrio Norte")

        Zona.objects.create(sector=uno, nombre="Zona 1")
        Zona.objects.create(sector=otro, nombre="Zona 1")

        self.assertEqual(Zona.objects.filter(nombre="Zona 1").count(), 2)

    def test_borrar_el_sector_arrastra_sus_zonas(self):
        sector = self.crear_sector()
        Zona.objects.create(sector=sector, nombre="Zona 1")

        sector.delete()

        self.assertEqual(Zona.objects.count(), 0)

    def test_nombre_completo_de_la_zona_lleva_el_camino_entero(self):
        """«Zona 1» a secas no identifica nada en una bitácora."""
        zona = Zona.objects.create(sector=self.crear_sector(), nombre="Zona 1")
        self.assertEqual(zona.nombre_completo, "Zona 1 · Los Boldos · Concepción")

    def test_la_zona_conoce_su_operativo_dos_niveles_arriba(self):
        zona = Zona.objects.create(sector=self.crear_sector(), nombre="Zona 1")
        self.assertEqual(zona.operativo, self.operativo)

    def test_las_viviendas_estimadas_son_opcionales(self):
        """Muchas veces no se sabe hasta llegar a terreno."""
        zona = Zona.objects.create(sector=self.crear_sector(), nombre="Zona 1")
        self.assertIsNone(zona.viviendas_estimadas)


# ==========================================================================
# 5. CONTROL DE ACCESO POR PERMISO
# ==========================================================================


class AccesoPorPermisoTest(BaseTerritorialTest):
    """El módulo se protege con los permisos que la HU-04 ya había sembrado."""

    def setUp(self):
        super().setUp()
        self.sector = self.crear_sector()
        self.zona = Zona.objects.create(sector=self.sector, nombre="Zona 1")

        self.rutas_consulta = [
            ("operativos:operativo_lista", {}),
            ("operativos:operativo_detalle", {"pk": self.operativo.pk}),
            ("operativos:comuna_lista", {}),
        ]
        self.rutas_gestion = [
            ("operativos:operativo_crear", {}),
            ("operativos:operativo_editar", {"pk": self.operativo.pk}),
            ("operativos:operativo_estado", {"pk": self.operativo.pk}),
            ("operativos:comuna_crear", {}),
            ("operativos:comuna_editar", {"pk": self.concepcion.pk}),
            ("operativos:comuna_desactivar", {"pk": self.concepcion.pk}),
            ("operativos:sector_crear", {"operativo_pk": self.operativo.pk}),
            ("operativos:sector_editar", {"pk": self.sector.pk}),
            ("operativos:sector_desactivar", {"pk": self.sector.pk}),
            ("operativos:zona_crear", {"sector_pk": self.sector.pk}),
            ("operativos:zona_editar", {"pk": self.zona.pk}),
            ("operativos:zona_desactivar", {"pk": self.zona.pk}),
        ]

    # -- el catálogo de permisos no cambió ---------------------------------

    def test_la_historia_no_agrego_permisos_al_catalogo(self):
        """Reutiliza los de la HU-04: es la ventaja de ese diseño, comprobada."""
        self.assertTrue(Permiso.objects.filter(codigo="operativos.ver").exists())
        self.assertTrue(Permiso.objects.filter(codigo="operativos.gestionar").exists())
        # ver, asignar_sector y gestionar: los mismos tres que sembró la HU-04.
        self.assertEqual(Permiso.objects.filter(modulo="OPERATIVOS").count(), 3)

    # -- consulta ----------------------------------------------------------

    def test_el_administrador_entra_a_todo(self):
        self.client.force_login(self.admin)
        for nombre, kwargs in self.rutas_consulta + self.rutas_gestion:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 200)

    def test_el_supervisor_consulta_porque_la_hu04_le_dio_operativos_ver(self):
        """No hay que conceder nada: el reparto inicial ya lo incluía."""
        self.client.force_login(self.supervisor)
        for nombre, kwargs in self.rutas_consulta:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 200)

    def test_el_supervisor_no_puede_gestionar(self):
        """Consultar no es planificar: son dos permisos distintos a propósito."""
        self.client.force_login(self.supervisor)
        for nombre, kwargs in self.rutas_gestion:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 302)

    def test_el_censista_no_entra_a_nada(self):
        self.client.force_login(self.censista)
        for nombre, kwargs in self.rutas_consulta + self.rutas_gestion:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 302)

    def test_un_visitante_anonimo_va_al_login(self):
        respuesta = self.client.get(reverse("operativos:operativo_lista"))
        self.assertIn(reverse("usuarios:login"), respuesta.url)

    # -- lo que la HU-04 hace posible --------------------------------------

    def test_conceder_gestionar_abre_la_planificacion_sin_tocar_codigo(self):
        """El objetivo del diseño de la HU-04, comprobado sobre la HU-05."""
        url = reverse("operativos:operativo_crear")
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 302)

        self.conceder(self.rol_supervisor, "operativos.gestionar")

        self.assertEqual(self.client.get(url).status_code, 200)

    def test_revocar_ver_cierra_la_consulta(self):
        self.rol_supervisor.permisos.remove(
            Permiso.objects.get(codigo="operativos.ver")
        )
        self.client.force_login(self.supervisor)

        self.assertEqual(
            self.client.get(reverse("operativos:operativo_lista")).status_code, 302
        )

    def test_desactivar_el_rol_cierra_el_modulo(self):
        self.rol_supervisor.activo = False
        self.rol_supervisor.save()

        self.client.force_login(self.supervisor)
        self.assertEqual(
            self.client.get(reverse("operativos:operativo_lista")).status_code, 302
        )


# ==========================================================================
# 6. CRUD DE COMUNAS
# ==========================================================================


class ComunaCrudTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_crear_una_comuna(self):
        respuesta = self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.metropolitana.pk, "nombre": "Puente Alto"},
        )
        self.assertRedirects(respuesta, reverse("operativos:comuna_lista"))
        self.assertTrue(Comuna.objects.filter(nombre="Puente Alto").exists())

    def test_crear_registra_una_fila_de_auditoria(self):
        self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.metropolitana.pk, "nombre": "Puente Alto"},
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.CREAR_TERRITORIO)
        self.assertEqual(registro.objeto_tipo, TipoObjetoAuditoria.COMUNA)
        self.assertIn("Puente Alto", registro.objeto_nombre)
        self.assertEqual(registro.administrador, self.admin)

    def test_el_nombre_se_limpia_de_espacios(self):
        """«Concepción » y «Concepción» serían dos comunas para PostgreSQL."""
        self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.metropolitana.pk, "nombre": "  Puente Alto  "},
        )
        self.assertTrue(Comuna.objects.filter(nombre="Puente Alto").exists())

    def test_no_se_puede_duplicar_en_la_misma_region(self):
        respuesta = self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.biobio.pk, "nombre": "Concepción"},
        )
        # No redirige: vuelve al formulario con el error junto al campo.
        self.assertEqual(respuesta.status_code, 200)
        self.assertFormError(
            respuesta.context["form"],
            "nombre",
            "Ya existe una comuna llamada «Concepción» en Región del Biobío. "
            "Los nombres no se repiten dentro de una misma región.",
        )

    def test_el_duplicado_no_distingue_mayusculas(self):
        """«TALCAHUANO» es la misma comuna que «Talcahuano».

        Se usa un nombre SIN TILDES a propósito, y conviene poder explicar por qué:
        la comprobación usa `nombre__iexact`, que cada motor traduce a lo suyo.
        PostgreSQL —el motor de desarrollo y producción— lo resuelve con UPPER() y
        pliega correctamente los caracteres acentuados, así que allí «CONCEPCIÓN»
        también se detecta como duplicado de «Concepción». SQLite, que solo se usa
        para poder ejecutar las pruebas sin levantar PostgreSQL, únicamente pliega
        el rango ASCII y no reconocería Ó como la misma letra que ó.

        Con un nombre ASCII la prueba comprueba exactamente la misma regla y da el
        mismo resultado en los dos motores. Verificar el plegado de tildes aquí no
        estaría probando el código de OPSO, sino la tabla de caracteres de SQLite.
        """
        Comuna.objects.create(region=self.biobio, nombre="Talcahuano")

        respuesta = self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.biobio.pk, "nombre": "TALCAHUANO"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            Comuna.objects.filter(region=self.biobio, nombre__in=["Talcahuano", "TALCAHUANO"]).count(),
            1,
        )

    def test_si_se_puede_repetir_el_nombre_en_otra_region(self):
        respuesta = self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.metropolitana.pk, "nombre": "Concepción"},
        )
        self.assertRedirects(respuesta, reverse("operativos:comuna_lista"))
        self.assertEqual(Comuna.objects.filter(nombre="Concepción").count(), 2)

    def test_editar_no_choca_consigo_misma(self):
        """Sin excluirse, una comuna nunca podría guardarse sin cambiar de nombre."""
        respuesta = self.client.post(
            reverse("operativos:comuna_editar", kwargs={"pk": self.concepcion.pk}),
            {"region": self.biobio.pk, "nombre": "Concepción"},
        )
        self.assertRedirects(respuesta, reverse("operativos:comuna_lista"))

    def test_editar_registra_solo_lo_que_cambio(self):
        self.client.post(
            reverse("operativos:comuna_editar", kwargs={"pk": self.concepcion.pk}),
            {"region": self.biobio.pk, "nombre": "Concepción Centro"},
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.EDITAR_TERRITORIO)
        self.assertIn("Concepción Centro", registro.detalle)

    def test_guardar_sin_cambios_no_escribe_en_la_bitacora(self):
        antes = RegistroAuditoria.objects.count()

        self.client.post(
            reverse("operativos:comuna_editar", kwargs={"pk": self.concepcion.pk}),
            {"region": self.biobio.pk, "nombre": "Concepción"},
        )

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_el_formulario_de_edicion_no_incluye_el_campo_activa(self):
        """Se cambia desde la pantalla de confirmación, no editando datos."""
        respuesta = self.client.get(
            reverse("operativos:comuna_editar", kwargs={"pk": self.concepcion.pk})
        )
        self.assertNotIn("activa", respuesta.context["form"].fields)


class ComunaDesactivarTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse(
            "operativos:comuna_desactivar", kwargs={"pk": self.concepcion.pk}
        )

    def test_desactivar_no_borra_la_fila(self):
        self.client.post(self.url)
        self.concepcion.refresh_from_db()

        self.assertFalse(self.concepcion.activa)
        self.assertTrue(Comuna.objects.filter(pk=self.concepcion.pk).exists())

    def test_desactivar_registra_la_accion(self):
        self.client.post(self.url)
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.DESACTIVAR_TERRITORIO)

    def test_activar_registra_su_propia_accion(self):
        self.concepcion.activa = False
        self.concepcion.save()

        self.client.post(
            reverse("operativos:comuna_activar", kwargs={"pk": self.concepcion.pk})
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.ACTIVAR_TERRITORIO)

    def test_no_se_desactiva_una_comuna_con_sectores_vigentes(self):
        """La regla se comprueba en el POST, no solo ocultando el botón."""
        self.crear_sector()

        self.client.post(self.url)
        self.concepcion.refresh_from_db()

        self.assertTrue(self.concepcion.activa)

    def test_el_rechazo_no_deja_rastro_en_la_bitacora(self):
        self.crear_sector()
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_desactivar_dos_veces_no_escribe_dos_filas(self):
        """Recargar la página o abrir el enlace dos veces no es un hecho nuevo."""
        self.client.post(self.url)
        antes = RegistroAuditoria.objects.count()

        self.client.post(self.url)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_el_get_solo_muestra_la_confirmacion_sin_modificar_nada(self):
        """Las peticiones GET deben ser seguras: es la regla de HTTP que evita CSRF."""
        self.client.get(self.url)
        self.concepcion.refresh_from_db()

        self.assertTrue(self.concepcion.activa)

    def test_el_post_exige_token_csrf(self):
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.admin)

        respuesta = cliente.post(self.url)

        self.assertEqual(respuesta.status_code, 403)


# ==========================================================================
# 7. CRUD DE OPERATIVOS
# ==========================================================================


class OperativoCrudTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def datos(self, **cambios):
        base = {
            "nombre": "Censo Social 2027",
            "descripcion": "Segundo levantamiento.",
            "fecha_inicio": "2027-03-01",
            "fecha_termino": "2027-03-31",
        }
        base.update(cambios)
        return base

    def test_crear_un_operativo(self):
        self.client.post(reverse("operativos:operativo_crear"), self.datos())
        self.assertTrue(Operativo.objects.filter(nombre="Censo Social 2027").exists())

    def test_el_operativo_nuevo_queda_en_planificacion(self):
        self.client.post(reverse("operativos:operativo_crear"), self.datos())
        nuevo = Operativo.objects.get(nombre="Censo Social 2027")

        self.assertEqual(nuevo.estado, EstadoOperativo.PLANIFICACION)

    def test_se_guarda_quien_lo_creo(self):
        self.client.post(reverse("operativos:operativo_crear"), self.datos())
        nuevo = Operativo.objects.get(nombre="Censo Social 2027")

        self.assertEqual(nuevo.creado_por, self.admin)

    def test_crear_registra_auditoria_con_las_fechas_en_el_detalle(self):
        self.client.post(reverse("operativos:operativo_crear"), self.datos())
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.CREAR_TERRITORIO)
        self.assertEqual(registro.objeto_tipo, TipoObjetoAuditoria.OPERATIVO)
        self.assertIn("31 días", registro.detalle)

    def test_rechaza_fecha_de_termino_anterior_al_inicio(self):
        respuesta = self.client.post(
            reverse("operativos:operativo_crear"),
            self.datos(fecha_inicio="2027-03-31", fecha_termino="2027-03-01"),
        )
        self.assertFormError(
            respuesta.context["form"],
            "fecha_termino",
            "La fecha de término no puede ser anterior a la de inicio.",
        )

    def test_el_error_de_fechas_va_en_el_campo_y_no_arriba(self):
        """Comprobarlo también en el formulario pone el mensaje donde se mira."""
        respuesta = self.client.post(
            reverse("operativos:operativo_crear"),
            self.datos(fecha_inicio="2027-03-31", fecha_termino="2027-03-01"),
        )
        self.assertEqual(respuesta.context["form"].non_field_errors(), [])

    def test_no_se_crea_nada_si_las_fechas_son_incoherentes(self):
        self.client.post(
            reverse("operativos:operativo_crear"),
            self.datos(fecha_inicio="2027-03-31", fecha_termino="2027-03-01"),
        )
        self.assertFalse(Operativo.objects.filter(nombre="Censo Social 2027").exists())

    def test_un_operativo_de_un_solo_dia_es_valido(self):
        self.client.post(
            reverse("operativos:operativo_crear"),
            self.datos(fecha_inicio="2027-03-01", fecha_termino="2027-03-01"),
        )
        self.assertTrue(Operativo.objects.filter(nombre="Censo Social 2027").exists())

    def test_editar_un_operativo_cerrado_si_esta_permitido(self):
        """Corregir una fecha mal escrita no altera el territorio."""
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        respuesta = self.client.get(
            reverse("operativos:operativo_editar", kwargs={"pk": self.operativo.pk})
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_el_formulario_no_incluye_el_campo_estado(self):
        respuesta = self.client.get(reverse("operativos:operativo_crear"))
        self.assertNotIn("estado", respuesta.context["form"].fields)


# ==========================================================================
# 8. CAMBIO DE ESTADO DEL OPERATIVO
# ==========================================================================


class OperativoEstadoTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse(
            "operativos:operativo_estado", kwargs={"pk": self.operativo.pk}
        )

    def test_de_planificacion_se_puede_pasar_a_en_curso(self):
        self.client.post(self.url, {"estado": EstadoOperativo.EN_CURSO})
        self.operativo.refresh_from_db()

        self.assertEqual(self.operativo.estado, EstadoOperativo.EN_CURSO)

    def test_de_planificacion_no_se_puede_volver_a_planificacion(self):
        respuesta = self.client.post(self.url, {"estado": EstadoOperativo.PLANIFICACION})
        self.operativo.refresh_from_db()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.operativo.estado, EstadoOperativo.PLANIFICACION)

    def test_un_operativo_cerrado_solo_puede_reabrirse_a_en_curso(self):
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        formulario = CambiarEstadoOperativoForm(operativo=self.operativo)
        opciones = [valor for valor, _ in formulario.fields["estado"].choices]

        self.assertEqual(opciones, [EstadoOperativo.EN_CURSO])

    def test_una_transicion_invalida_se_rechaza_aunque_llegue_manipulada(self):
        """Segunda comprobación contra TRANSICIONES, no solo contra choices."""
        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        formulario = CambiarEstadoOperativoForm(
            {"estado": EstadoOperativo.PLANIFICACION}, operativo=self.operativo
        )
        self.assertFalse(formulario.is_valid())

    def test_el_cambio_registra_el_antes_y_el_despues(self):
        self.client.post(self.url, {"estado": EstadoOperativo.EN_CURSO})
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.accion, AccionAuditoria.CAMBIAR_ESTADO_OPERATIVO)
        self.assertIn("En planificación", registro.detalle)
        self.assertIn("En curso", registro.detalle)

    def test_el_motivo_queda_en_la_bitacora(self):
        self.client.post(
            self.url,
            {"estado": EstadoOperativo.EN_CURSO, "motivo": "Se adelantó el terreno"},
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertIn("Se adelantó el terreno", registro.detalle)

    def test_el_motivo_es_opcional(self):
        respuesta = self.client.post(self.url, {"estado": EstadoOperativo.EN_CURSO})
        self.assertRedirects(respuesta, self.operativo.get_absolute_url())

    def test_el_post_exige_token_csrf(self):
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.admin)

        respuesta = cliente.post(self.url, {"estado": EstadoOperativo.EN_CURSO})

        self.assertEqual(respuesta.status_code, 403)


# ==========================================================================
# 9. SECTORES Y ZONAS: EL TERRITORIO
# ==========================================================================


class SectorCrudTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url_crear = reverse(
            "operativos:sector_crear", kwargs={"operativo_pk": self.operativo.pk}
        )

    def test_crear_un_sector(self):
        self.client.post(
            self.url_crear,
            {"comuna": self.concepcion.pk, "nombre": "Los Boldos", "descripcion": ""},
        )
        self.assertTrue(Sector.objects.filter(nombre="Los Boldos").exists())

    def test_el_sector_queda_en_el_operativo_de_la_url(self):
        """El operativo NO viene del formulario: no se puede manipular."""
        self.client.post(
            self.url_crear,
            {"comuna": self.concepcion.pk, "nombre": "Los Boldos", "descripcion": ""},
        )
        sector = Sector.objects.get(nombre="Los Boldos")

        self.assertEqual(sector.operativo, self.operativo)

    def test_el_formulario_no_tiene_campo_operativo(self):
        respuesta = self.client.get(self.url_crear)
        self.assertNotIn("operativo", respuesta.context["form"].fields)

    def test_crear_registra_auditoria_con_el_camino_completo(self):
        self.client.post(
            self.url_crear,
            {"comuna": self.concepcion.pk, "nombre": "Los Boldos", "descripcion": ""},
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.objeto_tipo, TipoObjetoAuditoria.SECTOR)
        self.assertEqual(registro.objeto_nombre, "Los Boldos · Concepción")

    def test_no_se_duplica_el_sector_en_el_mismo_operativo(self):
        self.crear_sector("Los Boldos")

        respuesta = self.client.post(
            self.url_crear,
            {"comuna": self.concepcion.pk, "nombre": "Los Boldos", "descripcion": ""},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Sector.objects.filter(nombre="Los Boldos").count(), 1)

    def test_solo_se_ofrecen_comunas_activas(self):
        self.concepcion.activa = False
        self.concepcion.save()

        respuesta = self.client.get(self.url_crear)
        comunas = respuesta.context["form"].fields["comuna"].queryset

        self.assertNotIn(self.concepcion, comunas)

    def test_al_editar_se_ofrece_su_propia_comuna_aunque_este_desactivada(self):
        """Si no, el sector quedaría imposible de guardar. Es el caso borde real."""
        sector = self.crear_sector()
        self.concepcion.activa = False
        self.concepcion.save()

        respuesta = self.client.get(
            reverse("operativos:sector_editar", kwargs={"pk": sector.pk})
        )
        comunas = respuesta.context["form"].fields["comuna"].queryset

        self.assertIn(self.concepcion, comunas)

    def test_avisa_cuando_no_hay_ninguna_comuna_activa(self):
        self.concepcion.activa = False
        self.concepcion.save()

        respuesta = self.client.get(self.url_crear)
        self.assertFalse(respuesta.context["hay_comunas"])


class ZonaCrudTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.sector = self.crear_sector()
        self.url_crear = reverse(
            "operativos:zona_crear", kwargs={"sector_pk": self.sector.pk}
        )

    def test_crear_una_zona(self):
        self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": 120},
        )
        self.assertTrue(Zona.objects.filter(nombre="Zona 1").exists())

    def test_la_zona_queda_en_el_sector_de_la_url(self):
        self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": ""},
        )
        self.assertEqual(Zona.objects.get(nombre="Zona 1").sector, self.sector)

    def test_las_viviendas_estimadas_pueden_ir_vacias(self):
        self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": ""},
        )
        self.assertIsNone(Zona.objects.get(nombre="Zona 1").viviendas_estimadas)

    def test_cero_viviendas_se_rechaza_con_un_mensaje_util(self):
        """0 no es un dato, es un error de tipeo: si no se sabe, se deja vacío."""
        respuesta = self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": 0},
        )
        self.assertFormError(
            respuesta.context["form"],
            "viviendas_estimadas",
            "Si no conoces el número de viviendas, deja el campo vacío en vez de "
            "escribir 0.",
        )

    def test_no_se_duplica_la_zona_en_el_sector(self):
        Zona.objects.create(sector=self.sector, nombre="Zona 1")

        respuesta = self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": ""},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Zona.objects.filter(sector=self.sector).count(), 1)

    def test_crear_registra_auditoria_con_el_camino_completo(self):
        self.client.post(
            self.url_crear,
            {"nombre": "Zona 1", "descripcion": "", "viviendas_estimadas": ""},
        )
        registro = RegistroAuditoria.objects.latest("ocurrido_en")

        self.assertEqual(registro.objeto_tipo, TipoObjetoAuditoria.ZONA)
        self.assertEqual(registro.objeto_nombre, "Zona 1 · Los Boldos · Concepción")


# ==========================================================================
# 10. LA REGLA POR OBJETO: UN OPERATIVO CERRADO CONGELA SU TERRITORIO
# ==========================================================================


class OperativoCerradoTest(BaseTerritorialTest):
    """Ningún permiso de la matriz permite reescribir la historia de un operativo."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.sector = self.crear_sector()
        self.zona = Zona.objects.create(sector=self.sector, nombre="Zona 1")

        self.operativo.estado = EstadoOperativo.CERRADO
        self.operativo.save()

        self.rutas = [
            ("operativos:sector_crear", {"operativo_pk": self.operativo.pk}),
            ("operativos:sector_editar", {"pk": self.sector.pk}),
            ("operativos:sector_desactivar", {"pk": self.sector.pk}),
            ("operativos:zona_crear", {"sector_pk": self.sector.pk}),
            ("operativos:zona_editar", {"pk": self.zona.pk}),
            ("operativos:zona_desactivar", {"pk": self.zona.pk}),
        ]

    def test_ninguna_pantalla_de_territorio_se_abre(self):
        for nombre, kwargs in self.rutas:
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertRedirects(respuesta, self.operativo.get_absolute_url())

    def test_tampoco_por_post_escribiendo_la_url_a_mano(self):
        """Ocultar el botón no es una validación: la URL se puede escribir."""
        respuesta = self.client.post(
            reverse("operativos:sector_desactivar", kwargs={"pk": self.sector.pk})
        )
        self.sector.refresh_from_db()

        self.assertTrue(self.sector.activo)
        self.assertRedirects(respuesta, self.operativo.get_absolute_url())

    def test_no_se_crea_ningun_sector_nuevo(self):
        self.client.post(
            reverse(
                "operativos:sector_crear", kwargs={"operativo_pk": self.operativo.pk}
            ),
            {"comuna": self.concepcion.pk, "nombre": "Nuevo", "descripcion": ""},
        )
        self.assertFalse(Sector.objects.filter(nombre="Nuevo").exists())

    def test_el_rechazo_no_deja_rastro_en_la_bitacora(self):
        antes = RegistroAuditoria.objects.count()

        for nombre, kwargs in self.rutas:
            self.client.post(reverse(nombre, kwargs=kwargs))

        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_reabrir_el_operativo_devuelve_el_acceso(self):
        self.client.post(
            reverse("operativos:operativo_estado", kwargs={"pk": self.operativo.pk}),
            {"estado": EstadoOperativo.EN_CURSO},
        )

        respuesta = self.client.get(
            reverse(
                "operativos:sector_crear", kwargs={"operativo_pk": self.operativo.pk}
            )
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_sin_permiso_se_avisa_del_permiso_y_no_del_estado(self):
        """El orden de los mixins importa: la autorización va antes que el estado.

        Si se comprobara primero el estado, alguien sin permiso averiguaría si un
        operativo existe y en qué estado está por la diferencia entre los mensajes.
        """
        self.client.force_login(self.censista)

        respuesta = self.client.get(
            reverse(
                "operativos:sector_crear", kwargs={"operativo_pk": self.operativo.pk}
            ),
            follow=True,
        )
        mensajes = [str(m) for m in respuesta.context["messages"]]

        self.assertTrue(any("permiso" in m for m in mensajes))
        self.assertFalse(any("está cerrado" in m for m in mensajes))


# ==========================================================================
# 11. LA FICHA DEL OPERATIVO
# ==========================================================================


class OperativoDetalleTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

        self.boldos = self.crear_sector("Los Boldos")
        self.norte = self.crear_sector("Barrio Norte")
        Zona.objects.create(
            sector=self.boldos, nombre="Zona 1", viviendas_estimadas=100
        )
        Zona.objects.create(sector=self.boldos, nombre="Zona 2", viviendas_estimadas=50)

        self.url = self.operativo.get_absolute_url()

    def test_agrupa_los_sectores_por_comuna(self):
        grupos = self.client.get(self.url).context["grupos"]

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["comuna"], self.concepcion)
        self.assertEqual(len(grupos[0]["sectores"]), 2)

    def test_separa_los_grupos_de_comunas_distintas(self):
        santiago = Comuna.objects.create(region=self.metropolitana, nombre="Santiago")
        self.crear_sector("Centro", comuna=santiago)

        grupos = self.client.get(self.url).context["grupos"]
        self.assertEqual(len(grupos), 2)

    def test_las_comunas_salen_ordenadas_de_norte_a_sur(self):
        """La Metropolitana antes que el Biobío: es el orden geográfico."""
        santiago = Comuna.objects.create(region=self.metropolitana, nombre="Santiago")
        self.crear_sector("Centro", comuna=santiago)

        grupos = self.client.get(self.url).context["grupos"]
        self.assertEqual(grupos[0]["comuna"], santiago)

    def test_los_contadores_son_correctos(self):
        contexto = self.client.get(self.url).context

        self.assertEqual(contexto["total_sectores"], 2)
        self.assertEqual(contexto["total_zonas"], 2)
        self.assertEqual(contexto["total_comunas"], 1)
        self.assertEqual(contexto["viviendas_estimadas"], 150)

    def test_las_viviendas_sin_estimar_no_rompen_la_suma(self):
        Zona.objects.create(sector=self.norte, nombre="Zona 1")

        contexto = self.client.get(self.url).context
        self.assertEqual(contexto["viviendas_estimadas"], 150)

    def test_un_operativo_sin_territorio_no_falla(self):
        vacio = Operativo.objects.create(
            nombre="Sin territorio",
            fecha_inicio=date(2028, 1, 1),
            fecha_termino=date(2028, 1, 5),
        )
        respuesta = self.client.get(vacio.get_absolute_url())

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["grupos"], [])


class OperativoDetalleConsultasTest(BaseTerritorialTest):
    """El prefetch anidado evita el problema N+1 al recorrer el árbol.

    Se aísla en su propia clase porque mide CONSULTAS y necesita controlar
    exactamente cuántos datos hay.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def poblar(self, cuantos_sectores, desde=0):
        for numero in range(desde, desde + cuantos_sectores):
            sector = self.crear_sector(f"Sector {numero}")
            for zona in range(3):
                Zona.objects.create(sector=sector, nombre=f"Zona {zona}")

    def contar_consultas(self):
        """Consultas que cuesta dibujar la ficha completa una vez."""
        with CaptureQueriesContext(connection) as captura:
            self.client.get(self.operativo.get_absolute_url())
        return len(captura.captured_queries)

    def test_el_numero_de_consultas_no_crece_con_el_territorio(self):
        """No se comprueba un número exacto, sino que sea CONSTANTE.

        Un número fijo con assertNumQueries sería frágil: cambiaría si Django
        ajustara cómo carga la sesión o el usuario, y la prueba fallaría sin que
        nada de esta historia estuviera mal. Lo que la HU-05 necesita garantizar
        es otra cosa: que el coste NO DEPENDA del tamaño del territorio. Para eso
        basta medir dos veces y comparar.

        Si alguien quita el prefetch_related de OperativoDetailView, la segunda
        medición se dispara y esta prueba falla.
        """
        self.poblar(2)
        con_dos_sectores = self.contar_consultas()

        self.poblar(4, desde=2)  # ahora son 6 sectores y 18 zonas
        con_seis_sectores = self.contar_consultas()

        self.assertEqual(con_dos_sectores, con_seis_sectores)


# ==========================================================================
# 12. LISTADOS: BÚSQUEDA, FILTROS Y CONSULTAS
# ==========================================================================


class ListadosTest(BaseTerritorialTest):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

        self.cerrado = Operativo.objects.create(
            nombre="Censo Piloto 2025",
            fecha_inicio=date(2025, 1, 1),
            fecha_termino=date(2025, 1, 10),
            estado=EstadoOperativo.CERRADO,
        )

    def test_el_listado_muestra_todos_los_operativos(self):
        respuesta = self.client.get(reverse("operativos:operativo_lista"))
        self.assertEqual(len(respuesta.context["operativos"]), 2)

    def test_filtra_por_estado(self):
        respuesta = self.client.get(
            reverse("operativos:operativo_lista"), {"estado": EstadoOperativo.CERRADO}
        )
        self.assertEqual(list(respuesta.context["operativos"]), [self.cerrado])

    def test_busca_por_nombre(self):
        respuesta = self.client.get(
            reverse("operativos:operativo_lista"), {"q": "Piloto"}
        )
        self.assertEqual(list(respuesta.context["operativos"]), [self.cerrado])

    def test_un_filtro_invalido_no_rompe_el_listado(self):
        """El formulario lo descarta en vez de fallar al consultar."""
        respuesta = self.client.get(
            reverse("operativos:operativo_lista"), {"estado": "INVENTADO"}
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_los_contadores_de_sectores_vienen_anotados(self):
        self.crear_sector()

        respuesta = self.client.get(reverse("operativos:operativo_lista"))
        operativo = next(
            o for o in respuesta.context["operativos"] if o.pk == self.operativo.pk
        )
        self.assertEqual(operativo.n_sectores, 1)

    def test_el_conteo_de_sectores_no_se_infla_con_las_zonas(self):
        """Sin distinct=True, un sector con 3 zonas contaría como 3 sectores."""
        sector = self.crear_sector()
        for numero in range(3):
            Zona.objects.create(sector=sector, nombre=f"Zona {numero}")

        respuesta = self.client.get(reverse("operativos:operativo_lista"))
        operativo = next(
            o for o in respuesta.context["operativos"] if o.pk == self.operativo.pk
        )

        self.assertEqual(operativo.n_sectores, 1)
        self.assertEqual(operativo.n_zonas, 3)

    def test_el_listado_de_comunas_filtra_por_region(self):
        Comuna.objects.create(region=self.metropolitana, nombre="Santiago")

        respuesta = self.client.get(
            reverse("operativos:comuna_lista"), {"region": self.biobio.pk}
        )
        self.assertEqual(list(respuesta.context["comunas"]), [self.concepcion])

    def test_el_listado_de_comunas_filtra_por_estado(self):
        self.concepcion.activa = False
        self.concepcion.save()
        Comuna.objects.create(region=self.metropolitana, nombre="Santiago")

        respuesta = self.client.get(
            reverse("operativos:comuna_lista"), {"estado": "inactivas"}
        )
        self.assertEqual(list(respuesta.context["comunas"]), [self.concepcion])


# ==========================================================================
# 13. INTEGRACIÓN CON LAS HISTORIAS ANTERIORES
# ==========================================================================


class IntegracionTest(BaseTerritorialTest):
    """Que la HU-05 no rompa lo que ya funcionaba, y se apoye en ello."""

    def test_la_bitacora_muestra_los_cambios_territoriales(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("operativos:comuna_crear"),
            {"region": self.metropolitana.pk, "nombre": "Puente Alto"},
        )

        respuesta = self.client.get(reverse("usuarios:auditoria"))
        self.assertContains(respuesta, "Puente Alto")
        self.assertContains(respuesta, "Creó el registro territorial")

    def test_la_bitacora_sigue_mostrando_las_acciones_sobre_usuarios(self):
        registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.EDITAR,
            usuario_afectado=self.censista,
            detalle="teléfono",
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("usuarios:auditoria"))
        self.assertContains(respuesta, "censista@opso.cl")

    def test_objetivo_resuelve_el_objeto_territorial(self):
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CREAR_TERRITORIO,
            objeto_territorial=self.concepcion,
        )
        self.assertEqual(registro.objetivo, "Comuna: Concepción (Región del Biobío)")

    def test_objetivo_sigue_resolviendo_usuarios_y_roles(self):
        por_usuario = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.EDITAR,
            usuario_afectado=self.censista,
        )
        por_rol = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CAMBIAR_PERMISOS,
            rol_afectado=self.rol_censista,
        )

        self.assertEqual(por_usuario.objetivo, "censista@opso.cl")
        self.assertEqual(por_rol.objetivo, "Rol: Censista")

    def test_registrar_accion_sin_objeto_afectado_falla(self):
        """Una fila que no dice sobre qué se actuó no sirve de nada."""
        with self.assertRaises(ValueError):
            registrar_accion(
                administrador=self.admin, accion=AccionAuditoria.CREAR_TERRITORIO
            )

    def test_un_objeto_fuera_del_catalogo_falla_en_vez_de_dejar_el_tipo_vacio(self):
        """Con el tipo vacío la fila quedaría fuera de cualquier filtro por tipo."""
        with self.assertRaises(ValueError):
            registrar_accion(
                administrador=self.admin,
                accion=AccionAuditoria.CREAR_TERRITORIO,
                objeto_territorial=self.rol_censista,  # un Rol no es territorial
            )

    def test_los_registros_no_territoriales_siguen_siendo_legibles(self):
        """La migración 0006 no tocó datos: objeto_tipo vacío es la verdad."""
        registro = registrar_accion(
            administrador=self.admin,
            accion=AccionAuditoria.CREAR,
            usuario_afectado=self.censista,
        )

        self.assertEqual(registro.objeto_tipo, "")
        self.assertIsNone(registro.objeto_id)
        self.assertFalse(registro.es_territorial)

    def test_el_panel_del_administrador_enlaza_a_los_operativos(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("dashboards:administrador"))

        self.assertContains(respuesta, reverse("operativos:operativo_lista"))

    def test_el_menu_muestra_operativos_a_quien_tiene_el_permiso(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("dashboards:supervisor"))

        self.assertContains(respuesta, reverse("operativos:operativo_lista"))

    def test_el_menu_oculta_operativos_a_quien_no_lo_tiene(self):
        self.client.force_login(self.censista)
        respuesta = self.client.get(reverse("dashboards:censista"))

        self.assertNotContains(respuesta, reverse("operativos:operativo_lista"))

    def test_la_administracion_de_usuarios_sigue_funcionando(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)

    def test_la_matriz_de_permisos_sigue_funcionando(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("usuarios:permisos")).status_code, 200)


# ==========================================================================
# 14. EL FILTRO DE PLANTILLA
# ==========================================================================


class FiltroPermisosTest(BaseTerritorialTest):
    """El filtro que permite consultar permisos desde una plantilla."""

    def test_devuelve_verdadero_si_lo_tiene(self):
        self.assertTrue(tiene_permiso(self.supervisor, "operativos.ver"))

    def test_devuelve_falso_si_no_lo_tiene(self):
        self.assertFalse(tiene_permiso(self.supervisor, "operativos.gestionar"))

    def test_el_administrador_lo_tiene_todo(self):
        self.assertTrue(tiene_permiso(self.admin, "operativos.gestionar"))

    def test_un_visitante_anonimo_no_rompe_la_plantilla(self):
        self.assertFalse(tiene_permiso(AnonymousUser(), "operativos.ver"))

    def test_alguno_de_varios_basta_con_uno(self):
        self.assertTrue(
            tiene_algun_permiso(
                self.supervisor, "operativos.gestionar,operativos.ver"
            )
        )

    def test_alguno_de_varios_es_falso_si_no_tiene_ninguno(self):
        self.assertFalse(
            tiene_algun_permiso(self.censista, "operativos.gestionar,operativos.ver")
        )

    def test_no_reimplementa_las_reglas_sino_que_delega(self):
        """Desactivar el rol corta los permisos, y el filtro lo refleja."""
        self.rol_supervisor.activo = False
        self.rol_supervisor.save()
        self.supervisor.refresh_from_db()

        self.assertFalse(tiene_permiso(self.supervisor, "operativos.ver"))
