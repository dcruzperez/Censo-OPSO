"""Formularios de la organización territorial (HU-05).

Todos son ModelForm por la misma razón que en la HU-03: el modelo ya declara los
tipos, las etiquetas, los textos de ayuda y las restricciones de unicidad, y un
ModelForm los DERIVA de ahí. Así la regla se escribe una vez y es imposible que
el formulario y la base de datos se contradigan.

QUÉ VALIDA CADA CAPA, Y POR QUÉ HAY TRES

  1. El MODELO (constraints e índices) -> lo garantiza PostgreSQL. Vale incluso
     para un script que no pase por aquí.
  2. El MODELO (clean) -> reglas que necesitan varios campos, como que un
     operativo no termine antes de empezar. Valen también en /admin/.
  3. El FORMULARIO (este archivo) -> reglas que necesitan el CONTEXTO de la
     petición: qué operativo se está editando, si está cerrado, si el nombre ya
     existe en ESA comuna. Y, sobre todo, los mensajes: aquí es donde el error se
     convierte en una frase que le dice al administrador qué corregir.

Las tres capas no son redundancia: la primera protege los datos, la segunda las
reglas y la tercera la experiencia de uso.
"""

from django import forms
from django.db.models import Q

from .models import Comuna, EstadoOperativo, Operativo, Region, Sector, Zona

# Clases de Bootstrap, iguales que en la HU-03 para que las pantallas nuevas se
# vean como las que ya existen.
CLASE_TEXTO = "form-control"
CLASE_SELECT = "form-select"
CLASE_AREA = "form-control"


class CampoComuna(forms.ModelChoiceField):
    """Selector de comuna que muestra la región y avisa si está desactivada.

    Mismo recurso que CampoRol en la HU-03: al redefinir label_from_instance, el
    desplegable dice «Concepción (Región del Biobío)» en vez de «Concepción».

    Importa porque en Chile hay comunas homónimas en regiones distintas, y
    elegir la equivocada no da ningún error: crea un sector perfectamente válido
    en el lugar equivocado, y eso solo se descubre cuando un censista llega a
    500 km de donde debía.
    """

    def label_from_instance(self, obj):
        etiqueta = obj.nombre_completo
        return etiqueta if obj.activa else f"{etiqueta} — desactivada"


# ==========================================================================
# COMUNA
# ==========================================================================


class ComunaForm(forms.ModelForm):
    """Alta y edición de una comuna.

    El campo `activa` NO está aquí a propósito: se cambia desde la pantalla de
    confirmación, con POST y explicando las consecuencias, igual que el estado de
    una cuenta en la HU-03. Mezclarlo con la edición de datos permitiría
    desactivar una comuna sin querer al corregirle una tilde al nombre.
    """

    region = forms.ModelChoiceField(
        label="Región",
        queryset=Region.objects.all(),
        empty_label="— Selecciona una región —",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
        help_text="Las 16 regiones de Chile. No se pueden crear ni editar.",
    )

    class Meta:
        model = Comuna
        fields = ("region", "nombre")
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Ej.: Concepción",
                    "autocomplete": "off",
                }
            ),
        }

    def clean_nombre(self):
        """Quita espacios sobrantes.

        Sin esto, «Concepción» y «Concepción » serían dos comunas distintas para
        la restricción de unicidad, porque para PostgreSQL son dos cadenas
        distintas. El administrador no vería la diferencia y tendría dos filas
        para el mismo lugar.
        """
        return (self.cleaned_data.get("nombre") or "").strip()

    def clean(self):
        """Comprueba el duplicado ANTES de que lo haga la base de datos.

        La restricción comuna_unica_por_region ya lo impide, pero si se dejara
        solo a PostgreSQL el resultado sería un IntegrityError: una página de
        error 500, no un mensaje. Comprobándolo aquí, el administrador recibe
        «Ya existe una comuna llamada Concepción en esa región» junto al campo.

        La restricción de la base de datos se conserva igualmente: es la que
        protege de un script que no pase por este formulario, y la que resuelve
        el caso en que dos administradores guarden el mismo nombre a la vez.
        """
        limpios = super().clean()
        region = limpios.get("region")
        nombre = limpios.get("nombre")

        if region and nombre:
            duplicadas = Comuna.objects.filter(region=region, nombre__iexact=nombre)
            # Al EDITAR hay que excluirse a sí misma, o una comuna nunca podría
            # guardarse sin cambiarle el nombre.
            if self.instance.pk:
                duplicadas = duplicadas.exclude(pk=self.instance.pk)

            if duplicadas.exists():
                self.add_error(
                    "nombre",
                    f"Ya existe una comuna llamada «{nombre}» en "
                    f"{region.nombre}. Los nombres no se repiten dentro de una "
                    "misma región.",
                )

        return limpios


# ==========================================================================
# OPERATIVO
# ==========================================================================


class OperativoForm(forms.ModelForm):
    """Alta y edición de un operativo.

    El `estado` no se edita aquí, por la misma razón que `activa` en ComunaForm:
    cambiar de "en planificación" a "cerrado" no es editar un dato, es una
    decisión con consecuencias (un operativo cerrado ya no admite cambios de
    territorio). Va por su propia pantalla de confirmación.
    """

    class Meta:
        model = Operativo
        fields = ("nombre", "descripcion", "fecha_inicio", "fecha_termino")
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Ej.: Censo Social 2026",
                    "autocomplete": "off",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": CLASE_AREA,
                    "rows": 3,
                    "placeholder": "Objetivo del operativo y antecedentes útiles.",
                }
            ),
            # type="date" hace que el navegador muestre su propio calendario. Es
            # el único "componente de interfaz" del módulo y no cuesta una línea
            # de JavaScript: lo trae HTML5. Además obliga al formato ISO, así que
            # desaparece la ambigüedad entre 03-04 y 04-03.
            "fecha_inicio": forms.DateInput(
                attrs={"class": CLASE_TEXTO, "type": "date"},
                format="%Y-%m-%d",
            ),
            "fecha_termino": forms.DateInput(
                attrs={"class": CLASE_TEXTO, "type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def clean_nombre(self):
        return (self.cleaned_data.get("nombre") or "").strip()

    def clean(self):
        """Coherencia de las fechas, con el mensaje puesto en el campo correcto.

        Operativo.clean() ya comprueba lo mismo y seguirá haciéndolo en /admin/.
        Se repite aquí por una razón práctica: cuando la validación vive solo en
        el modelo, Django coloca el error como error GENERAL del formulario y la
        plantilla lo muestra arriba, lejos del campo. Comprobándolo también aquí,
        el mensaje sale debajo de «fecha de término», que es donde el
        administrador está mirando.
        """
        limpios = super().clean()
        inicio = limpios.get("fecha_inicio")
        termino = limpios.get("fecha_termino")

        if inicio and termino and termino < inicio:
            self.add_error(
                "fecha_termino",
                "La fecha de término no puede ser anterior a la de inicio.",
            )

        return limpios


class CambiarEstadoOperativoForm(forms.Form):
    """Elige el nuevo estado de un operativo, ofreciendo solo transiciones válidas.

    ¿POR QUÉ UN FORMULARIO Y NO TRES BOTONES?

    Porque los estados no son independientes: desde "en planificación" tiene
    sentido pasar a "en curso" o directamente a "cerrado", pero de "cerrado" no
    se vuelve a "en curso" sin una decisión consciente. Un formulario que calcula
    las opciones válidas concentra esa regla en un solo lugar; tres botones la
    repartirían entre la plantilla (qué botón mostrar) y la vista (qué aceptar),
    que es exactamente como se produce la incoherencia de que la interfaz oculte
    algo que la vista sí acepta.
    """

    #: Desde cada estado, a cuáles se puede ir.
    TRANSICIONES = {
        EstadoOperativo.PLANIFICACION: (
            EstadoOperativo.EN_CURSO,
            EstadoOperativo.CERRADO,
        ),
        EstadoOperativo.EN_CURSO: (
            EstadoOperativo.CERRADO,
            # Volver a planificación es legítimo: un operativo que se inició por
            # error o que se posterga debe poder retroceder.
            EstadoOperativo.PLANIFICACION,
        ),
        # Reabrir un operativo cerrado se permite, pero solo a "en curso": no
        # tendría sentido devolver a planificación algo donde ya se trabajó.
        EstadoOperativo.CERRADO: (EstadoOperativo.EN_CURSO,),
    }

    estado = forms.ChoiceField(
        label="Nuevo estado",
        choices=(),  # se calculan en __init__ según el estado actual
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    motivo = forms.CharField(
        label="Motivo del cambio",
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Opcional: por qué se cambia el estado",
                "autocomplete": "off",
            }
        ),
        help_text=(
            "Queda guardado en la bitácora de auditoría junto al cambio. "
            "Ayuda a entender, meses después, por qué se cerró o se reabrió."
        ),
    )

    def __init__(self, *args, operativo, **kwargs):
        """operativo es obligatorio y va por nombre.

        Se exige como argumento de palabra clave (después de *) para que ninguna
        llamada pueda pasarlo por posición y confundirlo con `data`. Sin
        operativo el formulario no puede calcular las transiciones válidas, así
        que es mejor que falle al construirse que ofrecer opciones inventadas.
        """
        self.operativo = operativo
        super().__init__(*args, **kwargs)

        destinos = self.TRANSICIONES.get(operativo.estado, ())
        self.fields["estado"].choices = [
            (valor, EstadoOperativo(valor).label) for valor in destinos
        ]

    def clean_estado(self):
        """Segunda comprobación de la transición, contra una petición manipulada.

        ChoiceField ya rechaza un valor que no esté en `choices`, y `choices` se
        calculó en __init__. Se vuelve a comprobar contra TRANSICIONES por
        prudencia: si alguien cambiara __init__ y las opciones dejaran de
        recalcularse, esta comprobación seguiría cerrando el paso. Es la misma
        idea que tener la restricción en la base de datos además del formulario.
        """
        estado = self.cleaned_data["estado"]

        if estado not in self.TRANSICIONES.get(self.operativo.estado, ()):
            raise forms.ValidationError(
                f"No se puede pasar de «{self.operativo.get_estado_display()}» "
                f"a «{EstadoOperativo(estado).label}»."
            )

        return estado


# ==========================================================================
# SECTOR
# ==========================================================================


class SectorForm(forms.ModelForm):
    """Alta y edición de un sector dentro de un operativo.

    El operativo NO es un campo del formulario: viene de la URL
    (/operativos/<pk>/sectores/nuevo/). Es una decisión de seguridad y de
    usabilidad a la vez.

    De seguridad: un campo oculto con el identificador del operativo se puede
    manipular, y crearía sectores en un operativo que el administrador no estaba
    mirando. Tomándolo de la URL, la vista lo carga con get_object_or_404 y
    comprueba su estado antes de aceptar nada.

    De usabilidad: quien está dentro de un operativo ya eligió el operativo. Un
    desplegable para volver a elegirlo es un paso de más y una oportunidad de
    equivocarse.
    """

    comuna = CampoComuna(
        label="Comuna",
        queryset=Comuna.objects.none(),  # se ajusta en __init__
        empty_label="— Selecciona una comuna —",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
        help_text="Solo se ofrecen las comunas activas.",
    )

    class Meta:
        model = Sector
        fields = ("comuna", "nombre", "descripcion")
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Ej.: Los Boldos",
                    "autocomplete": "off",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": CLASE_AREA,
                    "rows": 2,
                    "placeholder": "Límites o referencias para reconocerlo en terreno.",
                }
            ),
        }

    def __init__(self, *args, operativo, **kwargs):
        self.operativo = operativo
        super().__init__(*args, **kwargs)

        # Solo comunas ACTIVAS... más la que este sector ya tiene.
        #
        # El detalle importa: si un sector se creó en una comuna que después se
        # desactivó, al editarle el nombre el desplegable no incluiría su propia
        # comuna, el campo quedaría inválido y sería IMPOSIBLE guardar el sector.
        # Incluir la actual mantiene la edición posible sin obligar a reactivar
        # una comuna que ya no se usa.
        disponibles = Q(activa=True)
        if self.instance.pk and self.instance.comuna_id:
            disponibles |= Q(pk=self.instance.comuna_id)

        self.fields["comuna"].queryset = (
            Comuna.objects.filter(disponibles)
            .select_related("region")
            .order_by("region__orden", "nombre")
        )

    def clean_nombre(self):
        return (self.cleaned_data.get("nombre") or "").strip()

    def clean(self):
        """Duplicado dentro del mismo operativo y la misma comuna.

        Nótese qué NO se comprueba: que el nombre sea único en todo el sistema.
        Dos operativos pueden tener un sector «Los Boldos» —son divisiones del
        mismo lugar hechas en momentos distintos— y eso es correcto. La
        restricción es la terna (operativo, comuna, nombre), no el nombre.
        """
        limpios = super().clean()
        comuna = limpios.get("comuna")
        nombre = limpios.get("nombre")

        if comuna and nombre:
            duplicados = Sector.objects.filter(
                operativo=self.operativo, comuna=comuna, nombre__iexact=nombre
            )
            if self.instance.pk:
                duplicados = duplicados.exclude(pk=self.instance.pk)

            if duplicados.exists():
                self.add_error(
                    "nombre",
                    f"El operativo ya tiene un sector «{nombre}» en "
                    f"{comuna.nombre}.",
                )

        return limpios

    def save(self, commit=True):
        """Fija el operativo tomado de la URL, no de los datos enviados."""
        sector = super().save(commit=False)
        sector.operativo = self.operativo
        if commit:
            sector.save()
        return sector


# ==========================================================================
# ZONA
# ==========================================================================


class ZonaForm(forms.ModelForm):
    """Alta y edición de una zona dentro de un sector.

    Mismo criterio que SectorForm: el sector viene de la URL, no del formulario.
    """

    class Meta:
        model = Zona
        fields = ("nombre", "descripcion", "viviendas_estimadas")
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Ej.: Zona 1 o Manzanas 1-8",
                    "autocomplete": "off",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": CLASE_AREA,
                    "rows": 2,
                    "placeholder": "Calles, manzanas o límites que definen la zona.",
                }
            ),
            "viviendas_estimadas": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "min": 0, "placeholder": "Opcional"}
            ),
        }

    def __init__(self, *args, sector, **kwargs):
        self.sector = sector
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        return (self.cleaned_data.get("nombre") or "").strip()

    def clean_viviendas_estimadas(self):
        """Rechaza el cero además de los negativos.

        PositiveIntegerField ya impide los negativos, pero acepta 0. Una zona con
        cero viviendas estimadas no es un dato, es un error de tipeo: si no se
        sabe cuántas hay, el campo se deja vacío (es opcional), que es distinto
        de afirmar que no hay ninguna.
        """
        viviendas = self.cleaned_data.get("viviendas_estimadas")

        if viviendas is not None and viviendas == 0:
            raise forms.ValidationError(
                "Si no conoces el número de viviendas, deja el campo vacío en "
                "vez de escribir 0."
            )

        return viviendas

    def clean(self):
        limpios = super().clean()
        nombre = limpios.get("nombre")

        if nombre:
            duplicadas = Zona.objects.filter(sector=self.sector, nombre__iexact=nombre)
            if self.instance.pk:
                duplicadas = duplicadas.exclude(pk=self.instance.pk)

            if duplicadas.exists():
                self.add_error(
                    "nombre",
                    f"El sector «{self.sector.nombre}» ya tiene una zona "
                    f"llamada «{nombre}».",
                )

        return limpios

    def save(self, commit=True):
        zona = super().save(commit=False)
        zona.sector = self.sector
        if commit:
            zona.save()
        return zona


# ==========================================================================
# FILTROS DE LOS LISTADOS
# ==========================================================================


class FiltroOperativosForm(forms.Form):
    """Búsqueda y filtro del listado de operativos.

    Form y no ModelForm: no crea ni modifica nada, solo limpia lo que llega por
    la URL. Mismo razonamiento que FiltroUsuariosForm en la HU-03: si alguien
    escribe ?estado=abc a mano, el campo lo descarta y el listado no filtra, en
    vez de fallar al consultar.
    """

    ESTADOS = (("", "Todos los estados"),) + tuple(EstadoOperativo.choices)

    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Nombre del operativo",
                "autocomplete": "off",
            }
        ),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=ESTADOS,
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()


class FiltroComunasForm(forms.Form):
    """Búsqueda y filtro del listado de comunas."""

    ESTADOS = (
        ("", "Todas"),
        ("activas", "Solo activas"),
        ("inactivas", "Solo desactivadas"),
    )

    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Nombre de la comuna",
                "autocomplete": "off",
            }
        ),
    )
    region = forms.ModelChoiceField(
        label="Región",
        required=False,
        queryset=Region.objects.all(),
        empty_label="Todas las regiones",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=ESTADOS,
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()
