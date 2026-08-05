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


# ==========================================================================
# HU-09 — REGISTRAR A LAS PERSONAS DEL HOGAR
# ==========================================================================


class IntegranteForm(forms.ModelForm):
    """Una persona del hogar.

    ----------------------------------------------------------------------
    LA VALIDACIÓN QUE DEFINE ESTE FORMULARIO: LOS CAMPOS QUE DEPENDEN DE LA EDAD
    ----------------------------------------------------------------------
    `nivel_educacional` y `situacion_ocupacional` admiten vacío en la columna y
    aquí se exigen —o no— SEGÚN LA FECHA DE NACIMIENTO que se acaba de escribir.
    No se le pregunta el nivel educacional a una guagua ni la ocupación a un niño
    de siete años.

    Se resuelve en `clean()` y no en `__init__` porque la edad no se conoce hasta
    que llegan los datos: en `__init__` todavía no hay fecha de nacimiento con la
    que decidir. Es una regla que depende de OTRO campo del mismo formulario, y
    ese es exactamente el trabajo de `clean()`.

    La alternativa —exigirlos siempre— produciría dos errores opuestos y los dos
    malos: pedir un dato que no existe para los niños, y aceptar el vacío en
    adultos si se dejara opcional para todos.

    ----------------------------------------------------------------------
    EL PARENTESCO Y EL JEFE DE HOGAR
    ----------------------------------------------------------------------
    El formulario sabe si el hogar YA tiene jefe registrado, y en ese caso retira
    la opción del desplegable. Es la misma técnica del queryset de zonas en la
    HU-08: lo que no está en el formulario no se puede enviar. La base de datos lo
    impide igualmente con `un_solo_jefe_por_hogar`, pero toparse con un
    IntegrityError es peor experiencia que no ver una opción imposible.

    La excepción es EDITAR al propio jefe de hogar: ahí la opción tiene que seguir
    estando, o al guardar cualquier otro cambio de esa persona el desplegable
    llegaría vacío y la dejaría sin parentesco.
    """

    #: Edad a partir de la cual el nivel educacional es obligatorio.
    EDAD_ESCOLARIDAD = Integrante.EDAD_ESCOLARIDAD

    #: Edad a partir de la cual la situación ocupacional es obligatoria.
    EDAD_OCUPACION = Integrante.EDAD_OCUPACION

    class Meta:
        model = Integrante
        fields = (
            "parentesco",
            "nombres",
            "apellidos",
            "rut",
            "sexo",
            "fecha_nacimiento",
            "nivel_educacional",
            "situacion_ocupacional",
            "pueblo_originario",
            "tiene_discapacidad",
            "observaciones",
        )
        widgets = {
            "parentesco": forms.Select(attrs={"class": CLASE_SELECT}),
            "nombres": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "autocomplete": "off"}
            ),
            "apellidos": forms.TextInput(
                attrs={"class": CLASE_TEXTO, "autocomplete": "off"}
            ),
            "rut": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": "12345678-9",
                    "autocomplete": "off",
                }
            ),
            "sexo": forms.Select(attrs={"class": CLASE_SELECT}),
            # type="date" deja que el teléfono abra su propio selector de fechas,
            # que en terreno es mucho más rápido y menos propenso a errores que
            # escribir 8 dígitos con una mano.
            "fecha_nacimiento": forms.DateInput(
                attrs={"class": CLASE_TEXTO, "type": "date"}, format="%Y-%m-%d"
            ),
            "nivel_educacional": forms.Select(attrs={"class": CLASE_SELECT}),
            "situacion_ocupacional": forms.Select(attrs={"class": CLASE_SELECT}),
            "pueblo_originario": forms.Select(attrs={"class": CLASE_SELECT}),
            "tiene_discapacidad": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": CLASE_TEXTO,
                    "rows": 2,
                    "placeholder": "Ej.: usa silla de ruedas, requiere apoyo permanente.",
                }
            ),
        }

    def __init__(self, *args, grupo_familiar, **kwargs):
        """`grupo_familiar` es obligatorio y va por nombre.

        Sin él no se puede saber si ya hay jefe de hogar ni comprobar los RUT
        repetidos, que son las dos reglas propias de este formulario. Se exige
        después de `*` por lo mismo que en ViviendaForm: para que nadie lo pase por
        posición y lo confunda con `data`.
        """
        self.grupo_familiar = grupo_familiar
        super().__init__(*args, **kwargs)

        self.fields["fecha_nacimiento"].input_formats = ["%Y-%m-%d", "%d-%m-%Y"]

        if self.debe_ocultar_jefe_de_hogar():
            self.fields["parentesco"].choices = [
                (valor, etiqueta)
                for valor, etiqueta in self.fields["parentesco"].choices
                if valor != Parentesco.JEFE_HOGAR
            ]

    def debe_ocultar_jefe_de_hogar(self):
        """True si el hogar ya tiene jefe y NO es la persona que se está editando."""
        jefe = self.grupo_familiar.jefe_hogar_registrado

        if jefe is None:
            return False

        return jefe.pk != self.instance.pk

    # -- validaciones -------------------------------------------------------

    def clean_nombres(self):
        return self.limpiar_nombre("nombres")

    def clean_apellidos(self):
        return self.limpiar_nombre("apellidos")

    def limpiar_nombre(self, campo):
        valor = (self.cleaned_data.get(campo) or "").strip()

        if len(valor) < 2:
            raise forms.ValidationError(
                "Escríbelo completo: una inicial no identifica a nadie."
            )

        return valor

    def clean_fecha_nacimiento(self):
        """Ni futura ni de hace más de 120 años.

        Se comprueba aquí además de en Integrante.clean() porque es lo que produce
        el mensaje junto al campo. Y no puede estar en una restricción de la base
        de datos: dependería de la fecha de hoy y sería falsa mañana.
        """
        fecha = self.cleaned_data.get("fecha_nacimiento")

        if fecha is None:
            return fecha

        hoy = timezone.localdate()

        if fecha > hoy:
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura.")

        if hoy.year - fecha.year > 120:
            raise forms.ValidationError(
                "Esa fecha implica más de 120 años. Revisa el año: casi siempre es "
                "un dígito equivocado."
            )

        return fecha

    def clean_rut(self):
        """El RUT no puede repetirse dentro del mismo hogar.

        La base de datos también lo impide (`rut_unico_en_el_hogar`), pero ahí el
        rechazo llega como un IntegrityError sin campo asociado. Aquí llega como un
        mensaje junto al RUT, que es donde la persona puede corregirlo.

        Se compara sobre el RUT NORMALIZADO, porque «12.345.678-5» y «12345678-5»
        son el mismo y sin normalizar pasarían como distintos hasta que el modelo
        los guardara iguales y la base de datos reventara.
        """
        rut = limpiar_rut(self.cleaned_data.get("rut")) or ""

        if not rut:
            return ""

        repetido = self.grupo_familiar.integrantes.filter(rut=rut)

        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)

        if repetido.exists():
            raise forms.ValidationError(
                "Ese RUT ya está registrado en este hogar. Si son personas "
                "distintas, revisa el número."
            )

        return rut

    def clean(self):
        """Escolaridad y ocupación, exigidas según la edad."""
        datos = super().clean()
        fecha = datos.get("fecha_nacimiento")

        if fecha is None:
            # Sin fecha no se puede decidir; el error de la fecha ya se informó.
            return datos

        edad = Integrante(fecha_nacimiento=fecha).edad()

        if edad >= self.EDAD_ESCOLARIDAD and not datos.get("nivel_educacional"):
            self.add_error(
                "nivel_educacional",
                f"Desde los {self.EDAD_ESCOLARIDAD} años hay que registrar el nivel "
                "educacional.",
            )

        if edad >= self.EDAD_OCUPACION and not datos.get("situacion_ocupacional"):
            self.add_error(
                "situacion_ocupacional",
                f"Desde los {self.EDAD_OCUPACION} años hay que registrar la "
                "situación ocupacional.",
            )

        return datos

    def save(self, commit=True):
        integrante = super().save(commit=False)
        integrante.grupo_familiar = self.grupo_familiar

        if commit:
            integrante.save()

        return integrante


# ==========================================================================
# HU-10 — GUARDAR EL BORRADOR Y CERRAR LA ENCUESTA
# ==========================================================================


class BorradorForm(forms.ModelForm):
    """La nota que el encuestador se deja a sí mismo antes de irse.

    ----------------------------------------------------------------------
    POR QUÉ ESTE FORMULARIO EXISTE SI YA TODO SE GUARDA SOLO
    ----------------------------------------------------------------------
    Desde la HU-08, cada pantalla guarda lo que se escribió en cuanto se pulsa el
    botón: no hay ningún dato del censo que se pierda al salir. Entonces, ¿qué
    guarda esta pantalla?

    Guarda LO QUE NO ES UN CAMPO DEL FORMULARIO: por dónde iba la conversación y
    cuándo conviene volver. Eso, hoy, vive en la cabeza del encuestador y se pierde
    al día siguiente. Una encuesta a medias sin nota es una encuesta que hay que
    reconstruir de memoria o volver a empezar, y cuando pasan cuatro días se vuelve
    a empezar.

    Es la diferencia entre «los datos están guardados» y «puedo continuar»: la
    historia pide lo segundo.

    ----------------------------------------------------------------------
    LA PRÓXIMA VISITA NO PUEDE SER DEL PASADO
    ----------------------------------------------------------------------
    Se valida porque una fecha pasada no es una cita, es un olvido: el listado la
    mostraría como visita vencida el mismo día en que se escribió. Se permite HOY,
    que es el caso real de «vuelvo esta tarde».
    """

    class Meta:
        model = Encuesta
        fields = ("nota_avance", "proxima_visita")
        widgets = {
            "nota_avance": forms.Textarea(
                attrs={
                    "class": CLASE_TEXTO,
                    "rows": 4,
                    "placeholder": (
                        "Ej.: falta el módulo de ingresos y los datos del hijo "
                        "mayor. La señora vuelve del trabajo a las 19:00."
                    ),
                }
            ),
            "proxima_visita": forms.DateInput(
                attrs={"class": CLASE_TEXTO, "type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proxima_visita"].input_formats = ["%Y-%m-%d", "%d-%m-%Y"]

    def clean_proxima_visita(self):
        fecha = self.cleaned_data.get("proxima_visita")

        if fecha is not None and fecha < timezone.localdate():
            raise forms.ValidationError(
                "Esa fecha ya pasó. Anota cuándo vas a volver, no cuándo estuviste."
            )

        return fecha


class CerrarSinDatosForm(forms.Form):
    """Cerrar una encuesta que NO se pudo levantar, dejando constancia.

    ----------------------------------------------------------------------
    POR QUÉ ESTE NO ES UN ModelForm, Y LOS DOS ANTERIORES SÍ
    ----------------------------------------------------------------------
    `ViviendaForm` y `GrupoFamiliarForm` editan los campos de un objeto, y para eso
    un ModelForm es lo correcto. Este formulario NO edita campos: PIDE UNA
    TRANSICIÓN de estado, y eso es otra cosa.

    La diferencia no es teórica, se ve al intentarlo: un ModelForm con `estado`
    entre sus campos ejecuta `Encuesta.clean()` al validar, con el estado nuevo ya
    puesto y las fechas todavía sin mover. La validación de coherencia de la HU-07
    —«una encuesta cerrada tiene que tener fecha de cierre»— rechaza esa
    combinación, y con razón: la fila estaría a medias. Las tres columnas las mueve
    `cambiar_estado()`, junto y en la vista.

    Es el mismo razonamiento que llevó a que AsignarSectorForm (HU-06) y
    PermisosRolForm (HU-04) fueran Form y no ModelForm: cuando lo que se envía no
    es «el contenido de un objeto», el ModelForm estorba en vez de ayudar.

    ----------------------------------------------------------------------
    POR QUÉ ESTO NO ES UN FRACASO NI UN CASO RARO
    ----------------------------------------------------------------------
    La HU-07 lo argumentó al definir los siete estados: «no ubicada» y «rechazada»
    son RESULTADOS, no fracasos. Si el único final posible fuera COMPLETADA, esas
    puertas quedarían pendientes para siempre y el avance del operativo mentiría
    hacia abajo: nadie podría distinguir «faltan 40 por visitar» de «40 no se pueden
    levantar y ya se sabe».

    Lo que la HU-07 no tenía era DÓNDE escribir el motivo, y por eso esta historia
    agrega `motivo_cierre` con una restricción que lo exige.

    ----------------------------------------------------------------------
    EL MOTIVO ES OBLIGATORIO Y CON UN MÍNIMO DE LARGO
    ----------------------------------------------------------------------
    La restricción de la base de datos solo exige que no esté vacío, así que un
    punto la satisfaría. Aquí se exige algo legible, porque el motivo tiene un
    lector concreto: el supervisor que decide si manda a otra persona a esa
    dirección o la da por cerrada. «x» no le sirve para decidir; «la dirección no
    existe, el pasaje llega hasta el 40» sí.
    """

    #: Largo mínimo del motivo. No es un número mágico: es lo que ocupa una frase
    #: corta, y menos que eso no explica nada.
    MOTIVO_MINIMO = 15

    #: Los dos únicos estados que esta pantalla puede producir. Se enumeran a partir
    #: de ESTADOS_SIN_LEVANTAR y no a mano, para que un tercer resultado de ese tipo
    #: aparezca aquí solo.
    estado = forms.ChoiceField(
        label="¿Qué pasó?",
        choices=(),  # se arman en __init__ desde ESTADOS_SIN_LEVANTAR
        widget=forms.RadioSelect,
    )
    motivo_cierre = forms.CharField(
        label="Motivo del cierre",
        widget=forms.Textarea(
            attrs={
                "class": CLASE_TEXTO,
                "rows": 3,
                "placeholder": (
                    "Ej.: la dirección no existe, el pasaje llega hasta el 40. "
                    "Confirmado con dos vecinos."
                ),
            }
        ),
        help_text=(
            "Lo va a leer tu supervisor para decidir si manda a otra persona a esa "
            "dirección."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["estado"].choices = [
            (valor, EstadoEncuesta(valor).label) for valor in ESTADOS_SIN_LEVANTAR
        ]

    def clean_motivo_cierre(self):
        motivo = (self.cleaned_data.get("motivo_cierre") or "").strip()

        if len(motivo) < self.MOTIVO_MINIMO:
            raise forms.ValidationError(
                "Explícalo con una frase: quien lea esto tiene que poder decidir si "
                "manda a otra persona a esa dirección."
            )

        return motivo


# ==========================================================================
# HU-11 — LA UBICACIÓN GEOGRÁFICA
# ==========================================================================


class UbicacionForm(forms.ModelForm):
    """Captura o corrige el punto GPS de una vivienda.

    ----------------------------------------------------------------------
    LOS CAMPOS LOS RELLENA EL NAVEGADOR, NO LA PERSONA
    ----------------------------------------------------------------------
    La historia pide capturar la ubicación AUTOMÁTICAMENTE, y eso lo hace la API de
    geolocalización del navegador (ver la plantilla). El formulario recibe lo que el
    aparato entregó: latitud, longitud y el radio de error que él mismo informa.

    Aun así los tres campos son editables y no ocultos, por dos motivos:

      - Sin JavaScript —o sin permiso de ubicación, o bajo techo sin señal— el
        formulario TIENE QUE SEGUIR SIRVIENDO. Se escriben las coordenadas a mano
        desde otro aparato y la encuesta no se queda sin punto. Es progressive
        enhancement: el JavaScript mejora la pantalla, no la sostiene.
      - Un campo oculto que se rellena solo es imposible de revisar. Verlos permite
        notar que el teléfono devolvió la posición de hace media hora.

    Lo que sí distingue el sistema es CÓMO se obtuvo: `ubicacion_manual` marca los
    puntos escritos a mano, porque no merecen la misma confianza que los capturados.

    ----------------------------------------------------------------------
    LA VALIDACIÓN GEOGRÁFICA: TRES CAPAS
    ----------------------------------------------------------------------
      1. Las dos coordenadas juntas o ninguna  -> restricción de la tabla
      2. El punto cae dentro de Chile          -> restricción de la tabla + aquí
      3. El punto está cerca del resto de la zona -> aquí, y solo AVISA

    Las dos primeras rechazan; la tercera pregunta. La diferencia es que un punto
    fuera de Chile es imposible, y un punto lejos del resto de la zona es
    improbable: puede ser una parcela apartada que de verdad pertenece a la zona.
    Bloquearlo haría perder un dato verdadero, así que se pide confirmar. Es el
    mismo patrón del aviso de dirección duplicada de la HU-08.
    """

    #: Límites del territorio nacional, insular incluido. Mismos valores que la
    #: restricción `vivienda_coordenadas_en_chile`, y por eso están en el modelo
    #: como constantes: dos copias con números distintos darían dos veredictos.
    confirmar_lejania = forms.BooleanField(
        label="Confirmo que la ubicación es correcta aunque esté lejos del resto de la zona",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Vivienda
        fields = ("latitud", "longitud", "precision_metros")
        widgets = {
            "latitud": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "step": "0.000001", "placeholder": "-36.826700"}
            ),
            "longitud": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "step": "0.000001", "placeholder": "-73.049700"}
            ),
            "precision_metros": forms.NumberInput(
                attrs={"class": CLASE_TEXTO, "min": 0, "placeholder": "metros"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Las coordenadas son obligatorias en ESTE formulario aunque la columna
        # admita nulos: una pantalla que se llama «capturar ubicación» y se envía
        # sin ubicación no hizo nada. Misma asimetría que ViviendaForm con las
        # características, y por el mismo motivo: la columna admite el vacío porque
        # hay viviendas anteriores sin punto.
        self.fields["latitud"].required = True
        self.fields["longitud"].required = True

    # -- validación ---------------------------------------------------------

    def clean_latitud(self):
        return self.comprobar_rango("latitud", Vivienda.LATITUD_MINIMA, Vivienda.LATITUD_MAXIMA)

    def clean_longitud(self):
        return self.comprobar_rango(
            "longitud", Vivienda.LONGITUD_MINIMA, Vivienda.LONGITUD_MAXIMA
        )

    def comprobar_rango(self, campo, minimo, maximo):
        """Rechaza un valor fuera del territorio nacional, con un mensaje útil.

        La restricción de la tabla ya lo impide, pero ahí el rechazo llega como un
        IntegrityError sin campo asociado. Aquí llega junto al número equivocado y
        explicando el error más probable, que es el signo: en Chile las dos
        coordenadas son negativas, siempre.
        """
        valor = self.cleaned_data.get(campo)

        if valor is None:
            return valor

        if not (minimo <= valor <= maximo):
            raise forms.ValidationError(
                f"Ese valor cae fuera de Chile. Revisa el signo: en Chile la "
                f"{campo} siempre es negativa, entre {minimo} y {maximo}."
            )

        return valor

    def clean(self):
        datos = super().clean()

        latitud = datos.get("latitud")
        longitud = datos.get("longitud")

        if latitud is None or longitud is None:
            return datos

        self.distancia_al_resto = self.calcular_distancia_al_resto(latitud, longitud)

        if (
            self.distancia_al_resto is not None
            and self.distancia_al_resto > Vivienda.DISTANCIA_SOSPECHOSA_METROS
            and not datos.get("confirmar_lejania")
        ):
            self.add_error(
                "confirmar_lejania",
                (
                    f"Este punto está a {self.distancia_al_resto:,.0f} m del resto de "
                    "las viviendas ubicadas de la zona. Suele significar que el "
                    "aparato entregó una posición antigua. Si de verdad la casa está "
                    "ahí, marca la casilla."
                ).replace(",", "."),
            )

        return datos

    def calcular_distancia_al_resto(self, latitud, longitud):
        """Metros hasta el punto medio de las demás viviendas ubicadas de la zona.

        Devuelve None cuando la zona todavía no tiene ninguna otra ubicada: es el
        caso de la primera casa de la jornada, y sin referencia no hay nada que
        comparar. Inventar una sería peor que no comprobar.
        """
        centro = Vivienda.centro_de_la_zona(
            self.instance.zona, excluir=self.instance.pk
        )

        if centro is None:
            return None

        # Se mide desde el punto NUEVO, así que se usa una vivienda temporal con
        # esas coordenadas en vez de la instancia guardada, que todavía tiene las
        # anteriores (o ninguna).
        return Vivienda(latitud=latitud, longitud=longitud).distancia_a(*centro)

    def save(self, commit=True):
        vivienda = super().save(commit=False)

        vivienda.ubicacion_capturada_en = timezone.now()
        # `capturada` lo pone la plantilla cuando el punto vino del navegador. Si no
        # llega, se asume escrito a mano: es la suposición prudente, porque marcar
        # como automático un dato tecleado le daría una confianza que no tiene.
        vivienda.ubicacion_manual = self.data.get("capturada") != "1"

        if commit:
            vivienda.save()

        return vivienda


# ==========================================================================
# HU-12 — LAS FOTOGRAFÍAS
# ==========================================================================


class FotografiaForm(forms.ModelForm):
    """Sube una fotografía como evidencia del levantamiento.

    ----------------------------------------------------------------------
    LO QUE VALIDA, Y POR QUÉ CADA COSA
    ----------------------------------------------------------------------
    Es el formulario con más validación del proyecto, y no por gusto: es el único
    que acepta un ARCHIVO, que es la entrada más peligrosa que puede recibir una
    aplicación web.

      1. QUE SEA UNA IMAGEN DE VERDAD. Lo hace ImageField decodificándola con
         Pillow. Comprobar la extensión no valida nada: cualquiera renombra un
         archivo. Esto es lo que impide que llegue algo que no es una foto.

      2. QUE EL FORMATO SEA UNO DE LOS TRES ESPERADOS. Pillow abre docenas de
         formatos, algunos exóticos y con historial de vulnerabilidades. Aceptar
         solo JPEG, PNG y WEBP reduce la superficie a lo que un teléfono produce.

      3. QUE NO PESE DEMASIADO. Cinco megabytes sobran para la foto de una fachada,
         y el límite evita que una imagen de 40 MB bloquee la subida en una conexión
         de terreno.

      4. QUE LA VIVIENDA NO ACUMULE UN ÁLBUM. La historia dice «cuando sea
         necesario»: cinco fotos por vivienda es el tope, y llegar a él suele
         significar que se está documentando de más.

      5. QUE HAYA UNA DESCRIPCIÓN. Ver la decisión 4 del modelo.

    ----------------------------------------------------------------------
    EL LÍMITE DE TAMAÑO SE COMPRUEBA ANTES QUE EL FORMATO
    ----------------------------------------------------------------------
    Y no es casual. Validar el formato obliga a decodificar la imagen, y decodificar
    una imagen enorme —o una preparada para expandirse al descomprimirse— consume
    memoria. Mirar `size` es leer un número que ya está ahí. Se rechaza barato antes
    de gastar caro.
    """

    class Meta:
        model = Fotografia
        fields = ("imagen", "tipo", "descripcion")
        widgets = {
            "imagen": forms.ClearableFileInput(
                attrs={
                    "class": CLASE_TEXTO,
                    # accept limita lo que ofrece el selector del teléfono y, en un
                    # móvil, hace que aparezca la cámara. Es comodidad, no
                    # seguridad: el servidor valida igual.
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
            "tipo": forms.Select(attrs={"class": CLASE_SELECT}),
            "descripcion": forms.TextInput(
                attrs={
                    "class": CLASE_TEXTO,
                    "placeholder": (
                        "El número de la casa está borrado; es la tercera del pasaje"
                    ),
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, vivienda, **kwargs):
        """`vivienda` es obligatoria y va por nombre.

        Sin ella no se puede comprobar el tope de fotografías, que es la única regla
        que depende de lo que ya hay guardado. Se exige después de `*` por lo mismo
        que en los demás formularios del módulo: para que nadie la pase por posición
        y la confunda con `data`.
        """
        self.vivienda = vivienda
        super().__init__(*args, **kwargs)

    def clean_descripcion(self):
        descripcion = (self.cleaned_data.get("descripcion") or "").strip()

        if len(descripcion) < 10:
            raise forms.ValidationError(
                "Explica en una frase qué muestra la foto y por qué hizo falta. "
                "Dentro de seis meses nadie va a recordarlo."
            )

        return descripcion

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")

        if imagen is None:
            return imagen

        # 1. El peso, primero: es barato y evita decodificar algo enorme.
        maximo = settings.OPSO_TAMANO_MAXIMO_FOTO

        if imagen.size > maximo:
            raise forms.ValidationError(
                f"La imagen pesa {imagen.size / 1024 / 1024:.1f} MB y el máximo son "
                f"{maximo / 1024 / 1024:.0f} MB. Vuelve a tomarla con menos "
                "resolución."
            )

        # 2. El formato. `imagen.image` lo dejó puesto ImageField al validar con
        #    Pillow, así que aquí no se vuelve a abrir el archivo.
        formato = getattr(getattr(imagen, "image", None), "format", None)

        if formato not in Fotografia.FORMATOS:
            raise forms.ValidationError(
                f"El formato {formato or 'de la imagen'} no se acepta. Usa JPEG, "
                "PNG o WEBP, que es lo que produce cualquier teléfono."
            )

        return imagen

    def clean(self):
        datos = super().clean()

        tope = settings.OPSO_MAXIMO_FOTOS_POR_VIVIENDA
        cuantas = self.vivienda.fotografias.count()

        if self.instance.pk is None and cuantas >= tope:
            raise forms.ValidationError(
                f"Esta vivienda ya tiene {cuantas} fotografías, que es el máximo. "
                "Si hace falta otra, quita alguna que ya no sirva: las fotos son "
                "evidencia puntual, no un álbum."
            )

        return datos

    def save(self, commit=True):
        fotografia = super().save(commit=False)
        fotografia.vivienda = self.vivienda

        if commit:
            fotografia.save()

        return fotografia


