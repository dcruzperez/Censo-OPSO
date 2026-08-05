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


