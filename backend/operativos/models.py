"""Modelos de la app "operativos" (HU-05).

Cinco tablas que responden a una sola pregunta: ¿DÓNDE se trabaja?

  1. operativos_region     -> las 16 regiones de Chile (catálogo sembrado)
  2. operativos_comuna     -> comunas donde OPSO puede operar
  3. operativos_operativo  -> el despliegue concreto, con sus fechas
  4. operativos_sector     -> división de una comuna dentro de un operativo
  5. operativos_zona       -> división de un sector; la unidad más pequeña

LA JERARQUÍA, Y POR QUÉ SE PARTE EN DOS MITADES

    Region ──< Comuna                GEOGRAFÍA: existe con o sin OPSO
                  │
    Operativo ──< Sector ──< Zona    ORGANIZACIÓN: existe porque hay un operativo

Arriba está la geografía de Chile: la Región del Biobío y la comuna de
Concepción existen independientemente de que se haga un censo. Son datos
estables, y por eso se guardan una sola vez y se reutilizan en todos los
operativos.

Abajo está la organización del trabajo: "Los Boldos" no es una entidad
geográfica oficial, es un pedazo de Concepción que ESTE operativo decidió tratar
como una unidad. El siguiente operativo puede dividir la misma comuna de otra
forma, y debe poder hacerlo sin alterar los datos del anterior.

Esa es la razón por la que Sector cuelga de Operativo y no solo de Comuna: si
los sectores fueran geografía permanente, redividir la comuna en el operativo de
2027 reescribiría la división con la que se levantaron las fichas de 2026, y el
histórico quedaría mintiendo sobre dónde trabajó cada censista.

CONTINUIDAD CON LAS HISTORIAS ANTERIORES

Esta historia no reimplementa nada. Reutiliza:
  - los permisos "operativos.ver" y "operativos.gestionar", ya sembrados por la
    migración 0005 de la HU-04, sin agregar ni una fila al catálogo;
  - PermisoRequeridoMixin de la HU-04 para proteger las vistas;
  - RegistroAuditoria de la HU-03 para la bitácora, extendido con un objeto
    afectado territorial (ver la migración usuarios/0006).

Lo nuevo es únicamente el modelo territorial y su interfaz de administración.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


# ==========================================================================
# 1. GEOGRAFÍA: REGIÓN Y COMUNA
# ==========================================================================


class Region(models.Model):
    """Una de las 16 regiones de Chile. Catálogo de solo lectura.

    DECISIÓN DE DISEÑO: es una TABLA sembrada por migración, no un campo de
    opciones (TextChoices) ni texto libre.

    ¿Por qué no TextChoices, como se hizo con RolCodigo o ModuloPermiso?
    Porque aquellos son valores que el CÓDIGO consulta: hay un `if` que pregunta
    si el rol es ADMINISTRADOR. Aquí no: ninguna regla de negocio de OPSO
    depende de que una región sea la del Biobío. La región es un DATO que el
    usuario elige en un desplegable, y los datos van en tablas.

    ¿Por qué no texto libre dentro de Comuna?
    Porque "Biobío", "Bío-Bío", "BIOBIO" y "VIII Región" son la misma región
    escrita de cuatro formas. Con texto libre, agrupar las comunas por región
    —que es justamente lo que hace útil el listado— dejaría de funcionar en
    cuanto dos personas la escribieran distinto. La clave foránea lo hace
    imposible: solo se puede elegir una de las 16 filas.

    ¿Por qué NO tiene CRUD?
    Porque las regiones de Chile no las administra un usuario de OPSO: las
    define la ley. Ofrecer un botón "crear región" invitaría a inventar una, y
    eso solo puede ensuciar los datos. Se siembran por migración y se consultan.
    Si el Estado creara una región nueva, se agrega con una migración de datos,
    que es la forma correcta de versionar un cambio legal: queda en Git, con
    fecha y autor.
    """

    codigo = models.CharField(
        "código",
        max_length=5,
        unique=True,
        help_text=(
            "Código oficial de la región según el Instituto Nacional de "
            "Estadísticas (ej.: 08 para el Biobío)."
        ),
    )
    nombre = models.CharField(
        "nombre",
        max_length=80,
        unique=True,
        help_text="Nombre oficial de la región.",
    )
    orden = models.PositiveSmallIntegerField(
        "orden",
        default=100,
        help_text=(
            "Posición en el listado. Se usa el orden geográfico de norte a sur, "
            "que es como se nombran las regiones en Chile, en vez del "
            "alfabético."
        ),
    )

    class Meta:
        db_table = "operativos_region"
        verbose_name = "región"
        verbose_name_plural = "regiones"
        # Norte a sur, no alfabético: es el orden en que cualquier persona en
        # Chile espera ver una lista de regiones.
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Comuna(models.Model):
    """Comuna donde OPSO puede desplegar un operativo.

    ¿POR QUÉ ESTA SÍ LA ADMINISTRA EL USUARIO, Y LA REGIÓN NO?

    Porque la lista no cumple la misma función. Las 16 regiones son pocas y
    sirven para agrupar; las 346 comunas de Chile son muchas y OPSO trabaja en
    un puñado. Sembrarlas todas obligaría al administrador a buscar entre 346
    opciones las 4 que le interesan, y a los reportes a mostrar 342 comunas
    vacías. Dar de alta solo las comunas donde se trabaja mantiene la lista
    corta y significativa: "estas son las comunas de OPSO".

    NO SE BORRAN, SE DESACTIVAN. Es la misma decisión de la HU-03 con las
    cuentas de usuario, por la misma razón: una comuna puede tener sectores, y
    esos sectores fichas de familias. Borrarla arrastraría el histórico del
    censo. Desactivarla la saca de los desplegables sin tocar un solo dato ya
    levantado.
    """

    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="comunas",
        verbose_name="región",
        help_text="Región a la que pertenece la comuna.",
    )
    nombre = models.CharField(
        "nombre",
        max_length=100,
        help_text="Nombre de la comuna, tal como se escribe oficialmente.",
    )
    activa = models.BooleanField(
        "activa",
        default=True,
        help_text=(
            "Si se desactiva, deja de ofrecerse al crear sectores nuevos. "
            "Los sectores que ya existen no se modifican."
        ),
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "operativos_comuna"
        verbose_name = "comuna"
        verbose_name_plural = "comunas"
        ordering = ["region__orden", "nombre"]
        constraints = [
            # No puede haber dos comunas con el mismo nombre en la MISMA región.
            #
            # ¿Por qué no unique=True sobre el nombre a secas? Porque en Chile
            # hay nombres de comuna repetidos en regiones distintas. El par
            # (región, nombre) sí es único, y es la restricción correcta.
            models.UniqueConstraint(
                fields=["region", "nombre"],
                name="comuna_unica_por_region",
            ),
        ]
        indexes = [
            # El listado filtra casi siempre por "solo las activas".
            models.Index(fields=["activa", "nombre"], name="idx_comuna_activa"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def nombre_completo(self):
        """«Concepción (Región del Biobío)», para desplegables y bitácora.

        Existe porque el nombre solo puede ser ambiguo: hay comunas homónimas en
        regiones distintas. En un desplegable donde el administrador elige dónde
        crear un sector, esa ambigüedad lleva a equivocarse de comuna.
        """
        return f"{self.nombre} ({self.region.nombre})"

    def total_sectores(self):
        return self.sectores.count()

    def puede_desactivarse(self):
        """¿Se puede desactivar esta comuna? Devuelve (True, "") o (False, motivo).

        Se responde con un motivo y no con un simple booleano para que la vista
        pueda EXPLICAR el rechazo: "no se puede porque tiene 3 sectores en el
        operativo Censo 2026" es accionable; "no se puede" obliga a adivinar.

        La regla: una comuna con sectores en operativos que aún no están
        cerrados no debe desactivarse, porque hay trabajo de terreno vivo
        apuntando a ella. Si todos sus operativos están cerrados, la comuna ya
        no se usa y desactivarla es exactamente lo correcto.
        """
        vigentes = self.sectores.filter(
            operativo__estado__in=(
                EstadoOperativo.PLANIFICACION,
                EstadoOperativo.EN_CURSO,
            )
        ).count()

        if vigentes:
            return False, (
                f"La comuna tiene {vigentes} sector"
                f"{'es' if vigentes != 1 else ''} en operativos que aún no "
                "están cerrados. Cierra esos operativos o mueve los sectores "
                "antes de desactivarla."
            )
        return True, ""


# ==========================================================================
# 2. EL OPERATIVO
# ==========================================================================


class EstadoOperativo(models.TextChoices):
    """Ciclo de vida de un operativo.

    Son TextChoices y no una tabla, al contrario que Rol o Region. La diferencia
    es la misma que se explicó en Region, aplicada al revés: el CÓDIGO sí
    consulta estos valores. Hay reglas que preguntan si un operativo está
    cerrado para decidir si se puede editar su territorio. Un valor que el
    código compara debe ser una constante, no una fila que alguien pueda
    renombrar y romper el `if`.

    Los tres estados no son decorativos, cada uno habilita cosas distintas:

      PLANIFICACIÓN -> se arma la división territorial. Todavía no hay terreno.
      EN CURSO      -> hay censistas trabajando. El territorio ya no debería
                       moverse sin buenas razones.
      CERRADO       -> terminó. Es solo histórico: no se agrega ni se modifica.
    """

    PLANIFICACION = "PLANIFICACION", "En planificación"
    EN_CURSO = "EN_CURSO", "En curso"
    CERRADO = "CERRADO", "Cerrado"


class Operativo(models.Model):
    """Un despliegue concreto de levantamiento de información en terreno.

    Es lo que da sentido a la división territorial. Sin operativo, un "sector"
    sería un pedazo de mapa sin propósito; con operativo, es una porción de
    trabajo con fechas, responsable y estado.

    ¿POR QUÉ EL TERRITORIO CUELGA DEL OPERATIVO Y NO AL REVÉS?

    Porque la división del terreno es una decisión de planificación, y las
    decisiones de planificación cambian entre un operativo y el siguiente. En el
    censo de 2026 puede convenir tratar "Los Boldos" como un solo sector; en
    2027, con más censistas, partirlo en tres. Si el sector fuera geografía
    permanente, ese cambio reescribiría el pasado: las fichas levantadas en 2026
    apuntarían a una división que en 2026 no existía.

    Colgándolo del operativo, cada uno conserva su propia foto del territorio y
    los datos históricos siguen siendo verdad.
    """

    nombre = models.CharField(
        "nombre",
        max_length=120,
        unique=True,
        help_text="Cómo se identifica el operativo. Ej.: Censo Social 2026.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Objetivo del operativo y cualquier antecedente útil.",
    )
    fecha_inicio = models.DateField(
        "fecha de inicio",
        help_text="Primer día de trabajo en terreno.",
    )
    fecha_termino = models.DateField(
        "fecha de término",
        help_text="Último día previsto de trabajo en terreno.",
    )
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoOperativo.choices,
        default=EstadoOperativo.PLANIFICACION,
        db_index=True,
        help_text="En qué etapa está el operativo.",
    )
    creado_por = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operativos_creados",
        verbose_name="creado por",
        help_text="Quién dio de alta el operativo.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "operativos_operativo"
        verbose_name = "operativo"
        verbose_name_plural = "operativos"
        # El más reciente primero: es el que se está gestionando.
        ordering = ["-fecha_inicio", "nombre"]
        constraints = [
            # La base de datos también lo impide, no solo el formulario. Una
            # importación masiva o un script que no pase por el formulario no
            # puede meter un operativo que termina antes de empezar.
            models.CheckConstraint(
                condition=models.Q(fecha_termino__gte=models.F("fecha_inicio")),
                name="operativo_fechas_coherentes",
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=EstadoOperativo.values),
                name="operativo_estado_valido",
            ),
        ]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("operativos:operativo_detalle", kwargs={"pk": self.pk})

    # -- estado ------------------------------------------------------------

    @property
    def esta_cerrado(self):
        return self.estado == EstadoOperativo.CERRADO

    @property
    def admite_cambios_de_territorio(self):
        """¿Se puede agregar o modificar sectores y zonas?

        Un operativo cerrado es histórico: cambiarle el territorio falsearía la
        información con la que efectivamente se trabajó. Se permite en
        planificación y en curso (en curso, porque en terreno aparecen
        realidades que la planificación no previó: un sector más grande de lo
        pensado hay que partirlo con censistas ya trabajando).
        """
        return not self.esta_cerrado

    @property
    def duracion_dias(self):
        """Días que abarca el operativo, ambos extremos incluidos."""
        return (self.fecha_termino - self.fecha_inicio).days + 1

    @property
    def vigente(self):
        """True si hoy cae dentro de las fechas y el operativo está en curso."""
        hoy = timezone.localdate()
        return (
            self.estado == EstadoOperativo.EN_CURSO
            and self.fecha_inicio <= hoy <= self.fecha_termino
        )

    # -- territorio --------------------------------------------------------

    def total_sectores(self):
        return self.sectores.count()

    def total_zonas(self):
        return Zona.objects.filter(sector__operativo=self).count()

    def comunas_cubiertas(self):
        """Comunas distintas que este operativo toca, ordenadas.

        Se resuelve con una consulta al ORM y no recorriendo los sectores en
        Python: `distinct()` lo hace PostgreSQL, que es donde están los datos.
        """
        return (
            Comuna.objects.filter(sectores__operativo=self)
            .select_related("region")
            .distinct()
            .order_by("region__orden", "nombre")
        )

    def clean(self):
        """Validación de modelo: coherencia de las fechas.

        Se escribe AQUÍ y no solo en el formulario para que valga también cuando
        el operativo se cree desde /admin/, desde una prueba o desde un comando
        de gestión. El formulario llama a este método automáticamente
        (ModelForm._post_clean), así que la regla se escribe una vez y protege
        todos los caminos.
        """
        super().clean()

        if self.fecha_inicio and self.fecha_termino:
            if self.fecha_termino < self.fecha_inicio:
                raise ValidationError(
                    {
                        "fecha_termino": (
                            "La fecha de término no puede ser anterior a la de "
                            "inicio."
                        )
                    }
                )


# ==========================================================================
# 3. ORGANIZACIÓN DEL TERRENO: SECTOR Y ZONA
# ==========================================================================


class Sector(models.Model):
    """División de una comuna dentro de un operativo concreto.

    Es la unidad de asignación de trabajo: el permiso "operativos.asignar_sector"
    —sembrado por la HU-04 y que usará una historia futura— habla justamente de
    esto. Un sector es lo que se le encarga a un censista o a un equipo.

    DOS CLAVES FORÁNEAS, Y NINGUNA ES REDUNDANTE:

      operativo -> a qué despliegue pertenece esta división del terreno
      comuna    -> qué parte de Chile cubre

    Se podría pensar que la comuna se deduce del operativo, pero no: un operativo
    abarca VARIAS comunas. Y tampoco al revés: una comuna aparece en varios
    operativos. El sector es precisamente el cruce de ambas cosas.

    CASCADE en `operativo` y PROTECT en `comuna` no es una inconsistencia. Un
    sector no significa nada sin su operativo —es una división DE ese
    operativo—, así que si el operativo se borra, sus sectores se van con él. La
    comuna, en cambio, es geografía compartida: borrarla mientras tenga sectores
    los dejaría sin ubicación, así que PostgreSQL lo impide y la interfaz ofrece
    desactivar en vez de borrar.
    """

    operativo = models.ForeignKey(
        Operativo,
        on_delete=models.CASCADE,
        related_name="sectores",
        verbose_name="operativo",
        help_text="Operativo al que pertenece este sector.",
    )
    comuna = models.ForeignKey(
        Comuna,
        on_delete=models.PROTECT,
        related_name="sectores",
        verbose_name="comuna",
        help_text="Comuna en la que se ubica el sector.",
    )
    nombre = models.CharField(
        "nombre",
        max_length=120,
        help_text="Cómo se conoce el sector en terreno. Ej.: Los Boldos.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Límites o referencias que ayuden a reconocerlo en terreno.",
    )
    activo = models.BooleanField(
        "activo",
        default=True,
        help_text=(
            "Si se desactiva, deja de considerarse parte del operativo sin "
            "borrar sus zonas ni su historial."
        ),
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "operativos_sector"
        verbose_name = "sector"
        verbose_name_plural = "sectores"
        ordering = ["comuna__nombre", "nombre"]
        constraints = [
            # Único por (operativo, comuna, nombre). Dos operativos distintos SÍ
            # pueden tener un sector "Los Boldos": son divisiones distintas del
            # mismo lugar, hechas en momentos distintos. Lo que no tiene sentido
            # es repetirlo dentro del mismo operativo y la misma comuna.
            models.UniqueConstraint(
                fields=["operativo", "comuna", "nombre"],
                name="sector_unico_por_operativo_y_comuna",
            ),
        ]
        indexes = [
            models.Index(fields=["operativo", "activo"], name="idx_sector_operativo"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def nombre_completo(self):
        """«Los Boldos · Concepción», para bitácora y desplegables."""
        return f"{self.nombre} · {self.comuna.nombre}"

    def total_zonas(self):
        return self.zonas.count()

    def zonas_activas(self):
        return self.zonas.filter(activa=True)


class Zona(models.Model):
    """División de un sector. Es la unidad más pequeña del territorio.

    ¿POR QUÉ HACE FALTA UN TERCER NIVEL?

    Porque un sector suele ser demasiado grande para una jornada. "Los Boldos"
    puede tener 400 viviendas: no es una unidad de trabajo, es un objetivo de
    varios días. La zona parte ese sector en pedazos abarcables ("manzanas 1 a
    8"), y eso permite dos cosas que el sector solo no permite: repartir el
    trabajo entre censistas del mismo equipo y medir el avance con grano fino
    ("vamos 3 de 5 zonas" es información útil; "vamos 0 de 1 sector" no dice
    nada durante tres días).

    Se llega hasta aquí y no más: un cuarto nivel (la manzana, la vivienda) ya
    es el objeto de la ficha de familia, no de la organización del operativo.
    """

    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="zonas",
        verbose_name="sector",
        help_text="Sector que esta zona subdivide.",
    )
    nombre = models.CharField(
        "nombre",
        max_length=120,
        help_text="Identificación de la zona. Ej.: Zona 1 o Manzanas 1-8.",
    )
    descripcion = models.TextField(
        "descripción",
        blank=True,
        help_text="Calles, manzanas o límites que definen la zona.",
    )
    viviendas_estimadas = models.PositiveIntegerField(
        "viviendas estimadas",
        null=True,
        blank=True,
        help_text=(
            "Cuántas viviendas se espera encontrar. Sirve para repartir la "
            "carga de trabajo de forma parecida entre censistas. Opcional: "
            "muchas veces no se sabe hasta llegar."
        ),
    )
    activa = models.BooleanField(
        "activa",
        default=True,
        help_text="Si se desactiva, deja de contarse en el avance del sector.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        db_table = "operativos_zona"
        verbose_name = "zona"
        verbose_name_plural = "zonas"
        ordering = ["sector__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "nombre"],
                name="zona_unica_por_sector",
            ),
        ]
        indexes = [
            models.Index(fields=["sector", "activa"], name="idx_zona_sector"),
        ]

    def __str__(self):
        return self.nombre

    @property
    def nombre_completo(self):
        """«Zona 1 · Los Boldos · Concepción», para la bitácora.

        La bitácora necesita el camino completo: "Zona 1" a secas no identifica
        nada, porque casi todos los sectores tienen una "Zona 1".
        """
        return f"{self.nombre} · {self.sector.nombre} · {self.sector.comuna.nombre}"

    @property
    def operativo(self):
        """Atajo al operativo, dos niveles arriba.

        Las vistas comprueban `zona.operativo.admite_cambios_de_territorio`
        constantemente. Sin esta propiedad, cada llamada escribiría
        `zona.sector.operativo`, y ese encadenamiento es justo el tipo de detalle
        que se copia mal.
        """
        return self.sector.operativo
