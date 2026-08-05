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
