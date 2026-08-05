"""Comando de gestión: siembra un operativo completo con encuestas de ejemplo.

POR QUÉ EXISTE ESTE COMANDO

La HU-07 es una historia de CONSULTA: muestra encuestas y no las crea. La pantalla
de registro llega con las historias siguientes del sprint. Sin datos, la
demostración de esta historia sería una pantalla vacía explicando que todavía no
hay nada, que es justo lo único que no hace falta demostrar.

Es el mismo papel que cumple `crear_usuarios_demo` para la HU-01, y se escribe con
el mismo criterio: un management command y no un script suelto, porque recibe la
configuración y la conexión a la base de datos ya inicializadas.

QUÉ CREA

Un operativo en curso, una comuna, un sector con tres zonas, la asignación del
sector al censista de demostración (reutilizando la HU-06) y unas treinta
encuestas repartidas en los OCHO estados. Los ocho importan: una demostración
con todo pendiente no muestra que la pantalla ordena por urgencia, ni que avisa de
las fichas devueltas, ni que la barra de avance se mueve.

Uso:
    python manage.py crear_encuestas_demo
    python manage.py crear_encuestas_demo --censista otra@opso.cl
    python manage.py crear_encuestas_demo --limpiar

Se puede volver a ejecutar sin romper nada: detecta lo que ya existe, igual que
`preparar_base_datos.py`.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from fichas.models import (
    ESTADOS_RESUELTOS,
    ESTADOS_SIN_LEVANTAR,
    Encuesta,
    EstadoEncuesta,
    GrupoFamiliar,
    Integrante,
    NivelEducacional,
    Parentesco,
    PuebloOriginario,
    Sexo,
    SituacionOcupacional,
    Vivienda,
)
from operativos.models import (
    AsignacionSector,
    Comuna,
    EstadoOperativo,
    Operativo,
    Region,
    Sector,
    Zona,
)

Usuario = get_user_model()

CORREO_CENSISTA = "censista@opso.cl"
NOMBRE_OPERATIVO = "Censo Social 2026 (demostración)"

# Las zonas del sector de demostración: nombre, descripción y viviendas estimadas.
ZONAS = [
    ("Zona 1", "Manzanas 1 a 8, entre Av. Central y el canal", 12),
    ("Zona 2", "Manzanas 9 a 14, subiendo por el cerro", 10),
    ("Zona 3", "Pasajes interiores del sector sur", 8),
]

# El padrón: (zona, dirección, referencia, tipo, tenencia, estado, hogares).
#
# El reparto de estados no es aleatorio, está pensado para que la pantalla se vea
# como en un operativo real a media marcha: la mayoría pendiente, algunas a medias,
# unas pocas devueltas y un par que no se pudieron levantar.
#
# «hogares» es cuántas familias viven en esa vivienda. Casi todas tienen una; la de
# «Pasaje Los Robles 47» tiene DOS, a propósito, porque es el caso que la HU-08
# vino a modelar bien y conviene poder mostrarlo en la defensa.
#
# El tipo y la tenencia se dejan vacíos ("") en las viviendas PENDIENTES: todavía no
# se ha llegado a la puerta, así que no hay nada que describir. Es el mismo criterio
# con el que la migración 0002 dejó sin describir el padrón heredado de la HU-07.
PADRON = [
    # zona, dirección, referencia, tipo, tenencia, estado, hogares
    (0, "Av. Central 1204", "Casa esquina, reja verde", "CASA", "PROPIA_PAGADA", EstadoEncuesta.VALIDADA, 1),
    (0, "Av. Central 1218", "", "CASA", "ARRENDADA", EstadoEncuesta.VALIDADA, 1),
    (0, "Av. Central 1232", "Portón de madera", "CASA", "PROPIA_PAGANDOSE", EstadoEncuesta.COMPLETADA, 1),
    (0, "Av. Central 1246", "", "DEPARTAMENTO", "ARRENDADA", EstadoEncuesta.COMPLETADA, 1),
    (0, "Pasaje Los Robles 15", "Frente al almacén", "CASA", "CEDIDA", EstadoEncuesta.OBSERVADA, 1),
    (0, "Pasaje Los Robles 23", "", "MEDIAGUA", "IRREGULAR", EstadoEncuesta.BORRADOR, 1),
    (0, "Pasaje Los Robles 31", "Casa con antejardín grande", "", "", EstadoEncuesta.PENDIENTE, 1),
    (0, "Pasaje Los Robles 39", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    # DOS hogares en la misma vivienda: el caso que la HU-08 modela bien.
    (0, "Pasaje Los Robles 47", "Sitio con dos casas", "CASA", "PROPIA_PAGADA", EstadoEncuesta.BORRADOR, 2),
    (0, "Calle El Canelo 302", "Deshabitada según los vecinos", "CASA", "OTRA", EstadoEncuesta.NO_UBICADA, 1),
    (0, "Calle El Canelo 318", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (1, "Subida El Mirador 45", "Casa celeste al final de la escalera", "CASA", "PROPIA_PAGADA", EstadoEncuesta.COMPLETADA, 1),
    (1, "Subida El Mirador 61", "", "CASA", "ARRENDADA", EstadoEncuesta.BORRADOR, 1),
    (1, "Subida El Mirador 77", "Pasar después de las 19:00", "", "", EstadoEncuesta.PENDIENTE, 1),
    (1, "Subida El Mirador 93", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (1, "Camino Las Vertientes 8", "Portón negro sin número visible", "CASA", "PROPIA_PAGADA", EstadoEncuesta.RECHAZADA, 1),
    (1, "Camino Las Vertientes 22", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (1, "Camino Las Vertientes 36", "Perro suelto: avisar desde la reja", "", "", EstadoEncuesta.PENDIENTE, 1),
    (1, "Camino Las Vertientes 50", "", "RANCHO", "IRREGULAR", EstadoEncuesta.OBSERVADA, 1),
    (2, "Pasaje Interior A 3", "Entrada por el costado del block", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior A 7", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior A 11", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior B 2", "Casa con reja blanca", "PIEZA", "ARRENDADA", EstadoEncuesta.BORRADOR, 1),
    (2, "Pasaje Interior B 6", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior B 10", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior B 14", "Solo hay alguien los fines de semana", "", "", EstadoEncuesta.PENDIENTE, 1),
    (2, "Pasaje Interior C 1", "", "", "", EstadoEncuesta.PENDIENTE, 1),
    # Anulada por el supervisor (HU-14): la ficha existe pero se descartó. Se siembra
    # para que la bandeja de revisión muestre también ese desenlace.
    (2, "Pasaje Interior C 5", "Duplicada de la C 1", "CASA", "ARRENDADA", EstadoEncuesta.ANULADA, 1),
]

# Nombres de ejemplo para los hogares. Son inventados a propósito y no se parecen
# a los de las cuentas de demostración: son datos personales de familias, aunque
# sean falsos, y conviene que en pantalla se vea que lo son.
JEFES_DE_HOGAR = [
    "María Fernanda Aguilera",
    "José Manuel Riquelme",
    "Carmen Gloria Sandoval",
    "Héctor Andrés Cabrera",
    "Rosa Elena Millán",
    "Patricio Alejandro Yáñez",
    "Sandra Beatriz Contreras",
    "Luis Alberto Quintana",
]

# Composición típica de un hogar, después del jefe: (parentesco, edad).
# El orden importa: los hogares pequeños se quedan con las primeras filas, que son
# las más frecuentes en un hogar real.
COMPOSICION = [
    (Parentesco.CONYUGE, 41),
    (Parentesco.HIJO, 16),
    (Parentesco.HIJO, 9),
    (Parentesco.HIJO, 3),
    (Parentesco.PADRE_MADRE, 72),
    (Parentesco.NIETO, 1),
    (Parentesco.OTRO_PARIENTE, 34),
]

# Nombres de las demás personas del hogar. Inventados, igual que los jefes.
OTRAS_PERSONAS = [
    ("Camila Andrea", "Riquelme Soto"),
    ("Matías Ignacio", "Aguilera Pino"),
    ("Josefa Antonia", "Cabrera Millán"),
    ("Benjamín Alonso", "Sandoval Vera"),
    ("Emilia Paz", "Yáñez Contreras"),
    ("Tomás Esteban", "Quintana Bravo"),
    ("Florencia Belén", "Muñoz Salazar"),
    ("Vicente Ignacio", "Fuentes Araya"),
]

NIVELES = [
    NivelEducacional.BASICA_COMPLETA,
    NivelEducacional.MEDIA_COMPLETA,
    NivelEducacional.MEDIA_INCOMPLETA,
    NivelEducacional.TECNICA,
    NivelEducacional.BASICA_INCOMPLETA,
    NivelEducacional.UNIVERSITARIA,
]

OCUPACIONES = [
    SituacionOcupacional.TRABAJA,
    SituacionOcupacional.LABORES_HOGAR,
    SituacionOcupacional.BUSCA_TRABAJO,
    SituacionOcupacional.ESTUDIA,
    SituacionOcupacional.JUBILADO,
    SituacionOcupacional.TRABAJA,
]

# INDICACIONES son lo que el encuestador RECIBE antes de salir (el campo
# `observaciones`), y NOTAS_DE_AVANCE lo que se deja escrito a sí mismo
# (`nota_avance`). La HU-10 partió ese campo en dos justamente para que no se pisen:
# dos autores, dos propósitos.
#
# Hasta la HU-15, la devolución del supervisor también se escribía aquí, porque no
# había otro sitio. Ahora tiene el suyo —`comentario_revision`, más abajo— y este
# quedó solo con lo que de verdad es una indicación previa.
INDICACIONES = {
    EstadoEncuesta.BORRADOR: (
        "Pasar después de las 19:00, en esta casa trabajan todo el día."
    ),
}

# Lo que el supervisor escribe al devolver (HU-15). Con el formato que produce
# DevolverEncuestaForm —los aspectos primero, la explicación después— porque la
# demostración tiene que enseñar lo que el encuestador va a leer de verdad, y no un
# texto suelto que la aplicación nunca generaría.
OBSERVACIONES_DE_DEVOLUCION = (
    "Corregir: Integrantes del hogar, Datos del hogar.\n\n"
    "- Faltan los datos de escolaridad de dos integrantes.\n"
    "- Falta la fecha de nacimiento del jefe de hogar.\n"
    "El ingreso declarado no cuadra con lo que anotaste en la nota de avance: "
    "confírmalo con la familia."
)

NOTAS_DE_AVANCE = [
    "Falta el módulo de ingresos. La señora vuelve del trabajo a las 19:00.",
    "Quedaron por registrar los dos hijos mayores; no estaban en la casa.",
    "La persona tenía que salir. Alcanzamos a llegar hasta los datos del hogar.",
    "Falta confirmar el RUT del jefe de hogar: dijo que buscaría el carnet.",
    "Nos interrumpió la lluvia. Falta la mitad de las personas del hogar.",
]

# El motivo del cierre (HU-10). Es OBLIGATORIO: lo exige la restricción
# `encuesta_cierre_con_motivo`, y tiene un lector concreto —el supervisor que decide
# si manda a otra persona a esa dirección—, así que son frases y no etiquetas.
MOTIVOS_DE_CIERRE = {
    EstadoEncuesta.NO_UBICADA: (
        "La vivienda está deshabitada desde hace meses según dos vecinos. La reja "
        "está con candado y no hay medidor."
    ),
    EstadoEncuesta.RECHAZADA: (
        "La familia no quiso participar. Se explicó el objetivo del operativo y se "
        "dejó el folleto informativo; pidieron no volver."
    ),
}


class Command(BaseCommand):
    help = "Crea un operativo de demostración con encuestas en todos los estados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--censista",
            default=CORREO_CENSISTA,
            help="Correo de la persona a la que se le asignan las encuestas.",
        )
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Borra las encuestas de demostración antes de volver a crearlas.",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        # Se respeta --verbosity 0 para que las pruebas que invocan el comando no
        # ensucien la salida del corredor con el resumen de la siembra.
        self.verbosidad = opciones["verbosity"]

        censista = self.buscar_censista(opciones["censista"])
        operativo = self.crear_operativo()
        sector = self.crear_territorio(operativo)
        zonas = self.crear_zonas(sector)
        self.asignar_sector(sector, censista)

        if opciones["limpiar"]:
            # Borrar las viviendas se lleva por delante sus encuestas (CASCADE) y
            # los grupos familiares de esas encuestas (CASCADE otra vez). Es la
            # cadena que describe el modelo, y aquí es exactamente lo que se
            # quiere: dejar la zona como estaba antes de sembrar.
            borradas, _ = Vivienda.objects.filter(zona__in=zonas).delete()
            self.aviso(f"  Se borraron {borradas} registros anteriores.")

        creadas = self.crear_encuestas(zonas, censista)

        self.aviso("")
        self.aviso(
            f"  {creadas} encuestas creadas para {censista.email} "
            f"en «{operativo.nombre}».",
            self.style.SUCCESS,
        )
        self.aviso(
            "  Son datos de DEMOSTRACIÓN: no usar en un entorno real.",
            self.style.WARNING,
        )
        self.aviso("  Entra con esa cuenta y abre /encuestas/.")

    # ------------------------------------------------------------------

    def aviso(self, texto, estilo=None):
        """Escribe en la consola salvo que se haya pedido --verbosity 0."""
        if not self.verbosidad:
            return

        self.stdout.write(estilo(texto) if estilo else texto)

    def buscar_censista(self, correo):
        usuario = Usuario.objects.filter(email=correo).first()

        if usuario is None:
            raise CommandError(
                f"No existe la cuenta {correo}. Créala primero con:\n"
                "    python manage.py crear_usuarios_demo"
            )

        return usuario

    def crear_operativo(self):
        hoy = timezone.localdate()

        operativo, creado = Operativo.objects.get_or_create(
            nombre=NOMBRE_OPERATIVO,
            defaults={
                "descripcion": (
                    "Operativo de demostración creado por "
                    "`manage.py crear_encuestas_demo` para mostrar la pantalla de "
                    "encuestas del encuestador."
                ),
                "fecha_inicio": hoy - timedelta(days=10),
                "fecha_termino": hoy + timedelta(days=20),
                "estado": EstadoOperativo.EN_CURSO,
            },
        )

        self.aviso(
            f"  Operativo {'creado' if creado else 'reutilizado'}: {operativo.nombre}"
        )
        return operativo

    def crear_territorio(self, operativo):
        # La región viene sembrada por la migración 0002 de la HU-05, así que no se
        # crea: se busca. Si no estuviera, la base no está migrada.
        region = Region.objects.order_by("orden").first()

        if region is None:
            raise CommandError(
                "No hay regiones en la base de datos. Ejecuta primero: "
                "python manage.py migrate"
            )

        comuna, _ = Comuna.objects.get_or_create(
            region=region,
            nombre="Concepción",
            defaults={"activa": True},
        )
        sector, _ = Sector.objects.get_or_create(
            operativo=operativo,
            comuna=comuna,
            nombre="Los Boldos",
            defaults={
                "descripcion": (
                    "Entre Av. Central y el canal, subiendo hasta el mirador."
                )
            },
        )
        return sector

    def crear_zonas(self, sector):
        zonas = []

        for nombre, descripcion, viviendas in ZONAS:
            zona, _ = Zona.objects.get_or_create(
                sector=sector,
                nombre=nombre,
                defaults={
                    "descripcion": descripcion,
                    "viviendas_estimadas": viviendas,
                },
            )
            zonas.append(zona)

        return zonas

    def asignar_sector(self, sector, censista):
        """Reutiliza la HU-06: el censista tiene el sector a cargo.

        Sin esto la demostración quedaría incoherente: encuestas en un sector que
        la pantalla «Mis sectores» diría que no es suyo.
        """
        _, creada = AsignacionSector.objects.get_or_create(
            sector=sector,
            censista=censista,
            activa=True,
            defaults={
                "observaciones": (
                    "Empezar por la Zona 1, que es la más cercana al punto de "
                    "encuentro."
                )
            },
        )

        if creada:
            self.aviso(f"  Sector «{sector.nombre}» asignado a {censista.email}")

    def crear_encuestas(self, zonas, censista):
        """Crea el padrón, saltando lo que ya exista.

        Las fechas se calculan hacia atrás desde hoy para que el listado se vea
        realista: las validadas son las más antiguas y las pendientes no tienen
        fecha de inicio, que es lo que exige la restricción
        `encuesta_inicio_coherente` de la tabla.
        """
        ahora = timezone.now()
        creadas = 0
        #: Cuántas fichas devueltas se han sembrado ya (HU-15). Ver `crear_encuesta`.
        self.devueltas_sembradas = 0

        for indice, fila in enumerate(PADRON):
            n_zona, direccion, referencia, tipo, tenencia, estado, hogares = fila
            zona = zonas[n_zona]

            vivienda, nueva = Vivienda.objects.get_or_create(
                zona=zona,
                direccion=direccion,
                defaults={
                    "referencia": referencia,
                    "registrada_por": censista,
                    **self.caracteristicas(tipo, tenencia, indice),
                },
            )

            if not nueva:
                continue

            # Tantas encuestas como hogares: la de «Pasaje Los Robles 47» crea DOS
            # sobre la MISMA vivienda, que es el caso que la HU-08 vino a resolver.
            for numero in range(hogares):
                self.crear_encuesta(
                    vivienda, censista, estado, indice, numero, ahora
                )
                creadas += 1

        return creadas

    def caracteristicas(self, tipo, tenencia, indice):
        """Las seis características, o ninguna si la vivienda sigue pendiente.

        Una vivienda que nadie ha visitado no tiene por qué estar descrita, y
        rellenarla sería inventar datos del censo. El comando reproduce así el
        estado real de un operativo a media marcha, que es lo que se quiere
        mostrar: unas descritas y otras no.
        """
        if not tipo:
            return {}

        # Se rotan los valores con el índice para que la demostración no muestre
        # veinte viviendas idénticas.
        muros = ["ALBANILERIA", "TABIQUE_FORRADO", "HORMIGON", "ADOBE", "PRECARIO"]
        aguas = ["RED_PUBLICA", "RED_PUBLICA", "POZO", "CAMION"]
        sanitarios = ["ALCANTARILLADO", "ALCANTARILLADO", "FOSA", "CAJON"]

        datos = {
            "tipo": tipo,
            "tenencia": tenencia,
            "materialidad_muros": muros[indice % len(muros)],
            "origen_agua": aguas[indice % len(aguas)],
            "sistema_sanitario": sanitarios[indice % len(sanitarios)],
            "tiene_electricidad": indice % 7 != 0,
        }
        datos.update(self.ubicacion(indice))
        return datos

    def ubicacion(self, indice):
        """Un punto GPS plausible para la vivienda (HU-11).

        Los puntos se reparten alrededor del centro de Concepción, separados unas
        decenas de metros entre sí, que es como se ven las casas de una zona real.
        Se calculan con el índice y no al azar para que el comando sea
        reproducible: dos ejecuciones dan la misma demostración.

        UNA DE CADA CINCO VIVIENDAS QUEDA SIN UBICACIÓN, a propósito. Es lo que pasa
        en terreno cuando no hay señal o no se dio el permiso, y una demostración
        donde todas tienen punto no muestra el aviso de «sin ubicación capturada»
        que la pantalla de terminar exhibe.

        Y una de cada siete tiene MALA PRECISIÓN, por el mismo motivo: el aviso de
        «poco precisa» solo se ve si hay alguna así.
        """
        if indice % 5 == 0:
            return {}

        # ~0,0001 grados son unos 11 m: la rejilla deja las casas a media cuadra
        # unas de otras.
        latitud = Decimal("-36.826700") + Decimal(indice % 7) * Decimal("0.00012")
        longitud = Decimal("-73.049700") + Decimal(indice % 5) * Decimal("0.00014")

        return {
            "latitud": latitud,
            "longitud": longitud,
            "precision_metros": 120 if indice % 7 == 3 else 6 + indice % 9,
            "ubicacion_capturada_en": timezone.now(),
            "ubicacion_manual": indice % 11 == 0,
        }

    def crear_encuesta(self, vivienda, censista, estado, indice, numero, ahora):
        """Una encuesta y, si ya se visitó, su grupo familiar."""
        encuesta = Encuesta.objects.create(
            vivienda=vivienda,
            censista=censista,
            observaciones=INDICACIONES.get(estado, ""),
        )

        # cambiar_estado() ajusta iniciada_en y cerrada_en según el estado, que es
        # justo lo que impide crear filas que la base de datos rechazaría.
        encuesta.cambiar_estado(estado, guardar=False)

        # Se envejecen las fechas para que el historial no sea todo del mismo
        # segundo: un listado donde todo ocurrió a la vez no se ve como uno real.
        dias = len(PADRON) - indice
        if encuesta.iniciada_en:
            encuesta.iniciada_en = ahora - timedelta(days=dias, hours=3)
        if encuesta.cerrada_en:
            encuesta.cerrada_en = ahora - timedelta(days=dias, hours=1)

        # --------------------------------------------------------------
        # HU-10: el borrador y el cierre.
        # --------------------------------------------------------------
        if estado == EstadoEncuesta.BORRADOR:
            # Los borradores llevan nota y visita anotada, que es lo que la
            # historia existe para conservar. Uno de cada tres tiene la visita YA
            # VENCIDA, a propósito: es el caso que la pantalla avisa, y una
            # demostración donde todas las fechas están en el futuro no lo muestra.
            encuesta.nota_avance = NOTAS_DE_AVANCE[indice % len(NOTAS_DE_AVANCE)]
            desplazamiento = -2 if indice % 3 == 0 else 3 + indice % 5
            encuesta.proxima_visita = timezone.localdate() + timedelta(
                days=desplazamiento
            )

        if estado in ESTADOS_RESUELTOS:
            # La resolución del supervisor (HU-14): quién la revisó y cuándo. El
            # comentario es OBLIGATORIO al anular y al devolver, y lo exige una
            # restricción de la tabla (`encuesta_resolucion_con_motivo`), así que el
            # comando lo escribe siempre que corresponde.
            encuesta.revisada_por = Usuario.objects.filter(
                rol__codigo="SUPERVISOR"
            ).first()
            encuesta.revisada_en = ahora - timedelta(days=1)

            if estado == EstadoEncuesta.ANULADA:
                encuesta.comentario_revision = (
                    "Duplicada: la misma vivienda está levantada en la ficha de "
                    "«Pasaje Interior C 1», con el mismo jefe de hogar."
                )

            if estado == EstadoEncuesta.OBSERVADA:
                encuesta.comentario_revision = OBSERVACIONES_DE_DEVOLUCION
                # La primera devuelta lleva una sola devolución y la segunda llega al
                # umbral de reincidencia, para que el aviso se vea en la demostración
                # sin tener que devolver la misma ficha tres veces a mano.
                #
                # Se cuenta con un contador propio y no con la paridad del índice del
                # padrón: si mañana se agrega una fila antes, la paridad cambia y la
                # demostración dejaría de mostrar el aviso sin que nadie se enterara.
                self.devueltas_sembradas += 1
                encuesta.veces_devuelta = (
                    1
                    if self.devueltas_sembradas == 1
                    else Encuesta.DEVOLUCIONES_PARA_ALERTAR
                )

        if estado in ESTADOS_SIN_LEVANTAR:
            # El motivo es obligatorio: lo exige `encuesta_cierre_con_motivo`. Antes
            # de la HU-10 este texto iba en `observaciones`, y la migración 0004 lo
            # trasladó para las filas que ya existían.
            encuesta.motivo_cierre = MOTIVOS_DE_CIERRE[estado]

        encuesta.save()

        # El hogar solo existe si la encuesta se empezó: una PENDIENTE es una
        # puerta que todavía nadie tocó, y darle jefe de hogar sería inventarlo.
        if estado != EstadoEncuesta.PENDIENTE:
            hogar = GrupoFamiliar.objects.create(
                encuesta=encuesta,
                jefe_hogar_nombre=JEFES_DE_HOGAR[
                    (indice + numero) % len(JEFES_DE_HOGAR)
                ],
                telefono_contacto="+56 9 5555 000{}".format(indice % 10),
                integrantes_declarados=1 + (indice + numero) % 6,
                ingreso_mensual=250_000 + (indice % 8) * 95_000,
            )
            self.crear_integrantes(hogar, estado, indice)

    def crear_integrantes(self, hogar, estado, indice):
        """Las personas del hogar (HU-09).

        DELIBERADAMENTE, LOS BORRADORES QUEDAN A MEDIAS. Un hogar en estado
        BORRADOR recibe menos personas de las que declaró, porque eso es lo que es
        un borrador en terreno: una encuesta que se interrumpió. Sembrarlos
        completos escondería justo lo que la pantalla de integrantes existe para
        mostrar —la barra de avance y el aviso de «faltan tres personas»—, y la
        demostración no enseñaría nada.
        """
        declarados = hogar.integrantes_declarados

        # Los borradores quedan a medias; el resto, completos.
        cuantos = max(1, declarados - 2) if estado == EstadoEncuesta.BORRADOR else declarados

        # El jefe de hogar se registra con el mismo nombre con que se identificó el
        # hogar, que es exactamente lo que hace el prellenado del formulario.
        partes = hogar.jefe_hogar_nombre.split()
        mitad = max(1, len(partes) // 2)

        Integrante.objects.create(
            grupo_familiar=hogar,
            parentesco=Parentesco.JEFE_HOGAR,
            nombres=" ".join(partes[:mitad]),
            apellidos=" ".join(partes[mitad:]),
            sexo=Sexo.FEMENINO if indice % 2 == 0 else Sexo.MASCULINO,
            fecha_nacimiento=self.fecha_de_nacimiento(28 + indice % 30),
            nivel_educacional=NIVELES[indice % len(NIVELES)],
            situacion_ocupacional=OCUPACIONES[indice % len(OCUPACIONES)],
            pueblo_originario=(
                PuebloOriginario.MAPUCHE if indice % 5 == 0 else PuebloOriginario.NINGUNO
            ),
        )

        for numero in range(1, cuantos):
            parentesco, edad = COMPOSICION[(numero - 1) % len(COMPOSICION)]
            nombre, apellido = OTRAS_PERSONAS[(indice + numero) % len(OTRAS_PERSONAS)]

            Integrante.objects.create(
                grupo_familiar=hogar,
                parentesco=parentesco,
                nombres=nombre,
                apellidos=apellido,
                sexo=Sexo.MASCULINO if numero % 2 == 0 else Sexo.FEMENINO,
                fecha_nacimiento=self.fecha_de_nacimiento(edad),
                # Los campos que dependen de la edad se dejan en blanco cuando no
                # corresponden, igual que hace el formulario.
                nivel_educacional=(
                    NIVELES[(indice + numero) % len(NIVELES)]
                    if edad >= Integrante.EDAD_ESCOLARIDAD
                    else ""
                ),
                situacion_ocupacional=(
                    OCUPACIONES[(indice + numero) % len(OCUPACIONES)]
                    if edad >= Integrante.EDAD_OCUPACION
                    else ""
                ),
                tiene_discapacidad=(indice + numero) % 11 == 0,
            )

    @staticmethod
    def fecha_de_nacimiento(edad):
        """Una fecha de nacimiento que da esa edad hoy.

        Se resta un día de más para no caer justo en el cumpleaños, donde el
        cálculo de la edad tiene su caso borde y una prueba podría volverse
        inestable según el día en que se ejecute.
        """
        return timezone.localdate() - timedelta(days=edad * 365 + 100)
