"""Formularios de la app "fichas" (HU-07 a HU-14).

Once formularios, y no hacen lo mismo:

    FiltroMisEncuestasForm -> limpia lo que llega por la URL (HU-07, consulta)
    ViviendaForm           -> da de alta o corrige una vivienda  (HU-08)
    GrupoFamiliarForm      -> registra el hogar de una encuesta  (HU-08)
    IntegranteForm         -> registra a una persona del hogar   (HU-09)
    BorradorForm           -> la nota de «por dónde iba»          (HU-10)
    CerrarSinDatosForm     -> cierra una encuesta que no se pudo  (HU-10)
    UbicacionForm          -> el punto GPS de la vivienda         (HU-11)
    FotografiaForm         -> una foto como evidencia             (HU-12)
    FiltroRevisionForm     -> la bandeja del supervisor           (HU-13)
    ValidarEncuestaForm    -> aprobar una encuesta                (HU-14)
    AnularEncuestaForm     -> descartar una que no sirve          (HU-14)

El de filtros se escribe como formulario de Django, y no leyendo request.GET a
mano en la vista, por lo mismo que los filtros de la HU-03, la HU-05 y la HU-06:
un formulario valida y limpia lo que llega por la URL, y una URL la escribe
cualquiera. Sin él, `?estado=BORRAD0R` (con un cero) o `?sector=abc` llegarían
tal cual al ORM.

Los dos de la HU-08 son ModelForm, al contrario que los de la HU-04 y la HU-06,
que eran Form «a mano». La diferencia no es de gusto: aquellos editaban un
CONJUNTO (los permisos de un rol, el equipo de un sector) y no un objeto, así que
un ModelForm no aportaba nada. Estos sí editan un objeto y uno solo, y entonces
el ModelForm regala la validación de cada campo, los mensajes de error y la
coherencia con las restricciones del modelo.

--------------------------------------------------------------------------
DÓNDE VIVE LA REGLA MÁS IMPORTANTE DE LA HU-08
--------------------------------------------------------------------------
«Un encuestador solo registra viviendas en el territorio que le asignaron» se
comprueba AQUÍ, en el queryset del campo `zona`, y no solo en la vista. Es la
misma técnica con la que la HU-06 hizo imposible asignar a alguien que no está en
la lista de disponibles: si la opción no existe en el formulario, enviarla a mano
no la hace válida.
"""

from django import forms
from django.conf import settings
from django.utils import timezone

from operativos.models import EstadoOperativo, Operativo, Sector, Zona
from usuarios.models import Usuario
from usuarios.validators import limpiar_rut

from .models import (
    ESTADOS_SIN_LEVANTAR,
    Encuesta,
    EstadoEncuesta,
    Fotografia,
    GrupoFamiliar,
    Integrante,
    Parentesco,
    Vivienda,
)

CLASE_TEXTO = "form-control"
CLASE_SELECT = "form-select"


def zonas_disponibles(censista):
    """Zonas donde esta persona puede registrar viviendas hoy.

    ES LA REGLA DE NEGOCIO CENTRAL DE LA HU-08, y por eso se escribe UNA vez, en
    una función del módulo, y la usan el formulario (para armar el desplegable) y
    las vistas (para comprobar el POST). Si cada uno la escribiera por su cuenta,
    bastaría con que una de las dos copias se quedara atrás para abrir un agujero.

    Cuatro condiciones, y cada una viene de una historia anterior:

      1. La zona pertenece a un sector ASIGNADO a esta persona y con la asignación
         VIGENTE (HU-06). Es lo que convierte el reparto del supervisor en una
         regla de seguridad y no solo en una lista informativa.
      2. El operativo NO está cerrado (HU-05). Un operativo cerrado es histórico:
         agregarle viviendas falsearía el registro de lo que se hizo.
      3. El sector está ACTIVO (HU-05). Un sector desactivado quedó fuera del
         territorio vigente.
      4. La zona está ACTIVA (HU-05). Una zona desactivada no se cuenta en el
         avance, así que registrar en ella sería trabajo que no suma.

    Un administrador o un supervisor no tienen asignaciones y por tanto no
    obtienen ninguna zona. Es correcto: quien levanta información en terreno es el
    encuestador, y la separación de funciones que la HU-03 estableció —quien valida
    no es quien levanta— se rompería si el supervisor pudiera registrar fichas.
    Para casos excepcionales está el admin, que es el camino técnico y deja rastro
    en su propio log.
    """
    return (
        Zona.objects.filter(
            sector__asignaciones__censista=censista,
            sector__asignaciones__activa=True,
            sector__activo=True,
            activa=True,
        )
        .exclude(sector__operativo__estado=EstadoOperativo.CERRADO)
        .select_related("sector", "sector__comuna")
        .distinct()
        .order_by("sector__nombre", "nombre")
    )


class CampoSector(forms.ModelChoiceField):
    """Selector de sector que muestra también la comuna.

    Mismo recurso que CampoCensistas en la HU-06 y CampoComuna en la HU-05: al
    redefinir label_from_instance, cada opción dice «Los Boldos · Concepción». El
    nombre del sector solo puede ser ambiguo, porque dos comunas pueden tener un
    sector con el mismo nombre.
    """

    def label_from_instance(self, obj):
        return obj.nombre_completo


class FiltroMisEncuestasForm(forms.Form):
    """Filtros de la pantalla «Mis encuestas».

    ----------------------------------------------------------------------
    POR QUÉ EL FILTRO DE ESTADO TIENE DOS OPCIONES QUE NO SON ESTADOS
    ----------------------------------------------------------------------
    Además de los siete estados del modelo, el desplegable ofrece «Las que
    requieren tu trabajo» y «Las ya cerradas». No son un adorno: son la pregunta
    que el encuestador se hace de verdad al abrir la pantalla por la mañana, y sin
    ellas tendría que filtrar tres veces (pendientes, borradores y observadas) y
    sumar los resultados de memoria.

    Los dos grupos no se enumeran aquí: se leen de ESTADOS_ABIERTOS y
    ESTADOS_CERRADOS, que el modelo define una sola vez. Escribir la lista otra vez
    en este archivo sería garantizar que un estado nuevo quedara fuera del filtro
    aunque sí apareciera en el listado.

    ----------------------------------------------------------------------
    POR QUÉ EL FILTRO DE SECTOR SE CONSTRUYE CON LOS DATOS DE LA PERSONA
    ----------------------------------------------------------------------
    El desplegable solo ofrece los sectores donde ESA persona tiene encuestas, y no
    todos los del operativo. Es la misma decisión que FiltroAsignacionesForm tomó
    en la HU-06 al ofrecer solo los censistas desplegados: una opción que siempre
    devuelve una lista vacía es una opción que estorba.

    Aquí tiene además una consecuencia de seguridad agradable: la lista de
    sectores ajenos no se puede leer desde este formulario. Elegir a mano el
    identificador de un sector ajeno tampoco sirve de nada —el filtro se aplica
    sobre las encuestas propias, que ya están filtradas por la vista—, pero no
    ofrecerlos evita incluso mostrar que existen.
    """

    #: Valores del desplegable que agrupan varios estados en vez de uno.
    GRUPO_ABIERTAS = "ABIERTAS"
    GRUPO_CERRADAS = "CERRADAS"

    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Dirección o referencia",
                "autocomplete": "off",
            }
        ),
    )
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=(),  # se arman en __init__ para no repetir la lista del modelo
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    sector = CampoSector(
        label="Sector",
        required=False,
        queryset=Sector.objects.none(),  # se ajusta en __init__
        empty_label="Todos mis sectores",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    historicas = forms.BooleanField(
        label="Incluir operativos cerrados",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text=(
            "Por defecto se muestra solo el trabajo vivo. Marca esta casilla para "
            "ver también tus encuestas de operativos ya terminados."
        ),
    )

    def __init__(self, *args, censista=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["estado"].choices = [
            ("", "Cualquier estado"),
            (self.GRUPO_ABIERTAS, "Las que requieren tu trabajo"),
            (self.GRUPO_CERRADAS, "Las ya cerradas"),
            *EstadoEncuesta.choices,
        ]

        if censista is not None:
            self.fields["sector"].queryset = self.sectores_con_encuestas(censista)

    @staticmethod
    def sectores_con_encuestas(censista):
        """Sectores donde esta persona tiene alguna encuesta.

        Se resuelve con UNA consulta con distinct() sobre Sector, y no recorriendo
        las encuestas en Python: filtrar es trabajo de PostgreSQL, que es donde
        están los datos. Es el mismo criterio de Operativo.comunas_cubiertas() en
        la HU-05.
        """
        return (
            # El camino tiene un salto más desde la HU-08: la encuesta ya no cuelga
            # de la zona sino de la vivienda, que es la que cuelga de la zona.
            Sector.objects.filter(zonas__viviendas__encuestas__censista=censista)
            .select_related("comuna")
            .distinct()
            .order_by("comuna__nombre", "nombre")
        )

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()


# ==========================================================================
# HU-08 — REGISTRAR LA VIVIENDA
# ==========================================================================


class CampoZona(forms.ModelChoiceField):
    """Selector de zona que muestra el sector y la comuna.

    «Zona 1» a secas no identifica nada: casi todos los sectores tienen una. Es el
    mismo problema que Zona.nombre_completo resolvió para la bitácora en la HU-05,
    y aquí importa más todavía, porque elegir la zona equivocada manda la vivienda
    a otro pedazo del mapa sin que nada avise.
    """

    def label_from_instance(self, obj):
        return f"{obj.nombre} · {obj.sector.nombre} · {obj.sector.comuna.nombre}"


class ViviendaForm(forms.ModelForm):
    """Alta y corrección de una vivienda.

    ----------------------------------------------------------------------
    LAS SEIS CARACTERÍSTICAS SON OBLIGATORIAS AQUÍ Y OPCIONALES EN LA COLUMNA
    ----------------------------------------------------------------------
    El modelo las declara `blank=True` porque existen filas antiguas sin ellas
    (ver la decisión 3 de Vivienda). Eso haría que el ModelForm las diera por
    opcionales, que es justo lo contrario de lo que se quiere en el momento de
    registrar: la persona está en la puerta y puede responderlas mirando.

    Se fuerza `required = True` en __init__ en vez de redeclarar los seis campos a
    mano, para no repetir sus etiquetas, sus opciones y sus textos de ayuda —que
    ya están en el modelo— y arriesgarse a que las dos copias se separen.

    ----------------------------------------------------------------------
    EL AVISO DE DUPLICADO: POR QUÉ NO BLOQUEA
    ----------------------------------------------------------------------
    Si ya hay una vivienda registrada en la misma dirección y zona, el formulario
    NO la rechaza: pide confirmar. La razón está en el modelo (dos viviendas en un
    mismo sitio son frecuentísimas en terreno), y la consecuencia de diseño es
    esta: bloquear haría perder un dato real, y avisar solo cuesta un clic.

    Se implementa con una casilla que aparece únicamente cuando hay conflicto. El
    primer envío falla con un mensaje que explica qué se encontró; el segundo, con
    la casilla marcada, guarda. No hace falta JavaScript ni una pantalla
    intermedia.
    """

    #: Campos que el formulario exige aunque el modelo los admita vacíos.
    OBLIGATORIOS = (
        "tipo",
        "tenencia",
        "materialidad_muros",
        "origen_agua",
        "sistema_sanitario",
        "tiene_electricidad",
    )

    zona = CampoZona(
        label="Zona",
        queryset=Zona.objects.none(),  # se ajusta en __init__
        empty_label="Elige la zona",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
        help_text="Solo aparecen las zonas de los sectores que tienes asignados.",
    )
    confirmar_duplicado = forms.BooleanField(
        label="Confirmo que es una vivienda distinta y no la misma cargada dos veces",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Vivienda
        fields = (
            "zona",
            "direccion",
            "referencia",
            "tipo",
            "tenencia",
            "materialidad_muros",
            "origen_agua",
            "sistema_sanitario",
            "tiene_electricidad",
            "observaciones",
        )
        widgets = {
            "direccion": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Pasaje Los Robles 1425",
                    "autocomplete": "off",
                }
            ),
            "referencia": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Casa verde, portón negro",
                    "autocomplete": "off",
                }
            ),
            "tipo": forms.Select(attrs={"class": CLASE_SELECT}),
            "tenencia": forms.Select(attrs={"class": CLASE_SELECT}),
            "materialidad_muros": forms.Select(attrs={"class": CLASE_SELECT}),
            "origen_agua": forms.Select(attrs={"class": CLASE_SELECT}),
            "sistema_sanitario": forms.Select(attrs={"class": CLASE_SELECT}),
            "tiene_electricidad": forms.Select(
                attrs={"class": CLASE_SELECT},
                choices=((True, "Sí"), (False, "No")),
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": CLASE_TEXTO,
                    "rows": 2,
                    "placeholder": "Lo que convenga dejar anotado de la vivienda.",
                }
            ),
        }

    def __init__(self, *args, censista, **kwargs):
        """`censista` es obligatorio y va por nombre.

        Se exige después de `*` para que ninguna llamada pueda pasarlo por posición
        y confundirlo con `data`. Sin él no se puede armar la lista de zonas, y un
        formulario con la lista completa de zonas del país sería precisamente el
        agujero que esta historia tiene que evitar. Mismo cuidado que
        AsignarSectorForm en la HU-06 con su argumento `sector`.
        """
        self.censista = censista
        super().__init__(*args, **kwargs)

        self.fields["zona"].queryset = zonas_disponibles(censista)

        for nombre in self.OBLIGATORIOS:
            self.fields[nombre].required = True

        # El desplegable de electricidad no debe ofrecer «---------»: es una
        # pregunta de sí o no, y dejarla en blanco no es una respuesta.
        self.fields["tiene_electricidad"].widget.choices = (
            ("", "Elige una opción"),
            (True, "Sí"),
            (False, "No"),
        )

    def clean_tiene_electricidad(self):
        """«No sé» no es una respuesta válida al registrar.

        Hay que comprobarlo a mano porque el campo del modelo admite nulos y Django
        lo traduce a un NullBooleanField, cuyo `validate()` NO hace nada: marcarlo
        como `required` no basta, y el formulario aceptaría el vacío en silencio.
        Es justo el tipo de detalle que sin una prueba no se descubre hasta que
        media zona quedó sin el dato.
        """
        tiene = self.cleaned_data.get("tiene_electricidad")

        if tiene is None:
            raise forms.ValidationError("Indica si la vivienda tiene electricidad.")

        return tiene

    # -- duplicados ---------------------------------------------------------

    def viviendas_en_la_misma_direccion(self):
        """Otras viviendas ya registradas en esa zona y esa dirección."""
        zona = self.cleaned_data.get("zona")
        direccion = (self.cleaned_data.get("direccion") or "").strip()

        if not zona or not direccion:
            return Vivienda.objects.none()

        consulta = Vivienda.objects.filter(zona=zona, direccion__iexact=direccion)

        # Al EDITAR, la propia vivienda no es un duplicado de sí misma.
        if self.instance.pk:
            consulta = consulta.exclude(pk=self.instance.pk)

        return consulta.select_related("zona")

    def clean_direccion(self):
        return (self.cleaned_data.get("direccion") or "").strip()

    def clean(self):
        datos = super().clean()

        self.duplicadas = self.viviendas_en_la_misma_direccion()

        if self.duplicadas.exists() and not datos.get("confirmar_duplicado"):
            cuantas = self.duplicadas.count()
            self.add_error(
                "confirmar_duplicado",
                (
                    f"Ya hay {cuantas} vivienda{'s' if cuantas != 1 else ''} "
                    f"registrada{'s' if cuantas != 1 else ''} en esa dirección. Si "
                    "es la misma casa y solo quieres agregar otro hogar, vuelve a "
                    "la ficha de esa vivienda. Si de verdad es otra vivienda, marca "
                    "esta casilla."
                ),
            )

        return datos

    def save(self, commit=True):
        vivienda = super().save(commit=False)

        # Solo al crear: quien corrige una vivienda no pasa a ser quien la registró.
        if vivienda.pk is None:
            vivienda.registrada_por = self.censista

        if commit:
            vivienda.save()

        return vivienda


# ==========================================================================
# HU-08 — REGISTRAR EL GRUPO FAMILIAR
# ==========================================================================


class GrupoFamiliarForm(forms.ModelForm):
    """El hogar que vive en la vivienda.

    Es el formulario que de verdad «almacena la información del censo», y por eso
    la validación más cuidada está aquí y no en el de la vivienda.

    ----------------------------------------------------------------------
    POR QUÉ EL RUT SE VALIDA PERO NO SE EXIGE
    ----------------------------------------------------------------------
    El campo es opcional (ver la decisión 4 de GrupoFamiliar: en terreno mucha
    gente no lo recuerda, y legalmente no se puede condicionar el registro a
    entregar un dato personal que no es imprescindible). Pero cuando SÍ se
    entrega, se valida con `validar_rut` de la HU-01 —el mismo con dígito
    verificador que se usa para las cuentas— porque un RUT mal escrito es peor que
    ninguno: parece un identificador y no identifica a nadie.

    ----------------------------------------------------------------------
    LA VALIDACIÓN QUE NO ES OBVIA: EL INGRESO
    ----------------------------------------------------------------------
    Se rechaza un ingreso desmesurado, no porque sea imposible, sino porque casi
    siempre es un dedo de más al teclear en un teléfono. En un operativo social,
    un ingreso con un cero de sobra no se nota en la pantalla y sí desplaza el
    promedio de toda una zona.
    """

    #: Tope de cordura del ingreso mensual del hogar, en pesos.
    #: No es un límite legal ni un juicio sobre la familia: es el umbral a partir
    #: del cual lo más probable es que sobre un dígito.
    INGRESO_MAXIMO = 100_000_000

    class Meta:
        model = GrupoFamiliar
        fields = (
            "jefe_hogar_nombre",
            "jefe_hogar_rut",
            "telefono_contacto",
            "integrantes_declarados",
            "ingreso_mensual",
            "observaciones",
        )
        widgets = {
            "jefe_hogar_nombre": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "Nombre y apellidos",
                    "autocomplete": "off",
                }
            ),
            "jefe_hogar_rut": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "12345678-9",
                    "autocomplete": "off",
                }
            ),
            "telefono_contacto": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "+56 9 1234 5678",
                    "autocomplete": "off",
                }
            ),
            "integrantes_declarados": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "min": 1, "max": 30}
            ),
            "ingreso_mensual": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "min": 0, "placeholder": "En pesos"}
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": CLASE_TEXTO,
                    "rows": 3,
                    "placeholder": (
                        "Situaciones que conviene dejar por escrito: personas con "
                        "discapacidad, adultos mayores solos, etc."
                    ),
                }
            ),
        }

    def clean_jefe_hogar_nombre(self):
        nombre = (self.cleaned_data.get("jefe_hogar_nombre") or "").strip()

        if len(nombre) < 3:
            raise forms.ValidationError(
                "Escribe el nombre completo de la persona, no una inicial."
            )

        return nombre

    def clean_integrantes_declarados(self):
        """Al menos una persona; el resto lo comprueba también la tabla.

        El máximo no es una restricción de la base de datos a propósito: 30
        personas en un hogar es rarísimo pero no imposible —una residencia, una
        toma—, así que el sistema pregunta en vez de prohibir. Lo que sí es
        imposible es cero, y eso lo garantiza el CheckConstraint del modelo.
        """
        cuantos = self.cleaned_data.get("integrantes_declarados")

        if cuantos is not None and cuantos < 1:
            raise forms.ValidationError(
                "Un hogar tiene al menos una persona: la propia jefa o jefe de hogar."
            )

        return cuantos

    def clean_ingreso_mensual(self):
        ingreso = self.cleaned_data.get("ingreso_mensual")

        if ingreso is not None and ingreso > self.INGRESO_MAXIMO:
            raise forms.ValidationError(
                "Ese ingreso parece tener un dígito de más. Revísalo: si es "
                "correcto, anótalo en las observaciones."
            )

        return ingreso


