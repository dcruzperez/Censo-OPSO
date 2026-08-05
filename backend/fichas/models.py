"""Modelos de la app "fichas" (HU-07, HU-08 y HU-09).

Cuatro tablas, y cada una responde una pregunta distinta:

    1. fichas_vivienda       -> ¿QUÉ es esta casa?      (el objeto físico)
    2. fichas_encuesta       -> ¿QUIÉN la levanta y en qué va?  (el trabajo)
    3. fichas_grupo_familiar -> ¿QUIÉN vive aquí?       (el hogar)
    4. fichas_integrante     -> ¿QUIÉNES son, una por una?  (las personas)

DÓNDE ENCAJAN EN LO QUE YA EXISTE

    Region ──< Comuna                       GEOGRAFÍA        (HU-05)
    Operativo ──< Sector ──< Zona           ORGANIZACIÓN     (HU-05)
                    │
                    ├──< AsignacionSector   REPARTO          (HU-06)
                    │
                    └──< Vivienda ──< Encuesta ──1:1── GrupoFamiliar ──< Integrante
                            HU-08       HU-07              HU-08           HU-09

La HU-05 dibujó el mapa, la HU-06 lo repartió entre personas, la HU-07 bajó hasta
la puerta concreta, la HU-08 registró lo que hay detrás de esa puerta y la HU-09
llega al final del recorrido: las personas, una por una.

--------------------------------------------------------------------------
LAS TRES TABLAS Y POR QUÉ NO SON UNA
--------------------------------------------------------------------------
Se podría guardar todo en `Encuesta`: la dirección, la materialidad, el jefe de
hogar y el estado. Sería una tabla con treinta columnas que mezcla tres cosas que
cambian por motivos distintos y en momentos distintos, y esa es exactamente la
definición de una tabla mal cortada. La separación se sostiene sola:

  VIVIENDA es el objeto FÍSICO y es estable. Una casa de albañilería con agua de
  red sigue siéndolo el año que viene y en el operativo siguiente. Sus datos no
  dependen de quién la encueste ni de cuándo.

  ENCUESTA es el TRABAJO y es efímero. Tiene dueño, estado y fechas; nace cuando
  alguien tiene que ir y muere cuando el supervisor la valida. En el operativo
  siguiente habrá otra encuesta sobre la misma vivienda.

  GRUPO FAMILIAR es el DATO LEVANTADO. Es lo que el censo quiere saber, y cambia
  cada vez que se levanta: la familia que vivía ahí en 2026 puede no ser la de
  2027.

--------------------------------------------------------------------------
REVISIÓN EXPLÍCITA DE LA DECISIÓN 4 DE LA HU-07
--------------------------------------------------------------------------
La HU-07 dejó escrito que NO habría unicidad por dirección, porque una misma
dirección aloja más de un hogar con toda normalidad, y resolvió el riesgo de
duplicado avisando en la pantalla. El argumento sigue siendo correcto, pero el
modelo que lo acompañaba era el provisional: allí «dos hogares en la misma casa»
eran dos filas de `Encuesta` con la dirección repetida, y con la HU-08 esa
repetición habría duplicado también el tipo de vivienda, la materialidad y los
servicios básicos —con la posibilidad de que las dos copias se contradijeran—.

Con `Vivienda` como tabla propia, el caso se modela como lo que es: UNA vivienda
y DOS encuestas colgando de ella. La dirección deja de repetirse porque deja de
estar en la tabla que se repite. La HU-07 no se equivocó: modeló lo que su
alcance necesitaba y dejó anotado el punto débil; la HU-08 lo resuelve en cuanto
aparece la información que lo justifica.

Es el mismo movimiento que hizo RegistroAuditoria entre la HU-04 y la HU-05: una
decisión se revisa cuando su premisa cambia, y la revisión se escribe.

--------------------------------------------------------------------------
LO QUE ESTAS TRES HISTORIAS TODAVÍA NO HACEN
--------------------------------------------------------------------------
El guardado parcial explícito de una encuesta incompleta y su cierre (HU-10), la
ubicación GPS de la vivienda (HU-11) y las fotografías (HU-12). Las tres cuelgan
de estas tablas sin cambiarlas: el GPS y las fotos de Vivienda, y el borrador es
un estado de Encuesta que ya existe.

La HU-09 confirmó que el corte de la HU-08 era el correcto: los integrantes
entraron colgando de GrupoFamiliar sin tocar una sola columna de las otras tres
tablas.
"""

from decimal import Decimal
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from usuarios.validators import limpiar_rut, validar_rut


# ==========================================================================
# 1. LA VIVIENDA: EL OBJETO FÍSICO (HU-08)
# ==========================================================================


# --------------------------------------------------------------------------
# LOS LÍMITES DEL TERRITORIO NACIONAL (HU-11)
#
# Se escriben UNA vez, aquí, y los usan la restricción de la tabla y la validación
# del formulario. Dos copias con números distintos darían dos veredictos para el
# mismo punto, y la que fallara sería la que nadie mira.
#
# Van a nivel de módulo y no dentro de la clase por una limitación del lenguaje: el
# cuerpo de una clase anidada —`class Meta`— no ve los nombres de la clase que la
# contiene, así que una constante declarada junto a los campos no se podría usar en
# `constraints`.
#
# El rango incluye el territorio INSULAR. Acotarlo a Chile continental (-76 a -66 de
# longitud) dejaría fuera Rapa Nui, que está en -109,4 y es territorio nacional.
# --------------------------------------------------------------------------
LATITUD_MINIMA = Decimal("-56.6")
LATITUD_MAXIMA = Decimal("-17.4")
LONGITUD_MINIMA = Decimal("-109.6")
LONGITUD_MAXIMA = Decimal("-66.3")


class TipoVivienda(models.TextChoices):
    """Qué clase de vivienda es.

    Las opciones no se inventaron: siguen la clasificación con que el Instituto
    Nacional de Estadísticas describe las viviendas en el censo chileno. Usar el
    vocabulario oficial tiene una ventaja concreta y no es de estilo: permite
    comparar los resultados de OPSO con las cifras nacionales. Una categoría
    propia («casa chica», «casa grande») produciría datos que no se pueden cruzar
    con nada.
    """

    CASA = "CASA", "Casa"
    DEPARTAMENTO = "DEPARTAMENTO", "Departamento en edificio"
    PIEZA = "PIEZA", "Pieza en casa antigua o conventillo"
    MEDIAGUA = "MEDIAGUA", "Mediagua o mejora"
    RANCHO = "RANCHO", "Rancho o choza"
    PRECARIA = "PRECARIA", "Vivienda precaria de materiales reutilizados"
    OTRA = "OTRA", "Otra"


class TenenciaVivienda(models.TextChoices):
    """A qué título la ocupa la familia.

    Es el dato que más pesa en la focalización social de todo el formulario: una
    familia arrendando y una propietaria con la casa pagada pueden tener el mismo
    ingreso y una vulnerabilidad muy distinta.
    """

    PROPIA_PAGADA = "PROPIA_PAGADA", "Propia, totalmente pagada"
    PROPIA_PAGANDOSE = "PROPIA_PAGANDOSE", "Propia, pagándose"
    ARRENDADA = "ARRENDADA", "Arrendada"
    CEDIDA = "CEDIDA", "Cedida por trabajo o por un familiar"
    IRREGULAR = "IRREGULAR", "Ocupación irregular"
    OTRA = "OTRA", "Otra"


class MaterialidadMuros(models.TextChoices):
    """De qué están hechos los muros exteriores.

    Se pregunta solo por los muros y no también por el techo y el piso, que es lo
    que hace el censo completo. La razón es que el formulario lo llena una persona
    de pie en la puerta: cada pregunta cuesta tiempo y cansa a quien responde, y
    los muros son el indicador que mejor resume la calidad constructiva. Si un
    operativo necesitara el detalle, se agregan dos columnas; empezar por las tres
    habría sido pedir datos «por si acaso».
    """

    HORMIGON = "HORMIGON", "Hormigón armado"
    ALBANILERIA = "ALBANILERIA", "Albañilería (ladrillo, bloque, piedra)"
    TABIQUE_FORRADO = "TABIQUE_FORRADO", "Tabique forrado por ambas caras"
    TABIQUE_SIN_FORRO = "TABIQUE_SIN_FORRO", "Tabique sin forro interior"
    ADOBE = "ADOBE", "Adobe, barro o quincha"
    PRECARIO = "PRECARIO", "Materiales precarios o de desecho"


class OrigenAgua(models.TextChoices):
    """De dónde llega el agua."""

    RED_PUBLICA = "RED_PUBLICA", "Red pública"
    POZO = "POZO", "Pozo o noria"
    CAMION = "CAMION", "Camión aljibe"
    SUPERFICIAL = "SUPERFICIAL", "Río, vertiente, estero o lago"
    OTRO = "OTRO", "Otro"


class SistemaSanitario(models.TextChoices):
    """Cómo se eliminan las aguas servidas."""

    ALCANTARILLADO = "ALCANTARILLADO", "Conectado al alcantarillado"
    FOSA = "FOSA", "Fosa séptica"
    LETRINA = "LETRINA", "Letrina sanitaria conectada a pozo"
    CAJON = "CAJON", "Cajón sobre pozo negro"
    NO_TIENE = "NO_TIENE", "No dispone de servicio higiénico"


class Vivienda(models.Model):
    """Una vivienda concreta dentro de una zona: el objeto físico del censo.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 1 — la vivienda es una tabla, no columnas de la encuesta
    ----------------------------------------------------------------------
    Ver la explicación larga en la cabecera del módulo. En corto: la vivienda es
    estable y la encuesta es efímera, y una misma vivienda puede alojar más de un
    hogar. Guardar la materialidad en la encuesta obligaría a repetirla en cada
    hogar de la misma casa, con dos copias que pueden contradecirse.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 2 — sigue sin haber unicidad por dirección
    ----------------------------------------------------------------------
    Ahora que las viviendas son filas propias, sería tentador exigir que no se
    repita una dirección dentro de una zona. Sigue siendo incorrecto, pero por un
    motivo distinto del de la HU-07: el caso de los dos hogares ya está resuelto
    por el modelo, y lo que queda es el sitio con DOS VIVIENDAS en la misma
    dirección —la casa del fondo y la de adelante—, que en terreno es
    frecuentísimo y no tiene numeración propia.

    Lo que sí hace el sistema es AVISAR: al registrar una vivienda en una
    dirección donde ya hay otra, el formulario se detiene y pide confirmar que se
    trata de una vivienda distinta y no de un duplicado (ver ViviendaForm). La
    diferencia entre bloquear y avisar es la diferencia entre perder un dato real
    y perder cinco segundos.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 3 — obligatorias EN EL FORMULARIO, opcionales EN LA COLUMNA
    ----------------------------------------------------------------------
    Las seis características admiten vacío en la base de datos y sin embargo el
    formulario de registro las exige todas. La asimetría es deliberada y tiene un
    motivo concreto, no es una imprecisión.

    Un censo con la mitad de las viviendas «sin dato» no permite calcular nada, y
    la persona que está en la puerta puede responderlas todas mirando: por eso el
    formulario no deja guardar sin ellas.

    Pero la columna tiene que admitir el vacío porque YA EXISTEN FILAS SIN ESA
    INFORMACIÓN: la HU-07 creó encuestas —el padrón por visitar— cuando la
    vivienda todavía no se había descrito. La migración que introduce esta tabla
    tiene que convertir esas encuestas en viviendas, y la única alternativa a
    dejar el dato vacío sería INVENTARLO («pongamos casa, que es lo más común»).
    Eso es fabricar datos del censo, y un dato inventado es peor que un dato
    ausente porque nadie puede distinguirlo después.

    El sistema lo hace visible en vez de esconderlo: `datos_completos` responde si
    la vivienda está descrita, y la ficha muestra «sin describir» con el enlace
    para completarla.

    `observaciones` es opcional también en el formulario: es donde cabe lo que el
    formulario no previó, y obligarlo produciría texto de relleno.
    """

    zona = models.ForeignKey(
        "operativos.Zona",
        on_delete=models.PROTECT,
        related_name="viviendas",
        verbose_name="zona",
        help_text="Zona del sector en la que se ubica la vivienda.",
    )
    direccion = models.CharField(
        "dirección",
        max_length=200,
        help_text="Calle y número. Ej.: Pasaje Los Robles 1425.",
    )
    referencia = models.CharField(
        "referencia",
        max_length=200,
        blank=True,
        help_text=(
            "Cómo reconocerla desde la calle. Ej.: casa verde, portón negro, "
            "la del fondo del sitio."
        ),
    )
    # Las seis características. Todas admiten vacío en la columna y ninguna en el
    # formulario: ver la decisión de diseño 3.
    tipo = models.CharField(
        "tipo de vivienda",
        max_length=20,
        choices=TipoVivienda.choices,
        blank=True,
        help_text="Clasificación según el censo.",
    )
    tenencia = models.CharField(
        "tenencia",
        max_length=20,
        choices=TenenciaVivienda.choices,
        blank=True,
        help_text="A qué título ocupa la familia esta vivienda.",
    )
    materialidad_muros = models.CharField(
        "materialidad de los muros",
        max_length=20,
        choices=MaterialidadMuros.choices,
        blank=True,
        help_text="Material predominante de los muros exteriores.",
    )
    origen_agua = models.CharField(
        "origen del agua",
        max_length=20,
        choices=OrigenAgua.choices,
        blank=True,
        help_text="De dónde proviene el agua que usa la vivienda.",
    )
    sistema_sanitario = models.CharField(
        "sistema sanitario",
        max_length=20,
        choices=SistemaSanitario.choices,
        blank=True,
        help_text="Cómo se eliminan las aguas servidas.",
    )
    # Nulo y no False: «no sabemos» y «no tiene luz» son cosas distintas, y un
    # booleano de dos valores obligaría a elegir una de las dos al migrar las
    # viviendas que la HU-07 dejó sin describir.
    tiene_electricidad = models.BooleanField(
        "tiene electricidad",
        null=True,
        blank=True,
        help_text="Si cuenta con suministro eléctrico regular.",
    )
    observaciones = models.TextField(
        "observaciones",
        blank=True,
        help_text="Lo que el formulario no previó y conviene dejar anotado.",
    )
    # ------------------------------------------------------------------
    # LA UBICACIÓN GEOGRÁFICA (HU-11)
    #
    # Cuelga de la VIVIENDA y no de la encuesta, y es la consecuencia directa del
    # corte que hizo la HU-08: unas coordenadas describen un lugar físico, no un
    # trabajo. Dos hogares de la misma casa comparten el punto, y el operativo del
    # año que viene lo hereda sin volver a medirlo.
    #
    # Se guardan como DECIMAL y no como float. Un float binario no puede
    # representar exactamente 0,1, y aunque el error sea minúsculo, en coordenadas
    # se traduce en metros y en comparaciones que fallan por el último dígito.
    # DecimalField guarda el número que se escribió.
    #
    # Seis decimales es la precisión de ~11 cm en el ecuador, muy por debajo de lo
    # que da el GPS de un teléfono (5-20 m en el mejor caso). Guardar más dígitos
    # sería fingir una exactitud que el aparato no tiene.
    # ------------------------------------------------------------------
    latitud = models.DecimalField(
        "latitud",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Grados decimales. En Chile siempre es negativa.",
    )
    longitud = models.DecimalField(
        "longitud",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Grados decimales. En Chile siempre es negativa.",
    )
    precision_metros = models.PositiveIntegerField(
        "precisión",
        null=True,
        blank=True,
        help_text=(
            "Radio de error en metros que informó el aparato. Sin este dato, un "
            "punto tomado dentro de una casa parece tan bueno como uno tomado en la "
            "calle."
        ),
    )
    ubicacion_capturada_en = models.DateTimeField(
        "ubicación capturada en",
        null=True,
        blank=True,
        help_text="Cuándo se tomó el punto.",
    )
    ubicacion_manual = models.BooleanField(
        "ubicación escrita a mano",
        default=False,
        help_text=(
            "True si las coordenadas se escribieron en vez de capturarlas del "
            "aparato. Un punto escrito a mano no tiene la misma confianza."
        ),
    )
    registrada_por = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="viviendas_registradas",
        verbose_name="registrada por",
        help_text="Quién la dio de alta en terreno.",
    )
    creada_en = models.DateTimeField("creada en", auto_now_add=True)
    actualizada_en = models.DateTimeField("actualizada en", auto_now=True)

    class Meta:
        db_table = "fichas_vivienda"
        verbose_name = "vivienda"
        verbose_name_plural = "viviendas"
        # Orden del recorrido: es como se camina una calle.
        ordering = ["zona__sector__nombre", "zona__nombre", "direccion"]
        constraints = [
            # El vacío se admite (vivienda sin describir todavía), pero un valor
            # inventado no: o es una de las opciones del catálogo, o no es nada.
            models.CheckConstraint(
                condition=models.Q(tipo__in=TipoVivienda.values) | models.Q(tipo=""),
                name="vivienda_tipo_valido",
            ),
            # --------------------------------------------------------------
            # HU-11: las dos coordenadas van juntas o no va ninguna.
            #
            # Media coordenada no ubica nada: una latitud sin longitud es una línea
            # que cruza el planeta. Y sin la restricción, un formulario a medio
            # enviar o un script dejarían filas que parecen tener ubicación y no la
            # tienen, que es peor que no tenerla, porque un mapa las dibujaría en
            # cualquier parte.
            # --------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    models.Q(latitud__isnull=True, longitud__isnull=True)
                    | models.Q(latitud__isnull=False, longitud__isnull=False)
                ),
                name="vivienda_coordenadas_completas",
            ),
            # --------------------------------------------------------------
            # HU-11: el punto tiene que caer en Chile.
            #
            # No es una comprobación decorativa: el error más común al escribir
            # coordenadas a mano es OLVIDAR EL SIGNO, y una latitud +36 en vez de
            # -36 pone la vivienda en Argelia sin que nada avise. También atrapa el
            # clásico de intercambiar latitud y longitud.
            #
            # El rango incluye el territorio INSULAR y no solo el continental: si
            # se acotara a la longitud de Chile continental (-76 a -66), Rapa Nui
            # (-109,4) quedaría fuera, y es territorio nacional donde puede haber un
            # operativo. Un límite que rechaza datos verdaderos es peor que no
            # tenerlo.
            # --------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    models.Q(latitud__isnull=True)
                    | models.Q(
                        latitud__gte=LATITUD_MINIMA,
                        latitud__lte=LATITUD_MAXIMA,
                        longitud__gte=LONGITUD_MINIMA,
                        longitud__lte=LONGITUD_MAXIMA,
                    )
                ),
                name="vivienda_coordenadas_en_chile",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tenencia__in=TenenciaVivienda.values)
                    | models.Q(tenencia="")
                ),
                name="vivienda_tenencia_valida",
            ),
        ]
        indexes = [
            # La consulta del aviso de duplicado y la del listado por zona.
            models.Index(fields=["zona", "direccion"], name="idx_vivienda_zona"),
        ]

    def __str__(self):
        return self.direccion

    def get_absolute_url(self):
        return reverse("fichas:vivienda_detalle", kwargs={"pk": self.pk})

    # -- atajos por la jerarquía territorial --------------------------------

    @property
    def sector(self):
        return self.zona.sector

    @property
    def comuna(self):
        return self.zona.sector.comuna

    @property
    def operativo(self):
        return self.zona.sector.operativo

    @property
    def nombre_completo(self):
        """«Pasaje Los Robles 1425 · Zona 1 · Los Boldos»."""
        return f"{self.direccion} · {self.zona.nombre} · {self.zona.sector.nombre}"

    # -- ¿está descrita? ----------------------------------------------------

    #: Las características que hacen que una vivienda cuente como descrita.
    CARACTERISTICAS = (
        "tipo",
        "tenencia",
        "materialidad_muros",
        "origen_agua",
        "sistema_sanitario",
    )

    @property
    def datos_completos(self):
        """True si la vivienda tiene sus seis características registradas.

        Existe para que «sin describir» sea una respuesta explícita del modelo y no
        una deducción que cada pantalla haga a su manera. Sin esto, el listado
        preguntaría por `tipo`, la ficha por `tipo` y `tenencia`, y las dos
        estarían mostrando cosas distintas con la misma etiqueta.
        """
        if self.tiene_electricidad is None:
            return False

        return all(getattr(self, campo) for campo in self.CARACTERISTICAS)

    # -- la ubicación (HU-11) -----------------------------------------------

    #: Precisión a partir de la cual el punto se marca como poco fiable, en metros.
    #: Veinte metros es aproximadamente el ancho de una calle con sus dos veredas:
    #: por debajo de eso, el punto distingue una casa de la de enfrente; por encima,
    #: ya no.
    PRECISION_ACEPTABLE = 20

    #: A partir de esta distancia al resto de la zona, el sistema pregunta. En una
    #: zona urbana caben pocas manzanas, así que medio kilómetro de separación es
    #: casi siempre un error de captura y no una casa lejana.
    DISTANCIA_SOSPECHOSA_METROS = 500

    # Atajos a los límites del módulo, para que quien tenga una vivienda a mano no
    # necesite importarlos aparte. Apuntan a los mismos objetos: no son una copia.
    LATITUD_MINIMA = LATITUD_MINIMA
    LATITUD_MAXIMA = LATITUD_MAXIMA
    LONGITUD_MINIMA = LONGITUD_MINIMA
    LONGITUD_MAXIMA = LONGITUD_MAXIMA

    @property
    def tiene_ubicacion(self):
        return self.latitud is not None and self.longitud is not None

    @property
    def coordenadas(self):
        """«-36.826700, -73.049700», o None si no se ha capturado.

        Existe para que las plantillas no repitan el formato y para que el número
        se muestre siempre con los mismos decimales: media pantalla con seis
        decimales y la otra media con cuatro parece dos datos distintos.
        """
        if not self.tiene_ubicacion:
            return None

        return f"{self.latitud:.6f}, {self.longitud:.6f}"

    @property
    def precision_aceptable(self):
        """True si el aparato informó una precisión suficiente.

        Sin dato de precisión devuelve False: un punto del que no se sabe cuánto
        error tiene no se puede dar por bueno. Es la misma lógica con la que
        `datos_completos` trata el vacío en la HU-08.
        """
        if self.precision_metros is None:
            return False

        return self.precision_metros <= self.PRECISION_ACEPTABLE

    def distancia_a(self, latitud, longitud):
        """Metros en línea recta hasta otro punto, por la fórmula del haversine.

        ¿POR QUÉ NO SE USA GeoDjango / PostGIS?

        Porque haría falta instalar la extensión PostGIS en el servidor y las
        bibliotecas GEOS y PROJ en cada equipo, y todo lo que OPSO necesita de la
        geometría es esta única función. Es una dependencia grande, difícil de
        instalar en Windows y que complicaría la puesta en marcha del proyecto
        —que hoy es `pip install -r requirements.txt`— para ahorrarse doce líneas.

        Si algún día hicieran falta consultas espaciales de verdad —«las viviendas
        dentro de este polígono», «las diez más cercanas ordenadas por distancia»—
        PostGIS sería lo correcto y esta función habría que tirarla. Mientras la
        pregunta sea «¿está este punto lejos de aquel?», el haversine sobra.

        Devuelve metros y no kilómetros porque las distancias que interesan aquí
        son de decenas o cientos de metros, y trabajar en kilómetros obligaría a
        leer «0,08» donde se quiere leer «80».
        """
        if not self.tiene_ubicacion:
            return None

        radio_tierra = 6_371_000  # metros

        lat1, lon1 = radians(float(self.latitud)), radians(float(self.longitud))
        lat2, lon2 = radians(float(latitud)), radians(float(longitud))

        seno_lat = sin((lat2 - lat1) / 2) ** 2
        seno_lon = sin((lon2 - lon1) / 2) ** 2
        a = seno_lat + cos(lat1) * cos(lat2) * seno_lon

        return radio_tierra * 2 * atan2(sqrt(a), sqrt(1 - a))

    @classmethod
    def centro_de_la_zona(cls, zona, excluir=None):
        """Punto medio de las viviendas ya ubicadas de una zona, o None si no hay.

        Es la referencia contra la que se comprueba si una ubicación nueva es
        plausible. La idea es simple y funciona: **las casas de una zona están
        cerca unas de otras**, así que un punto a tres kilómetros del resto casi
        siempre es un error de captura —el teléfono devolvió la última posición
        conocida, o alguien escribió mal un dígito—.

        Se usa el promedio y no el centroide geodésico correcto porque la
        diferencia entre ambos, en un área de unas manzanas, es de centímetros; y
        porque el resultado no se muestra a nadie: solo sirve para decidir si
        preguntar.

        Devuelve None cuando la zona todavía no tiene ninguna vivienda ubicada, que
        es el caso de la primera casa de la jornada. Sin referencia no se compara
        nada: inventar una sería peor que no comprobar.
        """
        consulta = cls.objects.filter(zona=zona, latitud__isnull=False)

        if excluir is not None:
            consulta = consulta.exclude(pk=excluir)

        puntos = list(consulta.values_list("latitud", "longitud"))

        if not puntos:
            return None

        return (
            sum(lat for lat, _ in puntos) / len(puntos),
            sum(lon for _, lon in puntos) / len(puntos),
        )

    # -- hogares ------------------------------------------------------------

    def total_hogares(self):
        """Cuántas encuestas —es decir, cuántos hogares— hay en esta vivienda."""
        return self.encuestas.count()

    @property
    def tiene_varios_hogares(self):
        return self.total_hogares() > 1

    def puede_registrarse_trabajo(self):
        """¿Se puede levantar información aquí? (True, "") o (False, motivo).

        Se devuelve el MOTIVO y no un booleano suelto, por lo mismo que
        Comuna.puede_desactivarse() en la HU-05 y Sector.puede_recibir_asignaciones()
        en la HU-06: la vista tiene que poder EXPLICAR el rechazo. «No se puede
        porque el operativo está cerrado» es accionable; «no se puede» obliga a
        adivinar.
        """
        if not self.zona.sector.operativo.admite_cambios_de_territorio:
            return False, (
                f"El operativo «{self.zona.sector.operativo.nombre}» está cerrado: "
                "no se puede registrar ni modificar información en él."
            )

        if not self.zona.sector.activo:
            return False, (
                f"El sector «{self.zona.sector.nombre}» está desactivado: no forma "
                "parte del territorio vigente del operativo."
            )

        if not self.zona.activa:
            return False, (
                f"La zona «{self.zona.nombre}» está desactivada: no se cuenta en el "
                "avance del sector."
            )

        return True, ""


# ==========================================================================
# 2. LA ENCUESTA: EL TRABAJO Y SU ESTADO (HU-07)
# ==========================================================================


class EstadoEncuesta(models.TextChoices):
    """Ciclo de vida de una encuesta.

    Son TextChoices y no una tabla, por la misma razón que EstadoOperativo en la
    HU-05: el CÓDIGO consulta estos valores. Hay reglas que preguntan si una
    encuesta sigue pendiente para contarla en el trabajo del día, y un valor que el
    código compara debe ser una constante y no una fila que alguien pueda
    renombrar y romper el `if`.

    Los siete estados responden a preguntas distintas del encuestador:

      PENDIENTE   -> tengo que ir. Todavía no la he tocado.
      BORRADOR    -> fui, la empecé y quedó a medias. Tengo que volver o
                     terminarla (es el estado que usará la historia de borradores).
      COMPLETADA  -> la terminé y la envié. Ya no depende de mí.
      OBSERVADA   -> el supervisor me la devolvió con reparos. Vuelve a ser trabajo
                     mío, y por eso es el estado más urgente de todos.
      VALIDADA    -> el supervisor la aprobó. Cerrada de verdad.
      NO_UBICADA  -> la dirección no existe, o la vivienda está deshabitada.
      RECHAZADA   -> la familia no quiso participar.

    LOS DOS ÚLTIMOS NO SON FRACASOS, SON RESULTADOS. Una encuesta que no se pudo
    levantar tiene que poder cerrarse dejando constancia del motivo. Si el único
    final posible fuera COMPLETADA, esas puertas quedarían pendientes para siempre
    y el avance del operativo mentiría hacia abajo: nadie sabría distinguir «faltan
    40 por visitar» de «40 no se pueden levantar y ya se sabe».

    OBSERVADA y VALIDADA las escribe el supervisor, no el encuestador, y las
    transiciones que las producen pertenecen a la historia de validación de fichas
    (permiso `fichas.validar`, sembrado por la HU-04). Se definen ya porque el
    encuestador NECESITA VERLAS: «me devolvieron una ficha» es exactamente el tipo
    de cosa que esta historia existe para que no se pierda por teléfono.

    ----------------------------------------------------------------------
    EL OCTAVO ESTADO: ANULADA (HU-14)
    ----------------------------------------------------------------------
      ANULADA -> el supervisor determinó que la ficha no sirve y NO se va a
                 corregir: está duplicada, se levantó en la dirección equivocada o
                 sus datos no son creíbles.

    ¿POR QUÉ NO SE LLAMA «RECHAZADA», QUE ES LA PALABRA DE LA HISTORIA?

    Porque RECHAZADA ya existe desde la HU-07 y significa otra cosa muy distinta:
    LA FAMILIA rechazó participar. Son dos hechos opuestos —uno es una decisión de
    la familia y el otro del supervisor— y confundirlos arruinaría cualquier
    lectura del censo: «40 rechazadas» dejaría de distinguir «40 hogares no
    quisieron» de «40 fichas estaban mal hechas», que exigen respuestas contrarias.

    Reutilizar el nombre habría sido más cómodo y menos cierto. Se prefirió una
    palabra nueva y exacta.

    ANULADA Y OBSERVADA TAMBIÉN SON DISTINTAS, y es la diferencia que separa las
    dos historias del sprint: observar es DEVOLVER para que se corrija —la encuesta
    vuelve a ser trabajo abierto—; anular es CERRAR sin corregir, porque no hay nada
    que arreglar o porque arreglarlo exigiría levantarla de nuevo.
    """

    PENDIENTE = "PENDIENTE", "Pendiente"
    BORRADOR = "BORRADOR", "Borrador"
    COMPLETADA = "COMPLETADA", "Completada"
    OBSERVADA = "OBSERVADA", "Observada"
    VALIDADA = "VALIDADA", "Validada"
    NO_UBICADA = "NO_UBICADA", "No ubicada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    ANULADA = "ANULADA", "Anulada"


# --------------------------------------------------------------------------
# LOS DOS GRUPOS DE ESTADOS
#
# El ciclo de vida tiene siete estados, pero para el encuestador solo hay una
# pregunta: ¿esto es trabajo mío o ya no? Esa partición se escribe UNA vez, aquí,
# y la usan el modelo (para sus restricciones y propiedades), la vista (para
# contar) y las pruebas. Repartirla por el código en listas escritas a mano
# garantizaría que un octavo estado quedara fuera de alguna de ellas.
#
# La partición es EXHAUSTIVA y EXCLUYENTE: todo estado está en exactamente un
# grupo. De eso dependen las dos restricciones de coherencia de más abajo, y hay
# una prueba que lo comprueba para que siga siendo cierto.
# --------------------------------------------------------------------------

#: Requieren trabajo del encuestador. Son las que salen primero en su pantalla.
ESTADOS_ABIERTOS = (
    EstadoEncuesta.PENDIENTE,
    EstadoEncuesta.BORRADOR,
    EstadoEncuesta.OBSERVADA,
)

#: Ya no dependen del encuestador, con final feliz o sin él.
ESTADOS_CERRADOS = (
    EstadoEncuesta.COMPLETADA,
    EstadoEncuesta.VALIDADA,
    EstadoEncuesta.NO_UBICADA,
    EstadoEncuesta.RECHAZADA,
    EstadoEncuesta.ANULADA,
)

#: Resoluciones del supervisor (HU-14 y HU-15). Es un corte transversal a la
#: partición de arriba y no un tercer grupo: VALIDADA y ANULADA son cerradas,
#: OBSERVADA es abierta. Lo que comparten es OTRA cosa —las produce quien revisa,
#: no quien levanta— y por eso todas registran `revisada_por` y `revisada_en`.
ESTADOS_RESUELTOS = (
    EstadoEncuesta.VALIDADA,
    EstadoEncuesta.OBSERVADA,
    EstadoEncuesta.ANULADA,
)

#: Cerradas SIN haber levantado la información (HU-10).
#:
#: Es un subconjunto de ESTADOS_CERRADOS y no un tercer grupo: no rompe la
#: partición exhaustiva y excluyente de arriba. Se nombra aparte porque las dos
#: comparten una regla que las demás no tienen —exigen un motivo escrito— y esa
#: regla la comprueba una restricción de la base de datos.
ESTADOS_SIN_LEVANTAR = (
    EstadoEncuesta.NO_UBICADA,
    EstadoEncuesta.RECHAZADA,
)


class Encuesta(models.Model):
    """El trabajo de levantar la información de UN hogar en UNA vivienda.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 1 — la encuesta cuelga de la VIVIENDA (HU-08)
    ----------------------------------------------------------------------
    En la HU-07 colgaba directamente de la zona y llevaba ella misma la dirección.
    La HU-08 interpuso `Vivienda`, y el cambio no fue estético: es lo que permite
    que dos hogares de la misma casa compartan una sola descripción del inmueble
    en vez de tener cada uno su copia (ver la cabecera del módulo).

    El nivel territorial no se perdió: la vivienda cuelga de la ZONA, que es donde
    la HU-07 la había puesto, y por las mismas dos razones que entonces se
    escribieron y siguen siendo válidas:

      - La zona ya existía para esto. Su docstring en la HU-05 dice que el sector
        «no es una unidad de trabajo, es un objetivo de varios días» y que la zona
        lo parte en pedazos abarcables.
      - La zona lleva `viviendas_estimadas`, así que la estimación SE PUEDE
        CONTRASTAR CON LA REALIDAD: «la zona 1 estimaba 80 viviendas y llevamos
        93». Ahora el contraste es todavía más limpio, porque se comparan
        viviendas con viviendas y no viviendas con hogares.

    La zona, el sector, la comuna y el operativo siguen a un paso de distancia
    (`encuesta.zona`, `.sector`, `.comuna`, `.operativo`), así que el código que la
    HU-07 escribió sobre esas propiedades no cambió.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 2 — el encuestador es OBLIGATORIO
    ----------------------------------------------------------------------
    `censista` no admite nulos: una encuesta existe porque alguien tiene que
    levantarla. Se evaluó permitir encuestas «sin dueño» —un padrón que el
    supervisor reparte después— y se descartó porque ese padrón ya existe y es el
    territorio: una vivienda que todavía no es de nadie es, simplemente, una zona
    sin encuestas cargadas. Modelar además una encuesta huérfana crearía dos formas
    de decir lo mismo, y la pantalla del encuestador tendría que explicar por qué
    hay trabajo que no le aparece a nadie.

    PROTECT y no CASCADE, igual que en AsignacionSector.censista: borrar la cuenta
    de una persona no puede llevarse por delante las fichas del censo que levantó.
    La HU-03 ya estableció que las cuentas se deshabilitan y no se borran; esta
    clave foránea es la que hace que ese acuerdo lo garantice la base de datos.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 3 — el estado va acompañado de sus dos fechas
    ----------------------------------------------------------------------
    `estado` responde «¿cómo está?» y por sí solo no responde «¿desde cuándo?».
    Sin fechas, la pantalla no puede ordenar por antigüedad ni distinguir un
    borrador de ayer de uno de hace tres semanas, que es exactamente la diferencia
    entre «lo termino hoy» y «esto se quedó olvidado».

    Se guardan dos y no una porque marcan los dos límites del trabajo:
    `iniciada_en` (la primera visita) y `cerrada_en` (cuando dejó de depender del
    encuestador). Las dos están AMARRADAS AL ESTADO por sendas restricciones de la
    base de datos, y por eso el estado no se cambia a mano sino con
    `cambiar_estado()`: ver la explicación en ese método.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 4 — varias encuestas por vivienda, y CASCADE
    ----------------------------------------------------------------------
    La clave foránea a `Vivienda` no es única: dos hogares que comparten la casa
    son dos encuestas sobre la misma vivienda, y es el caso que el modelo de la
    HU-08 vino a resolver bien (ver la cabecera del módulo).

    `on_delete=CASCADE` aquí y PROTECT en `censista`, y no es una incoherencia. Es
    el mismo par de decisiones que tomó Sector en la HU-05: una encuesta no
    significa nada sin su vivienda —es el levantamiento DE esa vivienda—, así que
    si la vivienda se borrara sus encuestas se van con ella. La persona, en
    cambio, es una cuenta compartida por todo el sistema y borrarla no puede
    arrastrar el trabajo del censo.
    """

    #: Devoluciones a partir de las cuales el problema deja de ser la ficha (HU-15).
    #: Dos son parte del trabajo; a la tercera, lo que falla es que alguien no
    #: entendió cómo se llena el formulario.
    DEVOLUCIONES_PARA_ALERTAR = 3

    #: Días a partir de los cuales una encuesta lleva «demasiado» esperando
    #: revisión (HU-13). Cinco días hábiles es aproximadamente lo que un
    #: encuestador tarda en dejar de recordar una casa concreta y en salir de esa
    #: zona: pasado ese punto, devolverle la ficha cuesta otra visita entera.
    DIAS_ESPERA_PROLONGADA = 7

    vivienda = models.ForeignKey(
        Vivienda,
        on_delete=models.CASCADE,
        related_name="encuestas",
        verbose_name="vivienda",
        help_text="Vivienda en la que se levanta la información.",
    )
    censista = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.PROTECT,
        related_name="encuestas",
        verbose_name="encuestador",
        help_text="Persona que debe levantar esta encuesta.",
    )
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoEncuesta.choices,
        default=EstadoEncuesta.PENDIENTE,
        db_index=True,
        help_text="En qué etapa está el levantamiento de esta vivienda.",
    )
    observaciones = models.TextField(
        "observaciones",
        blank=True,
        help_text=(
            "Indicaciones para quien va a levantar esta encuesta. Ej.: «pasar "
            "después de las 19:00, trabajan todo el día»."
        ),
    )
    # ------------------------------------------------------------------
    # EL BORRADOR (HU-10)
    #
    # La HU-07 declaró `observaciones` como «indicaciones del supervisor O notas
    # del propio encuestador», y esa «o» era una ambigüedad que se paga en cuanto
    # los dos escriben en el mismo campo: la nota que el encuestador se deja a sí
    # mismo pisaría las instrucciones que le dejaron, o al revés.
    #
    # La HU-10 la resuelve partiendo la responsabilidad: `observaciones` son las
    # INDICACIONES que se reciben, y `nota_avance` es la nota que uno se deja. Dos
    # autores distintos, dos propósitos distintos, dos columnas.
    # ------------------------------------------------------------------
    nota_avance = models.TextField(
        "nota de avance",
        blank=True,
        help_text=(
            "Recordatorio para uno mismo al retomar la encuesta. Ej.: «falta el "
            "módulo de ingresos y los datos del hijo mayor»."
        ),
    )
    proxima_visita = models.DateField(
        "próxima visita",
        null=True,
        blank=True,
        help_text=(
            "Cuándo conviene volver. Vacío si no hace falta una segunda visita."
        ),
    )
    motivo_cierre = models.TextField(
        "motivo del cierre",
        blank=True,
        help_text=(
            "Por qué no se pudo levantar. Obligatorio al cerrar una encuesta como "
            "no ubicada o rechazada."
        ),
    )
    asignada_por = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encuestas_asignadas",
        verbose_name="asignada por",
        help_text="Quién encargó esta encuesta. Vacío si la creó el encuestador.",
    )
    # ------------------------------------------------------------------
    class Meta:
        db_table = "fichas_encuesta"
        verbose_name = "encuesta"
        verbose_name_plural = "encuestas"
        # Orden GEOGRÁFICO por defecto: es el orden en que se recorre la calle.
        #
        # Ojo: NO es el orden en que se muestran en «Mis encuestas». Esa pantalla
        # ordena por urgencia (ver MisEncuestasView), que es una decisión de esa
        # vista y no del modelo. Aquí se deja el orden que sirve a cualquier otro
        # consumidor —el admin, un reporte, una exportación—, donde lo natural es
        # ver juntas las viviendas de la misma zona.
        ordering = [
            "vivienda__zona__sector__nombre",
            "vivienda__zona__nombre",
            "vivienda__direccion",
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=EstadoEncuesta.values),
                name="encuesta_estado_valido",
            ),
            # --------------------------------------------------------------
            # LAS DOS RESTRICCIONES QUE AMARRAN EL ESTADO A SUS FECHAS
            #
            # Misma técnica y mismo motivo que `asignacion_baja_coherente` en la
            # HU-06: son columnas que describen el mismo hecho y tienen que
            # moverse juntas. Un `save()` que cambiara el estado y olvidara la
            # fecha dejaría una fila que se contradice consigo misma, y el avance
            # del operativo —que se calcula justamente con estas columnas—
            # empezaría a mentir sin que ningún error avisara.
            #
            # Se escriben con los valores literales y no con las tuplas de arriba
            # porque una restricción viaja a la migración: tiene que seguir
            # significando lo mismo dentro de diez versiones del modelo.
            # --------------------------------------------------------------
            models.CheckConstraint(
                # iniciada_en es NULL si y solo si la encuesta está PENDIENTE.
                condition=(
                    models.Q(estado="PENDIENTE", iniciada_en__isnull=True)
                    | (~models.Q(estado="PENDIENTE") & models.Q(iniciada_en__isnull=False))
                ),
                name="encuesta_inicio_coherente",
            ),
            models.CheckConstraint(
                # cerrada_en es NULL si y solo si la encuesta sigue abierta.
                condition=(
                    models.Q(
                        estado__in=["PENDIENTE", "BORRADOR", "OBSERVADA"],
                        cerrada_en__isnull=True,
                    )
                    | models.Q(
                        estado__in=[
                            "COMPLETADA",
                            "VALIDADA",
                            "NO_UBICADA",
                            "RECHAZADA",
                            "ANULADA",
                        ],
                        cerrada_en__isnull=False,
                    )
                ),
                name="encuesta_cierre_coherente",
            ),
            # --------------------------------------------------------------
            # HU-10: cerrar sin levantar exige DECIR POR QUÉ.
            #
            # «No ubicada» y «rechazada» son resultados legítimos —la HU-07 lo
            # argumentó— pero solo son información si consta el motivo. Sin esta
            # restricción, una zona podría acumular veinte encuestas cerradas sin
            # que nadie pueda distinguir «la dirección no existe» de «pasé y no
            # había nadie», que exigen decisiones opuestas del supervisor.
            #
            # Se lee: o NO está cerrada sin levantar, o tiene motivo escrito.
            # --------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado__in=["NO_UBICADA", "RECHAZADA"])
                    | ~models.Q(motivo_cierre="")
                ),
                name="encuesta_cierre_con_motivo",
            ),
            # --------------------------------------------------------------
            # HU-14 y HU-15: anular y devolver exigen DECIR POR QUÉ.
            #
            # Mismo criterio que `encuesta_cierre_con_motivo` en la HU-10, aplicado
            # a las decisiones del supervisor en vez de a las del encuestador.
            #
            # Las dos lo necesitan por motivos distintos, y los dos son fuertes:
            #
            #   ANULADA   -> una ficha descartada sin explicación no se puede
            #                defender ante nadie: ni ante el encuestador cuyo
            #                trabajo se tira, ni ante quien audite el censo.
            #   OBSERVADA -> devolver sin decir qué corregir no pide una
            #                corrección, solo devuelve trabajo. El encuestador
            #                tendría que adivinar qué mirar, y volvería a enviar
            #                lo mismo.
            #
            # VALIDADA queda fuera a propósito: aprobar es el resultado esperado y
            # exigir un texto para cada ficha buena produciría cientos de «ok» que
            # nadie va a leer.
            #
            # La restricción de la HU-14 se llamaba `encuesta_anulacion_con_motivo`
            # y cubría solo ANULADA. La HU-15 la reemplaza por esta, con un nombre
            # que describe las dos: reutilizar el nombre anterior habría dejado una
            # restricción cuyo nombre miente sobre lo que comprueba.
            # --------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado__in=["ANULADA", "OBSERVADA"])
                    | ~models.Q(comentario_revision="")
                ),
                name="encuesta_resolucion_con_motivo",
            ),
        ]
        indexes = [
            # «Mis encuestas»: la consulta que hace el encuestador al entrar, y la
            # única que se ejecuta muchas veces al día desde un teléfono.
            models.Index(fields=["censista", "estado"], name="idx_encuesta_censista"),
            # «¿Cómo va esta vivienda / esta zona?»: la consulta del avance, que
            # usarán el panel del supervisor y los reportes. Va por vivienda
            # porque desde la HU-08 la zona se alcanza a través de ella.
            models.Index(fields=["vivienda", "estado"], name="idx_encuesta_vivienda"),
        ]

    def __str__(self):
        return f"{self.direccion} ({self.get_estado_display()})"

    def get_absolute_url(self):
        return reverse("fichas:encuesta_detalle", kwargs={"pk": self.pk})

    # ------------------------------------------------------------------
    # Atajos por la vivienda y por la jerarquía territorial.
    #
    # Mismo recurso que Zona.operativo en la HU-05: las plantillas y las vistas
    # preguntan por la dirección, el sector y la comuna constantemente, y sin
    # estas propiedades cada llamada escribiría `encuesta.vivienda.zona.sector`,
    # que es justo el tipo de encadenamiento que se copia mal.
    #
    # `direccion`, `referencia` y `zona` eran COLUMNAS de esta tabla en la HU-07 y
    # desde la HU-08 son propiedades que delegan en la vivienda. Mantener los
    # mismos nombres no fue casualidad: es lo que permitió mover el dato de tabla
    # sin reescribir las plantillas ni las pruebas que ya lo leían.
    #
    # Todas leen relaciones que las vistas traen con select_related, así que no
    # lanzan consultas extra.
    # ------------------------------------------------------------------

    @property
    def direccion(self):
        return self.vivienda.direccion

    @property
    def referencia(self):
        return self.vivienda.referencia

    @property
    def zona(self):
        return self.vivienda.zona

    @property
    def sector(self):
        return self.vivienda.zona.sector

    @property
    def comuna(self):
        return self.vivienda.zona.sector.comuna

    @property
    def operativo(self):
        return self.vivienda.zona.sector.operativo

    @property
    def ubicacion(self):
        """«Pasaje Los Robles 1425 · Zona 1 · Los Boldos», para listados y bitácora.

        Existe por lo mismo que Zona.nombre_completo: una dirección suelta no
        identifica nada fuera de su zona, porque en un operativo grande hay calles
        con el mismo nombre en comunas distintas.
        """
        return self.vivienda.nombre_completo

    # ------------------------------------------------------------------
    # El dato levantado (HU-08)
    # ------------------------------------------------------------------

    @property
    def tiene_grupo_familiar(self):
        """True si ya se registró el hogar de esta encuesta.

        Se comprueba con hasattr y no con un try/except sobre el acceso, porque en
        una relación uno a uno Django lanza RelatedObjectDoesNotExist cuando el
        otro lado no existe, y `hasattr` es la forma que la documentación de
        Django recomienda para preguntarlo.

        Existe porque «¿ya empecé a levantar esta encuesta?» es una pregunta que se
        hacen la plantilla, la vista y la historia de borradores, y las tres deben
        responderla igual.
        """
        return hasattr(self, "grupo_familiar")

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def requiere_trabajo(self):
        """True si sigue siendo trabajo del encuestador.

        Es la pregunta que ordena toda la pantalla de la HU-07, y por eso se
        responde AQUÍ y no con un `if` repetido en la vista y en la plantilla. Un
        octavo estado se agrega a ESTADOS_ABIERTOS y todo lo demás se entera solo.
        """
        return self.estado in ESTADOS_ABIERTOS

    @property
    def esta_cerrada(self):
        return self.estado in ESTADOS_CERRADOS

    @property
    def en_revision(self):
        """Enviada y a la espera de que el supervisor la valide."""
        return self.estado == EstadoEncuesta.COMPLETADA

    @property
    def necesita_correccion(self):
        """Devuelta por el supervisor: es lo más urgente de la lista.

        Se distingue de `requiere_trabajo` porque no es lo mismo trabajo nuevo que
        trabajo REHECHO: una ficha observada ya consumió una visita, tiene a un
        supervisor esperando y bloquea el cierre de la zona.
        """
        return self.estado == EstadoEncuesta.OBSERVADA

    @property
    def color_estado(self):
        """Sufijo de la clase de Bootstrap con que se pinta la etiqueta del estado.

        Vive en el modelo y no en la plantilla porque el color no es decoración:
        comunica urgencia, y esa correspondencia entre estado y urgencia es una
        regla del negocio. En la plantilla habría que repetirla en el listado, en
        la ficha y en el panel, y bastaría con que alguien agregara un estado para
        que dos pantallas lo pintaran y la tercera lo dejara gris.

        Es un paso más allá de lo que hizo la HU-05 con `_estado_operativo.html`
        —que resolvió la repetición con un fragmento, pero dejó el condicional en
        el HTML— y la razón es que aquí hay siete estados y no tres.
        """
        return {
            EstadoEncuesta.PENDIENTE: "secondary",
            EstadoEncuesta.BORRADOR: "warning",
            EstadoEncuesta.COMPLETADA: "primary",
            EstadoEncuesta.OBSERVADA: "danger",
            EstadoEncuesta.VALIDADA: "success",
            EstadoEncuesta.NO_UBICADA: "dark",
            EstadoEncuesta.RECHAZADA: "dark",
            EstadoEncuesta.ANULADA: "dark",
        }.get(self.estado, "secondary")

    def cambiar_estado(self, nuevo_estado, guardar=True):
        """Cambia el estado y ajusta las dos fechas que lo acompañan.

        ES EL ÚNICO CAMINO CORRECTO PARA MOVER EL ESTADO, y existe por lo mismo que
        `AsignacionSector.desactivar()` en la HU-06: hay columnas que tienen que
        moverse juntas, y si cada vista lo hiciera a mano alguna olvidaría una. La
        diferencia es que allí eran dos columnas y una transición, y aquí son tres
        columnas y siete estados —siete oportunidades de olvidarse—, así que la
        regla se centraliza con más razón todavía.

        Las dos reglas que aplica, y que son exactamente las que comprueban las
        restricciones de la tabla:

          - Al salir de PENDIENTE se marca `iniciada_en`, si no estaba. Incluso
            hacia NO_UBICADA: registrar que una vivienda no se pudo ubicar implica
            haber ido a buscarla, así que hubo una visita y tiene fecha.
          - `cerrada_en` se pone al pasar a un estado cerrado y se BORRA al volver
            a uno abierto. Ese borrado es el caso que justifica el método: una
            ficha observada vuelve a ser trabajo pendiente, y si conservara su
            fecha de cierre aparecería como terminada en cualquier recuento.

        No valida qué transiciones son legales (de PENDIENTE a VALIDADA, por
        ejemplo) a propósito: quién puede mover qué es una decisión de permisos y
        se resuelve en las vistas de cada historia, que son las que saben quién
        está pidiendo el cambio. El modelo se ocupa de que la fila quede coherente,
        que es lo que nadie más puede garantizar.
        """
        nuevo_estado = EstadoEncuesta(nuevo_estado)
        ahora = timezone.now()

        self.estado = nuevo_estado

        if nuevo_estado == EstadoEncuesta.PENDIENTE:
            self.iniciada_en = None
        elif self.iniciada_en is None:
            self.iniciada_en = ahora

        if nuevo_estado in ESTADOS_CERRADOS:
            if self.cerrada_en is None:
                self.cerrada_en = ahora
        else:
            self.cerrada_en = None

        if guardar:
            # Se escriben las CUATRO columnas que gobiernan las restricciones de
            # coherencia de esta tabla, y no solo las dos fechas.
            #
            # `motivo_cierre` está en la lista desde la HU-10 por un problema
            # concreto: con update_fields, cualquier cambio en memoria que no esté
            # nombrado se descarta EN SILENCIO. Quien escribía el motivo y llamaba
            # después a este método veía cómo la base rechazaba la fila por falta de
            # motivo… con el motivo delante, puesto en el objeto pero nunca
            # guardado. Si una columna participa en la misma restricción que el
            # estado, tiene que viajar con él.
            self.save(
                update_fields=[
                    "estado",
                    "iniciada_en",
                    "cerrada_en",
                    "motivo_cierre",
                    "actualizada_en",
                ]
            )

        return self

    # ------------------------------------------------------------------
    # ¿ESTÁ TERMINADA? (HU-10)
    #
    # Es la pregunta que cierra el sprint del encuestador, y la respuesta no la
    # puede dar una sola tabla: depende de la vivienda (¿está descrita?), del
    # hogar (¿se registró?) y de las personas (¿están todas?). Por eso vive aquí,
    # en la encuesta, que es lo único que conoce las tres.
    # ------------------------------------------------------------------

    def pasos_pendientes(self):
        """Lo que falta para poder dar la encuesta por terminada.

        Devuelve una lista de diccionarios con `texto` y `ruta` (el nombre de la URL
        a la que hay que ir), no una lista de textos ni un booleano.

        Es deliberado, y es lo que convierte esta historia en algo más que un botón:
        «no puedes completar la encuesta» obliga a adivinar qué falta y a buscarlo
        pantalla por pantalla. «Falta describir la vivienda → [ir]» se resuelve en
        un toque. Es el mismo criterio con que la HU-05 devuelve el MOTIVO en
        `puede_desactivarse()` en vez de un booleano suelto.

        El orden de la lista es el orden en que hay que hacer las cosas, no el
        orden en que se comprobaron: primero la casa, después el hogar, después las
        personas. Así el primer elemento es siempre el siguiente paso.

        ------------------------------------------------------------------
        LA UBICACIÓN GPS NO ESTÁ EN ESTA LISTA, Y ES UNA DECISIÓN (HU-11)
        ------------------------------------------------------------------
        Sería fácil agregarla y sería un error. El GPS depende de que haya señal, de
        que el sistema operativo dé el permiso y de que el teléfono no esté bajo
        techo: nada de eso lo controla el encuestador. Exigirlo para terminar
        dejaría fichas completas y correctas atrapadas en borrador por un fallo de
        cobertura, y la salida sería inventar coordenadas.

        Lo que sí hace el sistema es AVISAR en la pantalla de terminar. La
        diferencia entre bloquear y avisar es la misma de siempre: se bloquea lo que
        el usuario puede resolver, y se avisa de lo que quizá no.
        """
        pendientes = []

        if not self.vivienda.datos_completos:
            pendientes.append(
                {
                    "texto": "Describir la vivienda (tipo, materialidad, servicios).",
                    "ruta": "fichas:vivienda_editar",
                    "argumento": self.vivienda_id,
                }
            )

        if not self.tiene_grupo_familiar:
            pendientes.append(
                {
                    "texto": "Registrar los datos del hogar.",
                    "ruta": "fichas:registrar_hogar",
                    "argumento": self.pk,
                }
            )
            # Sin hogar no se puede comprobar nada de las personas: se corta aquí
            # para no listar tres pasos que dicen lo mismo.
            return pendientes

        hogar = self.grupo_familiar

        if hogar.jefe_hogar_registrado is None:
            pendientes.append(
                {
                    "texto": "Registrar a la jefa o jefe de hogar.",
                    "ruta": "fichas:integrantes",
                    "argumento": self.pk,
                }
            )

        if not hogar.esta_completo:
            faltan = hogar.integrantes_pendientes
            pendientes.append(
                {
                    "texto": (
                        f"Registrar {faltan} persona{'s' if faltan != 1 else ''} "
                        f"más: la familia declaró {hogar.integrantes_declarados}."
                    ),
                    "ruta": "fichas:integrantes",
                    "argumento": self.pk,
                }
            )

        return pendientes

    @property
    def puede_completarse(self):
        """True si no falta nada por registrar.

        No comprueba el estado ni el territorio: solo si los DATOS están completos.
        Quién puede completarla y cuándo lo decide `puede_registrarse()`, y las dos
        cosas se preguntan por separado a propósito: una encuesta puede estar
        completa y cerrada (nada que hacer) o abierta e incompleta (falta trabajo),
        y son situaciones distintas que la pantalla explica distinto.
        """
        return not self.pasos_pendientes()

    @property
    def visita_pendiente_vencida(self):
        """True si se anotó volver en una fecha que ya pasó.

        Es el aviso que evita el olvido silencioso: un borrador con «volver el
        jueves» y hoy es lunes de la semana siguiente no es trabajo pendiente
        cualquiera, es trabajo que se escapó.
        """
        if self.proxima_visita is None or not self.requiere_trabajo:
            return False

        return self.proxima_visita <= timezone.localdate()


    # ------------------------------------------------------------------
    def clean(self):
        """Validación de modelo: coherencia entre el estado y sus fechas.

        Duplica lo que ya garantizan las dos restricciones de la tabla, y eso es
        deliberado: la restricción protege el DATO y esta validación protege a la
        PERSONA. Sin ella, guardar desde /admin/ una encuesta pendiente con fecha
        de cierre respondería con un error 500 de PostgreSQL en vez de un mensaje
        junto al campo equivocado.

        Es el mismo criterio con que Operativo.clean() repite en Python la
        comprobación de fechas que ya hace `operativo_fechas_coherentes`.
        """
        super().clean()

        if self.estado == EstadoEncuesta.PENDIENTE and self.iniciada_en:
            raise ValidationError(
                {
                    "iniciada_en": (
                        "Una encuesta pendiente todavía no se ha visitado: no "
                        "puede tener fecha de inicio."
                    )
                }
            )

        if self.estado != EstadoEncuesta.PENDIENTE and not self.iniciada_en:
            raise ValidationError(
                {
                    "iniciada_en": (
                        "Una encuesta que ya no está pendiente tiene que tener "
                        "fecha de inicio."
                    )
                }
            )

        if self.estado in ESTADOS_CERRADOS and not self.cerrada_en:
            raise ValidationError(
                {
                    "cerrada_en": (
                        f"Una encuesta en estado «{self.get_estado_display()}» "
                        "tiene que tener fecha de cierre."
                    )
                }
            )

        if self.estado in ESTADOS_ABIERTOS and self.cerrada_en:
            raise ValidationError(
                {
                    "cerrada_en": (
                        f"Una encuesta en estado «{self.get_estado_display()}» "
                        "sigue abierta: no puede tener fecha de cierre."
                    )
                }
            )


# ==========================================================================
# 3. EL GRUPO FAMILIAR: EL DATO LEVANTADO (HU-08)
# ==========================================================================


class GrupoFamiliar(models.Model):
    """El hogar que vive en la vivienda: lo que la encuesta viene a averiguar.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 1 — uno a uno con la encuesta, y no columnas de ella
    ----------------------------------------------------------------------
    Todo esto cabría como columnas de `Encuesta`, y sería un error por dos razones
    distintas:

      a) MEZCLARÍA GESTIÓN Y CONTENIDO. `Encuesta` gobierna el trabajo (quién,
         estado, fechas) y esta tabla guarda el censo (quién vive, cuántos son,
         cuánto ingresan). Con las historias que faltan del sprint, `Encuesta`
         acabaría con treinta columnas de las que la mitad no tienen nada que ver
         con su función.

      b) PERDERÍA UNA INFORMACIÓN QUE HOY ES GRATIS. Que la fila EXISTA significa
         «aquí ya se levantó algo», y que no exista significa «esto no se ha
         tocado». Con columnas nulas dentro de Encuesta habría que preguntar
         «¿está vacío el nombre del jefe de hogar?» para deducir lo mismo, y esa
         deducción se escribiría distinta en cada pantalla.

    Por eso `Encuesta.tiene_grupo_familiar` es una comprobación de existencia y no
    de contenido.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 2 — CASCADE, al revés que casi todo el proyecto
    ----------------------------------------------------------------------
    OPSO desactiva en vez de borrar prácticamente en todas partes: cuentas (HU-03),
    comunas y sectores (HU-05), asignaciones (HU-06). Aquí se usa CASCADE, y no es
    un descuido: este dato no tiene ninguna existencia fuera de su encuesta. No es
    «el hogar de la casa 1425», que sobreviviría al levantamiento; es «lo que se
    respondió en ESTA encuesta». Sin la encuesta, la fila no significa nada y no
    hay ningún historial que preservar en ella.

    La encuesta, en cambio, sigue sin borrarse nunca: se cierra con un estado.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 3 — `integrantes_declarados` existe aunque venga la HU-09
    ----------------------------------------------------------------------
    La historia siguiente registra a las personas del hogar una por una, así que
    este número se podría calcular contándolas. Se guarda igual, y por el mismo
    motivo por el que la HU-05 guarda `viviendas_estimadas` en la zona teniendo
    después las viviendas reales: son dos datos distintos y su DIFERENCIA es
    información.

    «La señora dijo que viven seis y hay tres personas registradas» significa que
    la encuesta está incompleta, y eso solo se puede detectar si se guardó lo que
    la señora dijo. Sin este campo, una ficha a medias sería indistinguible de una
    ficha terminada de un hogar de tres.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 4 — el RUT del jefe de hogar es OPCIONAL
    ----------------------------------------------------------------------
    Es el único dato identificatorio fuerte del formulario y por eso da la
    tentación de exigirlo. No se exige, por una razón de terreno y otra legal:

      - En terreno, mucha gente no lo recuerda de memoria y no siempre está
        dispuesta a ir a buscar el carnet a la primera visita. Exigirlo
        convertiría una encuesta completa en una encuesta que no se puede guardar.
      - Legalmente, el RUT es un dato personal y pedirlo como condición para
        registrar un hogar es recoger más de lo necesario para el fin declarado
        (Ley N° 19.628 y Ley N° 21.719).

    Cuando SÍ se entrega, se valida con el mismo validador de la HU-01
    (`validar_rut`, con dígito verificador) y se normaliza con `limpiar_rut`, para
    que «12.345.678-5» y «12345678-5» sean el mismo dato y no dos.
    """

    encuesta = models.OneToOneField(
        Encuesta,
        on_delete=models.CASCADE,
        related_name="grupo_familiar",
        verbose_name="encuesta",
        help_text="Encuesta en la que se levantó este hogar.",
    )
    jefe_hogar_nombre = models.CharField(
        "nombre del jefe o jefa de hogar",
        max_length=150,
        help_text="Nombre completo de quien la familia reconoce como jefe de hogar.",
    )
    jefe_hogar_rut = models.CharField(
        "RUT del jefe o jefa de hogar",
        max_length=12,
        blank=True,
        validators=[validar_rut],
        help_text="Formato 12345678-9. Opcional: no se exige para poder registrar.",
    )
    telefono_contacto = models.CharField(
        "teléfono de contacto",
        max_length=20,
        blank=True,
        help_text="Para coordinar una segunda visita si la encuesta queda a medias.",
    )
    integrantes_declarados = models.PositiveSmallIntegerField(
        "personas que viven en el hogar",
        help_text=(
            "Cuántas personas declara la familia. Se contrasta con las que se "
            "registren una por una."
        ),
    )
    ingreso_mensual = models.PositiveIntegerField(
        "ingreso mensual del hogar",
        null=True,
        blank=True,
        help_text=(
            "Suma aproximada en pesos de todos los ingresos del hogar. Opcional: "
            "es la pregunta que más se prefiere no contestar."
        ),
    )
    observaciones = models.TextField(
        "observaciones",
        blank=True,
        help_text="Situaciones que el formulario no recoge y conviene dejar por escrito.",
    )
    registrado_en = models.DateTimeField("registrado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "fichas_grupo_familiar"
        verbose_name = "grupo familiar"
        verbose_name_plural = "grupos familiares"
        ordering = ["jefe_hogar_nombre"]
        constraints = [
            # Un hogar tiene al menos una persona: el propio jefe de hogar. Un cero
            # no es un dato desconocido —para eso el campo sería nulo—, es un dato
            # imposible, y aceptarlo desviaría cualquier promedio del operativo.
            models.CheckConstraint(
                condition=models.Q(integrantes_declarados__gte=1),
                name="grupo_familiar_al_menos_una_persona",
            ),
        ]

    def __str__(self):
        return f"Hogar de {self.jefe_hogar_nombre}"

    def save(self, *args, **kwargs):
        """Normaliza el RUT antes de escribir, igual que hace Usuario.save()."""
        self.jefe_hogar_rut = limpiar_rut(self.jefe_hogar_rut) or ""
        super().save(*args, **kwargs)

    @property
    def ingreso_por_persona(self):
        """Ingreso mensual dividido por el número de personas declaradas.

        Es el indicador que de verdad se usa para focalizar: 600.000 pesos son
        holgura para una persona sola y pobreza para un hogar de seis. Se calcula
        aquí y no en la plantilla porque es una regla del negocio, y porque una
        división en una plantilla obliga a repetir la comprobación del cero.

        Devuelve None si no se declaró el ingreso, que es distinto de cero.
        """
        if self.ingreso_mensual is None or not self.integrantes_declarados:
            return None

        return self.ingreso_mensual // self.integrantes_declarados

    # ------------------------------------------------------------------
    # El recuento de personas (HU-09)
    #
    # Aquí es donde `integrantes_declarados` cobra sentido. La HU-08 lo guardó
    # aunque la HU-09 fuera a permitir contar las personas una por una, con este
    # argumento: «son dos datos distintos y su DIFERENCIA es información». Estas
    # tres propiedades son esa diferencia, convertida en algo que la pantalla
    # puede mostrar.
    # ------------------------------------------------------------------

    def total_integrantes(self):
        """Personas efectivamente registradas."""
        return self.integrantes.count()

    def integrantes_ordenados(self):
        """Las personas del hogar, con el jefe de hogar primero y luego por edad.

        El orden importa para leer: una lista de seis nombres donde hay que buscar
        cuál es el jefe de hogar obliga a recorrerla entera cada vez, y el
        parentesco de todos los demás se entiende respecto a esa persona.

        Se resuelve con un CASE de SQL —la misma técnica que ORDEN_POR_URGENCIA en
        la HU-07— y no con `sorted()` en Python, para que siga valiendo si algún
        día esta lista se pagina o se agrega a un reporte.
        """
        from django.db.models import Case, IntegerField, Value, When

        return self.integrantes.annotate(
            orden=Case(
                When(parentesco=Parentesco.JEFE_HOGAR, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("orden", "fecha_nacimiento")

    @property
    def integrantes_pendientes(self):
        """Cuántas personas faltan por registrar, según lo que declaró la familia.

        Nunca es negativo: si se registraron MÁS de las declaradas, lo que sobra no
        es un pendiente en negativo, es una discrepancia, y la responde
        `hay_discrepancia`. Devolver -2 obligaría a cada plantilla a acordarse de
        que el número puede ser negativo.
        """
        return max(0, self.integrantes_declarados - self.total_integrantes())

    @property
    def esta_completo(self):
        """True si hay tantas personas registradas como declaró la familia."""
        return self.total_integrantes() >= self.integrantes_declarados

    @property
    def hay_discrepancia(self):
        """True si se registraron MÁS personas de las que la familia declaró.

        No es un error: en terreno pasa que la familia dice «somos cuatro» y al
        enumerar aparece la abuela que vive en la pieza del fondo. Lo que no puede
        pasar es que el sistema lo esconda, porque el número declarado es el que
        se usó para calcular el ingreso por persona.
        """
        return self.total_integrantes() > self.integrantes_declarados

    @property
    def jefe_hogar_registrado(self):
        """El integrante marcado como jefe de hogar, o None si aún no se registró.

        Existe porque el nombre del jefe de hogar está en DOS sitios y eso podría
        parecer una duplicación descuidada. No lo es, y la diferencia es la razón
        de esta propiedad:

          `jefe_hogar_nombre` es la IDENTIFICACIÓN DEL HOGAR, tomada en el primer
          contacto —«¿con quién hablo?»— antes de enumerar a nadie. Es lo que
          etiqueta el hogar en los listados y lo que sobrevive si la enumeración
          nunca llega a hacerse, que es exactamente el caso de un borrador.

          El INTEGRANTE con parentesco JEFE_HOGAR es la persona censada, con su
          RUT, su edad, su escolaridad y su ocupación.

        Una es una etiqueta y el otro es un registro. El sistema las mantiene
        coherentes prellenando el formulario con la etiqueta y avisando si al final
        no coinciden (ver `nombre_del_jefe_coincide`).
        """
        return self.integrantes.filter(parentesco=Parentesco.JEFE_HOGAR).first()

    @property
    def nombre_del_jefe_coincide(self):
        """¿La etiqueta del hogar y la persona censada dicen lo mismo?

        Devuelve True mientras no haya con qué comparar: un hogar sin jefe
        registrado todavía no puede contradecirse. Se compara en minúsculas y sin
        espacios sobrantes, porque «Rosa Millán» y «rosa  millán» son la misma
        persona y avisar de eso sería ruido.
        """
        jefe = self.jefe_hogar_registrado

        if jefe is None:
            return True

        return " ".join(self.jefe_hogar_nombre.lower().split()) == " ".join(
            jefe.nombre_completo.lower().split()
        )


# ==========================================================================
# 4. LOS INTEGRANTES DEL HOGAR (HU-09)
# ==========================================================================


class Parentesco(models.TextChoices):
    """Relación de cada persona con el jefe o jefa de hogar.

    Se mide el parentesco RESPECTO AL JEFE DE HOGAR y no entre todos con todos,
    que es como lo hace el censo y como se puede preguntar en una puerta. La
    alternativa —un grafo de relaciones familiares— daría más información y
    tardaría media hora por hogar.
    """

    JEFE_HOGAR = "JEFE_HOGAR", "Jefe o jefa de hogar"
    CONYUGE = "CONYUGE", "Cónyuge o conviviente"
    HIJO = "HIJO", "Hijo o hija"
    PADRE_MADRE = "PADRE_MADRE", "Padre o madre"
    HERMANO = "HERMANO", "Hermano o hermana"
    NIETO = "NIETO", "Nieto o nieta"
    OTRO_PARIENTE = "OTRO_PARIENTE", "Otro pariente"
    NO_PARIENTE = "NO_PARIENTE", "Sin parentesco"


class Sexo(models.TextChoices):
    """Sexo de la persona, con la opción de no responder.

    «Prefiere no responder» es una opción explícita y no la ausencia de dato. La
    diferencia importa: un vacío no distingue a quien no quiso contestar de la
    pregunta que el encuestador olvidó hacer, y solo la primera es una respuesta
    que hay que respetar.
    """

    FEMENINO = "FEMENINO", "Femenino"
    MASCULINO = "MASCULINO", "Masculino"
    OTRO = "OTRO", "Otro"
    NO_RESPONDE = "NO_RESPONDE", "Prefiere no responder"


class NivelEducacional(models.TextChoices):
    """Último nivel de estudios alcanzado."""

    SIN_ESTUDIOS = "SIN_ESTUDIOS", "Sin estudios formales"
    BASICA_INCOMPLETA = "BASICA_INCOMPLETA", "Básica incompleta"
    BASICA_COMPLETA = "BASICA_COMPLETA", "Básica completa"
    MEDIA_INCOMPLETA = "MEDIA_INCOMPLETA", "Media incompleta"
    MEDIA_COMPLETA = "MEDIA_COMPLETA", "Media completa"
    TECNICA = "TECNICA", "Técnica de nivel superior"
    UNIVERSITARIA = "UNIVERSITARIA", "Universitaria"
    POSTGRADO = "POSTGRADO", "Postgrado"


class SituacionOcupacional(models.TextChoices):
    """A qué se dedica la persona.

    «Labores del hogar» está separada de «no trabaja» a propósito: son situaciones
    distintas y confundirlas invisibiliza trabajo no remunerado, que en un
    operativo social es justamente parte de lo que se quiere ver.
    """

    TRABAJA = "TRABAJA", "Trabaja"
    BUSCA_TRABAJO = "BUSCA_TRABAJO", "Busca trabajo"
    ESTUDIA = "ESTUDIA", "Estudia"
    LABORES_HOGAR = "LABORES_HOGAR", "Labores del hogar"
    JUBILADO = "JUBILADO", "Jubilado o pensionado"
    NO_TRABAJA = "NO_TRABAJA", "No trabaja ni busca trabajo"


class PuebloOriginario(models.TextChoices):
    """Pueblo originario al que la persona declara pertenecer.

    Los nueve pueblos son los reconocidos por la Ley Indígena N° 19.253 más el
    pueblo chango, incorporado en 2020 por la Ley N° 21.273. Es un dato
    AUTODECLARADO: lo que vale es lo que la persona dice, no lo que el encuestador
    deduzca de su apellido.
    """

    NINGUNO = "NINGUNO", "No pertenece a ninguno"
    MAPUCHE = "MAPUCHE", "Mapuche"
    AYMARA = "AYMARA", "Aymara"
    RAPANUI = "RAPANUI", "Rapa Nui"
    LICKANANTAY = "LICKANANTAY", "Lickanantay (atacameño)"
    QUECHUA = "QUECHUA", "Quechua"
    COLLA = "COLLA", "Colla"
    DIAGUITA = "DIAGUITA", "Diaguita"
    KAWESQAR = "KAWESQAR", "Kawésqar"
    YAGAN = "YAGAN", "Yagán"
    CHANGO = "CHANGO", "Chango"
    NO_RESPONDE = "NO_RESPONDE", "Prefiere no responder"


class Integrante(models.Model):
    """Una persona que vive en el hogar.

    Es el nivel más fino de todo OPSO y el final del recorrido que empezó en la
    HU-05 con las regiones:

        Región → Comuna → Operativo → Sector → Zona → Vivienda → Hogar → PERSONA

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 1 — cuelga del HOGAR, no de la vivienda ni de la encuesta
    ----------------------------------------------------------------------
    Podría colgar de cualquiera de las tres y solo una es correcta.

    De la VIVIENDA no, porque en una casa con dos familias las personas de cada
    una son de SU hogar; mezclarlas produciría un «hogar» de nueve personas que no
    existe y que arruinaría el ingreso por persona de las dos familias.

    De la ENCUESTA tampoco, aunque parezca lo mismo que del hogar: la encuesta es
    el TRABAJO (quién la levanta, en qué estado va) y el hogar es el DATO. Colgar
    las personas del trabajo diría que son un atributo del acto de encuestar y no
    de la familia, y volvería a mezclar las dos cosas que la HU-08 separó.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 2 — un solo jefe de hogar, garantizado por la base de datos
    ----------------------------------------------------------------------
    Es la restricción más importante de esta historia, porque TODO el resto del
    formulario depende de ella: el parentesco de cada persona se mide respecto al
    jefe de hogar, así que dos jefes dejarían sin sentido la columna «parentesco»
    de todas las demás filas.

    Se resuelve con un índice único PARCIAL —único entre los que son jefe de
    hogar—, que es exactamente la misma técnica que `asignacion_activa_unica` en
    la HU-06. Allí el filtro era `WHERE activa` y aquí es
    `WHERE parentesco = 'JEFE_HOGAR'`; el problema es el mismo: hacer único un
    valor concreto de una columna sin hacer única la columna entera.

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 3 — se guarda la FECHA DE NACIMIENTO, no la edad
    ----------------------------------------------------------------------
    Guardar «34» sería más simple y estaría mal a los pocos meses. Una edad es un
    dato que caduca; una fecha de nacimiento no. Con la fecha, la edad se calcula
    siempre respecto a la fecha que interese —hoy, o el día del operativo— y el
    histórico del censo sigue siendo cierto años después.

    Es la misma razón por la que Operativo guarda fechas y no «duración en días».

    ----------------------------------------------------------------------
    DECISIÓN DE DISEÑO 4 — escolaridad y ocupación dependen de la EDAD
    ----------------------------------------------------------------------
    No se le pregunta el nivel educacional a una guagua ni la situación
    ocupacional a un niño de siete años. Los dos campos admiten vacío en la
    columna y el formulario los exige solo a partir de cierta edad (ver
    IntegranteForm), lo que evita dos errores opuestos: pedir un dato que no
    existe, y dejar sin dato a media población adulta porque el campo era
    opcional para todos.
    """

    #: Desde qué edad tiene sentido preguntar por estudios (educación parvularia).
    EDAD_ESCOLARIDAD = 5

    #: Desde qué edad tiene sentido preguntar por ocupación (edad mínima legal
    #: para trabajar en Chile con autorización, Código del Trabajo art. 13).
    EDAD_OCUPACION = 15

    grupo_familiar = models.ForeignKey(
        GrupoFamiliar,
        on_delete=models.CASCADE,
        related_name="integrantes",
        verbose_name="grupo familiar",
        help_text="Hogar al que pertenece esta persona.",
    )
    parentesco = models.CharField(
        "parentesco",
        max_length=20,
        choices=Parentesco.choices,
        help_text="Relación con el jefe o jefa de hogar.",
    )
    nombres = models.CharField(
        "nombres",
        max_length=100,
        help_text="Nombre o nombres de pila.",
    )
    apellidos = models.CharField(
        "apellidos",
        max_length=100,
        help_text="Apellidos de la persona.",
    )
    rut = models.CharField(
        "RUT",
        max_length=12,
        blank=True,
        validators=[validar_rut],
        help_text="Formato 12345678-9. Opcional, igual que el del jefe de hogar.",
    )
    sexo = models.CharField(
        "sexo",
        max_length=20,
        choices=Sexo.choices,
        help_text="Tal como la persona lo declara.",
    )
    fecha_nacimiento = models.DateField(
        "fecha de nacimiento",
        help_text="Se guarda la fecha y no la edad: la edad caduca y la fecha no.",
    )
    nivel_educacional = models.CharField(
        "nivel educacional",
        max_length=20,
        choices=NivelEducacional.choices,
        blank=True,
        help_text=f"Se pregunta desde los {EDAD_ESCOLARIDAD} años.",
    )
    situacion_ocupacional = models.CharField(
        "situación ocupacional",
        max_length=20,
        choices=SituacionOcupacional.choices,
        blank=True,
        help_text=f"Se pregunta desde los {EDAD_OCUPACION} años.",
    )
    pueblo_originario = models.CharField(
        "pueblo originario",
        max_length=20,
        choices=PuebloOriginario.choices,
        default=PuebloOriginario.NINGUNO,
        help_text="Dato autodeclarado por la persona.",
    )
    tiene_discapacidad = models.BooleanField(
        "presenta discapacidad",
        default=False,
        help_text="Alguna condición de discapacidad permanente declarada.",
    )
    observaciones = models.TextField(
        "observaciones",
        blank=True,
        help_text="Situaciones de esta persona que conviene dejar por escrito.",
    )
    registrado_en = models.DateTimeField("registrado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "fichas_integrante"
        verbose_name = "integrante"
        verbose_name_plural = "integrantes"
        # De mayor a menor edad, que es como una familia se enumera a sí misma.
        #
        # El jefe de hogar NO puede ir primero desde aquí: ordenar por la columna
        # `parentesco` daría el orden alfabético de sus códigos, que no significa
        # nada («CONYUGE» antes que «JEFE_HOGAR» y «HIJO» después). Poner al jefe
        # delante exige un CASE de SQL, y eso vive en
        # GrupoFamiliar.integrantes_ordenados(), que es quien conoce el criterio.
        ordering = ["fecha_nacimiento"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(parentesco__in=Parentesco.values),
                name="integrante_parentesco_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(sexo__in=Sexo.values),
                name="integrante_sexo_valido",
            ),
            # Índice único PARCIAL: un solo jefe de hogar por hogar (decisión 2).
            models.UniqueConstraint(
                fields=["grupo_familiar"],
                condition=models.Q(parentesco="JEFE_HOGAR"),
                name="un_solo_jefe_por_hogar",
            ),
            # La misma persona no puede estar dos veces en el mismo hogar. Es
            # parcial porque el RUT es opcional: sin la condición, dos personas sin
            # RUT chocarían entre sí por tener las dos la cadena vacía, y el
            # sistema impediría registrar a una familia que no lleva los carnets
            # encima.
            models.UniqueConstraint(
                fields=["grupo_familiar", "rut"],
                condition=~models.Q(rut=""),
                name="rut_unico_en_el_hogar",
            ),
        ]
        indexes = [
            models.Index(
                fields=["grupo_familiar", "parentesco"], name="idx_integrante_hogar"
            ),
        ]

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def es_jefe_hogar(self):
        return self.parentesco == Parentesco.JEFE_HOGAR

    def edad(self, a_fecha=None):
        """Años cumplidos a la fecha indicada (hoy por defecto).

        La resta de años se corrige comparando (mes, día): sin eso, alguien nacido
        el 30 de diciembre aparecería con un año de más durante casi todo el año
        anterior a su cumpleaños. Es el típico cálculo que parece trivial y se
        escribe mal una vez por proyecto, y por eso está aquí y no repartido.
        """
        if self.fecha_nacimiento is None:
            return None

        referencia = a_fecha or timezone.localdate()

        return (
            referencia.year
            - self.fecha_nacimiento.year
            - (
                (referencia.month, referencia.day)
                < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
            )
        )

    @property
    def es_menor_de_edad(self):
        edad = self.edad()
        return edad is not None and edad < 18

    @property
    def se_le_pregunta_escolaridad(self):
        edad = self.edad()
        return edad is not None and edad >= self.EDAD_ESCOLARIDAD

    @property
    def se_le_pregunta_ocupacion(self):
        edad = self.edad()
        return edad is not None and edad >= self.EDAD_OCUPACION

    def save(self, *args, **kwargs):
        """Normaliza el RUT antes de escribir, igual que GrupoFamiliar y Usuario."""
        self.rut = limpiar_rut(self.rut) or ""
        super().save(*args, **kwargs)

    def clean(self):
        """Coherencia de la persona: fechas imposibles y datos fuera de edad.

        Igual que en Encuesta.clean(), esto duplica en Python lo que en parte ya
        garantizan las restricciones: la restricción protege el DATO y la
        validación protege a la PERSONA que está rellenando el formulario.

        Lo que aquí se comprueba NO puede estar en un CheckConstraint, y por eso es
        el único sitio donde vive: una restricción de la base de datos no puede
        depender de la fecha de hoy sin volverse falsa mañana.
        """
        super().clean()

        if self.fecha_nacimiento:
            hoy = timezone.localdate()

            if self.fecha_nacimiento > hoy:
                raise ValidationError(
                    {"fecha_nacimiento": "La fecha de nacimiento no puede ser futura."}
                )

            if self.edad() > 120:
                raise ValidationError(
                    {
                        "fecha_nacimiento": (
                            "Esa fecha implica más de 120 años. Revisa el año: casi "
                            "siempre es un dígito equivocado."
                        )
                    }
                )


# ==========================================================================
