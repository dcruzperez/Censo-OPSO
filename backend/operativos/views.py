"""Vistas de la organización territorial (HU-05).

Cuatro CRUD y una pantalla de estado, sobre dos ejes:

    /operativos/            -> listado de operativos
    /operativos/<pk>/       -> ficha con su territorio: sectores y zonas anidados
    /operativos/comunas/    -> catálogo de comunas (transversal a los operativos)

CONTROL DE ACCESO — POR PERMISO, REUTILIZANDO LA HU-04

Ninguna vista de este módulo exige un ROL. Todas exigen un PERMISO, con
PermisoRequeridoMixin, y los permisos son los que la migración 0005 de la HU-04
YA sembró:

    operativos.ver        -> consultar (listados y fichas)
    operativos.gestionar  -> crear, editar, activar y desactivar

No se agregó ni una fila al catálogo de permisos. Eso no es suerte: es la ventaja
del diseño de la HU-04 cobrándose sola. La descripción sembrada entonces decía
literalmente "Definir el operativo, sus fechas y la división territorial", así
que la autorización de esta historia estaba modelada antes de que existieran las
pantallas.

Consecuencia práctica y demostrable en la defensa: el administrador puede delegar
TODA la planificación territorial en el rol Supervisor marcando dos casillas en la
matriz, sin que nadie edite ni despliegue código.

POR QUÉ LA LECTURA Y LA ESCRITURA SE SEPARAN EN DOS PERMISOS

Porque son dos necesidades distintas. Un supervisor necesita CONSULTAR en qué
zonas está dividido su sector para repartir el trabajo; no necesita poder
redibujar el territorio. Con un solo permiso, delegar la consulta obligaría a
entregar también la capacidad de rehacer la planificación completa.

LAS TRES CAPAS DEL CONTROL DE ACCESO, IGUAL QUE EN LA HU-03

  1. LoginRequiredMiddleware        -> ninguna vista responde sin sesión.
  2. PermisoRequeridoMixin          -> el permiso que cada vista declara.
  3. OperativoAbiertoMixin          -> regla POR OBJETO: un operativo cerrado no
                                       admite cambios de territorio, tenga quien
                                       entre el permiso que tenga.

La capa 3 es la que impide la "modificación por URL": no basta con poder
gestionar territorio, el operativo concreto también tiene que admitirlo.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from usuarios.auditoria import describir_cambios, registrar_accion
from usuarios.mixins import PermisoRequeridoMixin
from usuarios.models import AccionAuditoria

from .forms import (
    CambiarEstadoOperativoForm,
    ComunaForm,
    FiltroComunasForm,
    FiltroOperativosForm,
    OperativoForm,
    SectorForm,
    ZonaForm,
)
from .models import Comuna, EstadoOperativo, Operativo, Sector, Zona


# ==========================================================================
# PUERTAS DE ACCESO COMUNES
# ==========================================================================


class ConsultaTerritorialMixin(PermisoRequeridoMixin):
    """Puerta para las pantallas que solo LEEN.

    Se declara una vez y la heredan todas las vistas de consulta, igual que
    ModuloUsuariosMixin en la HU-04. La ventaja es la misma: es imposible agregar
    una pantalla al módulo y olvidar protegerla, porque la protección viene en la
    clase base. Y si alguien hereda sin declarar permisos_requeridos,
    PermisoRequeridoMixin levanta ImproperlyConfigured en vez de dejarla abierta.
    """

    permisos_requeridos = ("operativos.ver",)
    mensaje_sin_permiso = "No tienes permiso para consultar la organización territorial."


class GestionTerritorialMixin(PermisoRequeridoMixin):
    """Puerta para las pantallas que MODIFICAN."""

    permisos_requeridos = ("operativos.gestionar",)
    mensaje_sin_permiso = "No tienes permiso para modificar la organización territorial."


class OperativoAbiertoMixin:
    """Regla POR OBJETO: un operativo cerrado no admite cambios de territorio.

    Se extrae en su propia clase por lo mismo que VerificarSuperusuarioMixin en
    la HU-03: es una regla sobre EL OBJETO, no sobre quién entra. Así se combina
    con la puerta de acceso sin quedar amarrada a ella.

    Es la capa que no puede saltarse ningún permiso de la matriz: tener
    "operativos.gestionar" autoriza a planificar territorio, no a reescribir la
    historia de un operativo que ya terminó.

    EL ORDEN DE HERENCIA IMPORTA, Y NO ES UN DETALLE COSMÉTICO.

    Este mixin debe declararse DESPUÉS de la puerta de permiso:

        class SectorCreateView(GestionTerritorialMixin, OperativoAbiertoMixin, ...)

    Porque dispatch() se encadena siguiendo el orden de resolución de métodos: el
    de GestionTerritorialMixin (que hereda el de UserPassesTestMixin) corre
    primero, comprueba el permiso, y solo entonces llama al de aquí. Al revés, un
    usuario SIN permiso averiguaría si un operativo existe y en qué estado está
    por la diferencia entre los mensajes de error. Es una fuga de información
    pequeña, pero gratuita de evitar.

    Se responde con una redirección y un mensaje, no con un 403, porque no es un
    intento de intrusión: es alguien que llegó a una pantalla que ya no aplica, y
    lo útil es explicarle por qué y devolverlo a la ficha.
    """

    def obtener_operativo_afectado(self):
        """El operativo cuyo territorio se pretende tocar.

        Cada vista sabe cómo encontrarlo: unas lo tienen en la URL, otras dos
        niveles más arriba del objeto que editan. Se declara aquí para que quede
        explícito que una vista que herede de este mixin SIN implementarlo falle
        de inmediato, en vez de saltarse la comprobación en silencio.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} hereda de OperativoAbiertoMixin pero no "
            "implementa obtener_operativo_afectado()."
        )

    def dispatch(self, request, *args, **kwargs):
        operativo = self.obtener_operativo_afectado()

        if not operativo.admite_cambios_de_territorio:
            messages.error(
                request,
                f"El operativo «{operativo.nombre}» está cerrado: su división "
                "territorial ya no se puede modificar. Reábrelo si necesitas "
                "cambiarla.",
            )
            return redirect("operativos:operativo_detalle", pk=operativo.pk)

        return super().dispatch(request, *args, **kwargs)


class ObjetoCacheadoMixin:
    """get_object() resuelve UNA consulta por petición, no varias.

    Hace falta porque OperativoAbiertoMixin necesita el objeto en dispatch() para
    saber a qué operativo pertenece, y después UpdateView vuelve a pedirlo para
    el formulario. Sin esta caché, cada edición costaría dos consultas idénticas.

    cached_property guarda el resultado en la instancia de la vista, y Django crea
    una instancia nueva por petición: no hay riesgo de que un objeto se filtre
    entre peticiones ni entre usuarios.
    """

    @cached_property
    def objeto(self):
        return super().get_object()

    def get_object(self, queryset=None):
        return self.objeto


# ==========================================================================
# 1. OPERATIVOS — LISTADO
# ==========================================================================


class OperativoListView(ConsultaTerritorialMixin, ListView):
    """Listado de operativos con búsqueda, filtro por estado y paginación.

    URL: /operativos/
    """

    model = Operativo
    template_name = "operativos/operativo_list.html"
    context_object_name = "operativos"
    paginate_by = 10

    def get_queryset(self):
        """Los operativos, ya con sus totales contados por PostgreSQL.

        annotate(Count(...)) resuelve los contadores en la MISMA consulta. Sin
        esto, mostrar "3 sectores · 12 zonas" en cada fila lanzaría dos consultas
        por operativo: con 10 filas serían 21 consultas en vez de 1 (el problema
        N+1).

        distinct=True no es opcional aquí: al unir sectores y zonas en la misma
        consulta, cada sector se repite una vez por zona, y sin distinct el
        conteo de sectores saldría multiplicado. Es el error clásico de combinar
        dos Count sobre relaciones anidadas.
        """
        consulta = (
            Operativo.objects.annotate(
                n_sectores=Count("sectores", distinct=True),
                n_zonas=Count("sectores__zonas", distinct=True),
            )
            .select_related("creado_por")
            # El order_by es OBLIGATORIO aquí, aunque el Meta del modelo ya
            # declare el mismo orden: Django DESCARTA el ordering por defecto en
            # las consultas que llevan GROUP BY, y annotate(Count(...)) genera
            # uno. Sin esta línea el queryset queda sin orden, y un queryset sin
            # orden paginado devuelve resultados inconsistentes (PostgreSQL no
            # garantiza el mismo orden entre dos consultas). Django lo advierte
            # con UnorderedObjectListWarning.
            .order_by("-fecha_inicio", "nombre")
        )

        self.filtro = FiltroOperativosForm(self.request.GET or None)

        if self.filtro.is_valid():
            texto = self.filtro.cleaned_data.get("q")
            estado = self.filtro.cleaned_data.get("estado")

            if texto:
                consulta = consulta.filter(
                    Q(nombre__icontains=texto) | Q(descripcion__icontains=texto)
                )
            if estado:
                consulta = consulta.filter(estado=estado)

        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Operativos"
        contexto["filtro"] = self.filtro

        # Los filtros vigentes SIN el número de página, para que los enlaces de
        # la paginación no pierdan la búsqueda. Mismo recurso que en la HU-03.
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        # Contadores globales, no de la página: responden "¿cómo va todo?" y no
        # deben cambiar al pasar de página.
        contexto["total_operativos"] = Operativo.objects.count()
        contexto["total_en_curso"] = Operativo.objects.filter(
            estado=EstadoOperativo.EN_CURSO
        ).count()
        contexto["total_planificacion"] = Operativo.objects.filter(
            estado=EstadoOperativo.PLANIFICACION
        ).count()
        contexto["puede_gestionar"] = self.request.user.tiene_permiso(
            "operativos.gestionar"
        )
        return contexto


# ==========================================================================
# 2. OPERATIVOS — FICHA CON EL TERRITORIO ANIDADO
# ==========================================================================


class OperativoDetailView(ConsultaTerritorialMixin, DetailView):
    """Ficha del operativo: sus datos y su árbol de sectores y zonas.

    URL: /operativos/<pk>/

    Es la pantalla central de la historia. Reúne en un solo lugar lo que hace
    falta para responder "¿cómo está organizado este operativo?": los sectores
    agrupados por comuna y, dentro de cada sector, sus zonas.
    """

    model = Operativo
    template_name = "operativos/operativo_detail.html"
    context_object_name = "operativo"

    def get_queryset(self):
        """Trae el operativo con TODO su territorio en un número fijo de consultas.

        prefetch_related con un Prefetch anidado carga los sectores (con su comuna
        y su región) y las zonas de cada sector. Dibujar el árbol completo cuesta
        entonces cuatro consultas, no una por sector más una por zona.

        El orden de las zonas se fija aquí, en el Prefetch, y no en la plantilla:
        ordenar en la consulta lo hace PostgreSQL; ordenar en la plantilla
        obligaría a traerlo todo y reordenarlo en memoria.
        """
        # HU-06: el equipo a cargo de cada sector se trae en el mismo prefetch. Se
        # filtra a las asignaciones ACTIVAS y se guarda en `equipo` con to_attr,
        # porque sin filtrar la plantilla mostraría también a quien ya fue retirado.
        #
        # Añadirlo aquí y no llamar a sector.asignaciones_activas() en la plantilla
        # es lo que mantiene constante el coste de la página: hay una prueba
        # (OperativoDetalleConsultasTest) que falla si el número de consultas crece
        # con el número de sectores.
        from .models import AsignacionSector

        equipo_activo = Prefetch(
            "asignaciones",
            queryset=AsignacionSector.objects.filter(activa=True)
            .select_related("censista")
            .order_by("censista__first_name", "censista__last_name"),
            to_attr="equipo",
        )

        return Operativo.objects.select_related("creado_por").prefetch_related(
            Prefetch(
                "sectores",
                queryset=Sector.objects.select_related("comuna", "comuna__region")
                .prefetch_related(
                    Prefetch("zonas", queryset=Zona.objects.order_by("nombre")),
                    equipo_activo,
                )
                .order_by("comuna__region__orden", "comuna__nombre", "nombre"),
            )
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        operativo = self.object

        contexto["titulo_pagina"] = operativo.nombre
        contexto["grupos"] = self.agrupar_por_comuna(operativo)

        # Se cuenta sobre los objetos YA cargados por el prefetch: len() sobre
        # una lista prefetchada no toca la base de datos, mientras que .count()
        # lanzaría una consulta nueva por cada contador.
        sectores = list(operativo.sectores.all())
        contexto["total_sectores"] = len(sectores)
        contexto["total_zonas"] = sum(len(s.zonas.all()) for s in sectores)
        contexto["total_comunas"] = len({s.comuna_id for s in sectores})
        contexto["viviendas_estimadas"] = sum(
            zona.viviendas_estimadas or 0
            for sector in sectores
            for zona in sector.zonas.all()
        )

        contexto["puede_gestionar"] = self.request.user.tiene_permiso(
            "operativos.gestionar"
        )
        return contexto

    def agrupar_por_comuna(self, operativo):
        """Agrupa los sectores por comuna para que la plantilla solo recorra.

        Se construye en Python, en la vista, por la misma razón que la matriz de
        permisos de la HU-04: el lenguaje de plantillas de Django no agrupa, y
        forzarlo llevaría a inventar filtros propios. Preparar los datos aquí deja
        la plantilla en dos bucles anidados y nada más.

        Resultado:
            [{"comuna": <Comuna>, "sectores": [<Sector>, ...]}, ...]
        """
        grupos = {}

        for sector in operativo.sectores.all():
            grupo = grupos.setdefault(
                sector.comuna_id, {"comuna": sector.comuna, "sectores": []}
            )
            grupo["sectores"].append(sector)

        # El orden lo dio ya el queryset (región de norte a sur, luego comuna) y
        # los diccionarios de Python conservan el orden de inserción, así que
        # basta con devolver los valores.
        return list(grupos.values())


# ==========================================================================
# 3. OPERATIVOS — CREAR Y EDITAR
# ==========================================================================


class OperativoCreateView(GestionTerritorialMixin, CreateView):
    """Alta de un operativo. URL: /operativos/nuevo/"""

    model = Operativo
    form_class = OperativoForm
    template_name = "operativos/operativo_form.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Nuevo operativo"
        contexto["es_creacion"] = True
        return contexto

    def form_valid(self, formulario):
        """Guarda el operativo y su fila de auditoría en una sola transacción.

        transaction.atomic garantiza que no pueda quedar un operativo creado sin
        su registro en la bitácora: si la auditoría falla, el operativo tampoco se
        guarda. Es el mismo criterio de la HU-03 y de la matriz de la HU-04. Una
        bitácora con huecos es peor que no tenerla, porque da falsa confianza.
        """
        with transaction.atomic():
            formulario.instance.creado_por = self.request.user
            operativo = formulario.save()

            registrar_accion(
                administrador=self.request.user,
                accion=AccionAuditoria.CREAR_TERRITORIO,
                objeto_territorial=operativo,
                detalle=(
                    f"Operativo creado del {operativo.fecha_inicio:%d-%m-%Y} al "
                    f"{operativo.fecha_termino:%d-%m-%Y} "
                    f"({operativo.duracion_dias} días)."
                ),
                request=self.request,
            )

        messages.success(
            self.request,
            f"Operativo «{operativo.nombre}» creado. Ahora agrega los sectores "
            "donde se va a trabajar.",
        )
        return redirect(operativo.get_absolute_url())


class OperativoUpdateView(GestionTerritorialMixin, UpdateView):
    """Edición de los datos de un operativo. URL: /operativos/<pk>/editar/

    Se puede editar en cualquier estado, incluso cerrado: corregir una fecha mal
    escrita o completar la descripción de un operativo pasado es legítimo y no
    altera el territorio. Lo que un operativo cerrado no admite son cambios en su
    división territorial, y eso lo protege OperativoAbiertoMixin en las vistas de
    sectores y zonas, no aquí.
    """

    model = Operativo
    form_class = OperativoForm
    template_name = "operativos/operativo_form.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Editar {self.object.nombre}"
        contexto["es_creacion"] = False
        return contexto

    def form_valid(self, formulario):
        """Registra solo lo que cambió, usando describir_cambios de la HU-03.

        Si no cambió nada no se escribe en la bitácora: guardar el formulario sin
        tocar un campo no es un hecho auditable, y las filas vacías esconden las
        que importan. Es la misma regla que aplica la matriz de permisos.
        """
        detalle = describir_cambios(formulario)

        with transaction.atomic():
            operativo = formulario.save()

            if detalle:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.EDITAR_TERRITORIO,
                    objeto_territorial=operativo,
                    detalle=detalle,
                    request=self.request,
                )

        if detalle:
            messages.success(
                self.request, f"Operativo «{operativo.nombre}» actualizado."
            )
        else:
            messages.info(self.request, "No hiciste ningún cambio.")

        return redirect(operativo.get_absolute_url())


# ==========================================================================
# 4. OPERATIVOS — CAMBIAR DE ESTADO
# ==========================================================================


class OperativoCambiarEstadoView(GestionTerritorialMixin, View):
    """Cambia el estado de un operativo. GET confirma, POST ejecuta.

    URL: /operativos/<pk>/estado/

    DOS PASOS, POR LA MISMA RAZÓN QUE DESHABILITAR UNA CUENTA EN LA HU-03:
    cambiar el estado MODIFICA datos, y las peticiones GET deben ser seguras e
    idempotentes (regla de HTTP). Si se pudiera cerrar un operativo con un GET,
    bastaría con insertar <img src=".../estado/"> en cualquier página para que el
    navegador del administrador lo ejecutara sin que lo notara: es un ataque CSRF.
    Con POST y token es imposible.

    Y de paso el GET sirve de pantalla de confirmación, que es donde se explica la
    consecuencia: cerrar un operativo congela su división territorial.
    """

    template_name = "operativos/operativo_estado.html"

    @cached_property
    def operativo(self):
        return get_object_or_404(Operativo, pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        formulario = CambiarEstadoOperativoForm(operativo=self.operativo)
        return render(request, self.template_name, self.contexto(formulario))

    def post(self, request, *args, **kwargs):
        operativo = self.operativo
        formulario = CambiarEstadoOperativoForm(request.POST, operativo=operativo)

        if not formulario.is_valid():
            return render(request, self.template_name, self.contexto(formulario))

        anterior = operativo.get_estado_display()
        nuevo = formulario.cleaned_data["estado"]
        motivo = formulario.cleaned_data.get("motivo", "")

        detalle = f"Estado: «{anterior}» → «{EstadoOperativo(nuevo).label}»"
        if motivo:
            detalle += f". Motivo: {motivo}"

        with transaction.atomic():
            operativo.estado = nuevo
            # update_fields limita el UPDATE a las columnas que cambian. No es
            # solo eficiencia: evita sobrescribir con datos viejos cualquier otro
            # campo que se hubiera modificado entre la carga y el guardado.
            operativo.save(update_fields=["estado", "actualizado_en"])

            registrar_accion(
                administrador=request.user,
                accion=AccionAuditoria.CAMBIAR_ESTADO_OPERATIVO,
                objeto_territorial=operativo,
                detalle=detalle,
                request=request,
            )

        messages.success(
            request,
            f"El operativo «{operativo.nombre}» quedó "
            f"«{operativo.get_estado_display()}».",
        )
        return redirect(operativo.get_absolute_url())

    def contexto(self, formulario):
        return {
            "titulo_pagina": f"Cambiar el estado de {self.operativo.nombre}",
            "operativo": self.operativo,
            "form": formulario,
            # Si no hay transiciones posibles, la plantilla lo explica en vez de
            # mostrar un desplegable vacío.
            "sin_transiciones": not formulario.fields["estado"].choices,
        }


# ==========================================================================
# 5. COMUNAS
# ==========================================================================


class ComunaListView(ConsultaTerritorialMixin, ListView):
    """Catálogo de comunas donde OPSO puede operar.

    URL: /operativos/comunas/

    Vive bajo /operativos/ aunque sea transversal a todos ellos, porque forma
    parte de la misma tarea del administrador: preparar dónde se va a trabajar.
    """

    model = Comuna
    template_name = "operativos/comuna_list.html"
    context_object_name = "comunas"
    paginate_by = 20

    def get_queryset(self):
        consulta = (
            Comuna.objects.select_related("region")
            .annotate(n_sectores=Count("sectores", distinct=True))
            # Igual que en el listado de operativos: annotate(Count(...)) genera
            # un GROUP BY y Django descarta el Meta.ordering, así que el orden hay
            # que repetirlo explícitamente o la paginación no es fiable.
            .order_by("region__orden", "nombre")
        )

        self.filtro = FiltroComunasForm(self.request.GET or None)

        if self.filtro.is_valid():
            texto = self.filtro.cleaned_data.get("q")
            region = self.filtro.cleaned_data.get("region")
            estado = self.filtro.cleaned_data.get("estado")

            if texto:
                consulta = consulta.filter(nombre__icontains=texto)
            if region:
                consulta = consulta.filter(region=region)
            if estado == "activas":
                consulta = consulta.filter(activa=True)
            elif estado == "inactivas":
                consulta = consulta.filter(activa=False)

        return consulta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Comunas"
        contexto["filtro"] = self.filtro

        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        contexto["total_comunas"] = Comuna.objects.count()
        contexto["total_activas"] = Comuna.objects.filter(activa=True).count()
        contexto["puede_gestionar"] = self.request.user.tiene_permiso(
            "operativos.gestionar"
        )
        return contexto


class ComunaCreateView(GestionTerritorialMixin, CreateView):
    """Alta de una comuna. URL: /operativos/comunas/nueva/"""

    model = Comuna
    form_class = ComunaForm
    template_name = "operativos/comuna_form.html"
    success_url = reverse_lazy("operativos:comuna_lista")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Nueva comuna"
        contexto["es_creacion"] = True
        return contexto

    def form_valid(self, formulario):
        with transaction.atomic():
            comuna = formulario.save()
            registrar_accion(
                administrador=self.request.user,
                accion=AccionAuditoria.CREAR_TERRITORIO,
                objeto_territorial=comuna,
                detalle=f"Comuna dada de alta en {comuna.region.nombre}.",
                request=self.request,
            )

        messages.success(
            self.request,
            f"Comuna «{comuna.nombre}» agregada. Ya se puede usar al crear sectores.",
        )
        return redirect(self.success_url)


class ComunaUpdateView(GestionTerritorialMixin, UpdateView):
    """Edición de una comuna. URL: /operativos/comunas/<pk>/editar/"""

    model = Comuna
    form_class = ComunaForm
    template_name = "operativos/comuna_form.html"
    success_url = reverse_lazy("operativos:comuna_lista")

    def get_queryset(self):
        return Comuna.objects.select_related("region")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Editar {self.object.nombre}"
        contexto["es_creacion"] = False
        return contexto

    def form_valid(self, formulario):
        detalle = describir_cambios(formulario)

        with transaction.atomic():
            comuna = formulario.save()
            if detalle:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.EDITAR_TERRITORIO,
                    objeto_territorial=comuna,
                    detalle=detalle,
                    request=self.request,
                )

        if detalle:
            messages.success(self.request, f"Comuna «{comuna.nombre}» actualizada.")
        else:
            messages.info(self.request, "No hiciste ningún cambio.")

        return redirect(self.success_url)


class ComunaCambiarEstadoView(GestionTerritorialMixin, View):
    """Activa o desactiva una comuna. GET confirma, POST ejecuta.

    URLs: /operativos/comunas/<pk>/desactivar/ y .../activar/

    Una sola clase atiende las dos rutas; el atributo `activar` (definido en
    urls.py) decide el sentido de la operación. Así la validación y la auditoría
    no se escriben dos veces. Es el mismo patrón que CambiarEstadoUsuarioView en
    la HU-03.
    """

    template_name = "operativos/comuna_confirmar_estado.html"

    #: True = activar, False = desactivar. Se define en urls.py.
    activar = False

    @cached_property
    def comuna(self):
        return get_object_or_404(
            Comuna.objects.select_related("region"), pk=self.kwargs["pk"]
        )

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.contexto())

    def post(self, request, *args, **kwargs):
        comuna = self.comuna

        # REGLA DE NEGOCIO: no desactivar una comuna con trabajo vivo.
        #
        # Se comprueba en el POST y no solo se oculta el botón en la plantilla,
        # porque ocultar un botón no es una validación: la URL se puede escribir a
        # mano. Es la misma lección de la HU-03 con "no autodeshabilitarse".
        if not self.activar:
            permitido, motivo = comuna.puede_desactivarse()
            if not permitido:
                messages.error(request, motivo)
                return redirect("operativos:comuna_lista")

        if comuna.activa == self.activar:
            # Nada que hacer. No se escribe en la bitácora ni se avisa de un
            # éxito que no ocurrió: probablemente se recargó la página o se abrió
            # el enlace dos veces.
            messages.info(
                request,
                f"La comuna «{comuna.nombre}» ya estaba "
                f"{'activa' if self.activar else 'desactivada'}.",
            )
            return redirect("operativos:comuna_lista")

        with transaction.atomic():
            comuna.activa = self.activar
            comuna.save(update_fields=["activa", "actualizado_en"])

            registrar_accion(
                administrador=request.user,
                accion=(
                    AccionAuditoria.ACTIVAR_TERRITORIO
                    if self.activar
                    else AccionAuditoria.DESACTIVAR_TERRITORIO
                ),
                objeto_territorial=comuna,
                detalle=(
                    "Comuna activada: vuelve a ofrecerse al crear sectores."
                    if self.activar
                    else "Comuna desactivada: deja de ofrecerse al crear sectores."
                ),
                request=request,
            )

        messages.success(
            request,
            f"Comuna «{comuna.nombre}» "
            f"{'activada' if self.activar else 'desactivada'}. No se borró ningún "
            "dato.",
        )
        return redirect("operativos:comuna_lista")

    def contexto(self):
        permitido, motivo = True, ""
        if not self.activar:
            permitido, motivo = self.comuna.puede_desactivarse()

        return {
            "titulo_pagina": (
                f"{'Activar' if self.activar else 'Desactivar'} {self.comuna.nombre}"
            ),
            "comuna": self.comuna,
            "activar": self.activar,
            "permitido": permitido,
            "motivo": motivo,
            "total_sectores": self.comuna.total_sectores(),
        }


# ==========================================================================
# 6. SECTORES
# ==========================================================================


class SectorCreateView(GestionTerritorialMixin, OperativoAbiertoMixin, CreateView):
    """Alta de un sector dentro de un operativo.

    URL: /operativos/<operativo_pk>/sectores/nuevo/

    El operativo viene de la URL y no del formulario. Ver la explicación en
    SectorForm: un campo oculto con el identificador se podría manipular para
    crear sectores en un operativo que el administrador no estaba mirando.
    """

    model = Sector
    form_class = SectorForm
    template_name = "operativos/sector_form.html"

    @cached_property
    def operativo(self):
        return get_object_or_404(Operativo, pk=self.kwargs["operativo_pk"])

    def obtener_operativo_afectado(self):
        return self.operativo

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["operativo"] = self.operativo
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Nuevo sector en {self.operativo.nombre}"
        contexto["operativo"] = self.operativo
        contexto["es_creacion"] = True
        # Si no hay comunas activas el desplegable saldría vacío y nadie
        # entendería por qué. La plantilla lo avisa y ofrece el enlace para crear
        # una.
        contexto["hay_comunas"] = Comuna.objects.filter(activa=True).exists()
        return contexto

    def form_valid(self, formulario):
        with transaction.atomic():
            sector = formulario.save()
            registrar_accion(
                administrador=self.request.user,
                accion=AccionAuditoria.CREAR_TERRITORIO,
                objeto_territorial=sector,
                detalle=f"Sector creado en el operativo «{self.operativo.nombre}».",
                request=self.request,
            )

        messages.success(
            self.request,
            f"Sector «{sector.nombre}» creado. Divídelo en zonas para repartir el "
            "trabajo.",
        )
        return redirect(self.operativo.get_absolute_url())


class SectorUpdateView(
    GestionTerritorialMixin, OperativoAbiertoMixin, ObjetoCacheadoMixin, UpdateView
):
    """Edición de un sector. URL: /operativos/sectores/<pk>/editar/"""

    model = Sector
    form_class = SectorForm
    template_name = "operativos/sector_form.html"

    def get_queryset(self):
        return Sector.objects.select_related("operativo", "comuna", "comuna__region")

    def obtener_operativo_afectado(self):
        return self.objeto.operativo

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["operativo"] = self.objeto.operativo
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Editar {self.object.nombre}"
        contexto["operativo"] = self.object.operativo
        contexto["es_creacion"] = False
        contexto["hay_comunas"] = True
        return contexto

    def form_valid(self, formulario):
        detalle = describir_cambios(formulario)

        with transaction.atomic():
            sector = formulario.save()
            if detalle:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.EDITAR_TERRITORIO,
                    objeto_territorial=sector,
                    detalle=detalle,
                    request=self.request,
                )

        if detalle:
            messages.success(self.request, f"Sector «{sector.nombre}» actualizado.")
        else:
            messages.info(self.request, "No hiciste ningún cambio.")

        return redirect(sector.operativo.get_absolute_url())


class SectorCambiarEstadoView(GestionTerritorialMixin, OperativoAbiertoMixin, View):
    """Activa o desactiva un sector. GET confirma, POST ejecuta."""

    template_name = "operativos/sector_confirmar_estado.html"
    activar = False

    @cached_property
    def sector(self):
        return get_object_or_404(
            Sector.objects.select_related("operativo", "comuna"), pk=self.kwargs["pk"]
        )

    def obtener_operativo_afectado(self):
        return self.sector.operativo

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.contexto())

    def post(self, request, *args, **kwargs):
        sector = self.sector

        if sector.activo == self.activar:
            messages.info(
                request,
                f"El sector «{sector.nombre}» ya estaba "
                f"{'activo' if self.activar else 'desactivado'}.",
            )
            return redirect(sector.operativo.get_absolute_url())

        with transaction.atomic():
            sector.activo = self.activar
            sector.save(update_fields=["activo", "actualizado_en"])

            registrar_accion(
                administrador=request.user,
                accion=(
                    AccionAuditoria.ACTIVAR_TERRITORIO
                    if self.activar
                    else AccionAuditoria.DESACTIVAR_TERRITORIO
                ),
                objeto_territorial=sector,
                detalle=(
                    f"Sector {'activado' if self.activar else 'desactivado'} en el "
                    f"operativo «{sector.operativo.nombre}». Sus "
                    f"{sector.total_zonas()} zona(s) se conservan."
                ),
                request=request,
            )

        messages.success(
            request,
            f"Sector «{sector.nombre}» "
            f"{'activado' if self.activar else 'desactivado'}. Sus zonas y su "
            "historial se conservan.",
        )
        return redirect(sector.operativo.get_absolute_url())

    def contexto(self):
        return {
            "titulo_pagina": (
                f"{'Activar' if self.activar else 'Desactivar'} {self.sector.nombre}"
            ),
            "sector": self.sector,
            "operativo": self.sector.operativo,
            "activar": self.activar,
            "total_zonas": self.sector.total_zonas(),
        }


# ==========================================================================
# 7. ZONAS
# ==========================================================================


class ZonaCreateView(GestionTerritorialMixin, OperativoAbiertoMixin, CreateView):
    """Alta de una zona dentro de un sector.

    URL: /operativos/sectores/<sector_pk>/zonas/nueva/
    """

    model = Zona
    form_class = ZonaForm
    template_name = "operativos/zona_form.html"

    @cached_property
    def sector(self):
        return get_object_or_404(
            Sector.objects.select_related("operativo", "comuna"),
            pk=self.kwargs["sector_pk"],
        )

    def obtener_operativo_afectado(self):
        return self.sector.operativo

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sector"] = self.sector
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Nueva zona en {self.sector.nombre}"
        contexto["sector"] = self.sector
        contexto["operativo"] = self.sector.operativo
        contexto["es_creacion"] = True
        return contexto

    def form_valid(self, formulario):
        with transaction.atomic():
            zona = formulario.save()
            registrar_accion(
                administrador=self.request.user,
                accion=AccionAuditoria.CREAR_TERRITORIO,
                objeto_territorial=zona,
                detalle=f"Zona creada en el sector «{self.sector.nombre}».",
                request=self.request,
            )

        messages.success(self.request, f"Zona «{zona.nombre}» creada.")
        return redirect(self.sector.operativo.get_absolute_url())


class ZonaUpdateView(
    GestionTerritorialMixin, OperativoAbiertoMixin, ObjetoCacheadoMixin, UpdateView
):
    """Edición de una zona. URL: /operativos/zonas/<pk>/editar/"""

    model = Zona
    form_class = ZonaForm
    template_name = "operativos/zona_form.html"

    def get_queryset(self):
        return Zona.objects.select_related(
            "sector", "sector__operativo", "sector__comuna"
        )

    def obtener_operativo_afectado(self):
        return self.objeto.operativo

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sector"] = self.objeto.sector
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = f"Editar {self.object.nombre}"
        contexto["sector"] = self.object.sector
        contexto["operativo"] = self.object.operativo
        contexto["es_creacion"] = False
        return contexto

    def form_valid(self, formulario):
        detalle = describir_cambios(formulario)

        with transaction.atomic():
            zona = formulario.save()
            if detalle:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.EDITAR_TERRITORIO,
                    objeto_territorial=zona,
                    detalle=detalle,
                    request=self.request,
                )

        if detalle:
            messages.success(self.request, f"Zona «{zona.nombre}» actualizada.")
        else:
            messages.info(self.request, "No hiciste ningún cambio.")

        return redirect(zona.operativo.get_absolute_url())


class ZonaCambiarEstadoView(GestionTerritorialMixin, OperativoAbiertoMixin, View):
    """Activa o desactiva una zona. GET confirma, POST ejecuta."""

    template_name = "operativos/zona_confirmar_estado.html"
    activar = False

    @cached_property
    def zona(self):
        return get_object_or_404(
            Zona.objects.select_related(
                "sector", "sector__operativo", "sector__comuna"
            ),
            pk=self.kwargs["pk"],
        )

    def obtener_operativo_afectado(self):
        return self.zona.operativo

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.contexto())

    def post(self, request, *args, **kwargs):
        zona = self.zona

        if zona.activa == self.activar:
            messages.info(
                request,
                f"La zona «{zona.nombre}» ya estaba "
                f"{'activa' if self.activar else 'desactivada'}.",
            )
            return redirect(zona.operativo.get_absolute_url())

        with transaction.atomic():
            zona.activa = self.activar
            zona.save(update_fields=["activa", "actualizado_en"])

            registrar_accion(
                administrador=request.user,
                accion=(
                    AccionAuditoria.ACTIVAR_TERRITORIO
                    if self.activar
                    else AccionAuditoria.DESACTIVAR_TERRITORIO
                ),
                objeto_territorial=zona,
                detalle=(
                    f"Zona {'activada' if self.activar else 'desactivada'} en el "
                    f"sector «{zona.sector.nombre}»."
                ),
                request=request,
            )

        messages.success(
            request,
            f"Zona «{zona.nombre}» {'activada' if self.activar else 'desactivada'}.",
        )
        return redirect(zona.operativo.get_absolute_url())

    def contexto(self):
        return {
            "titulo_pagina": (
                f"{'Activar' if self.activar else 'Desactivar'} {self.zona.nombre}"
            ),
            "zona": self.zona,
            "sector": self.zona.sector,
            "operativo": self.zona.operativo,
            "activar": self.activar,
        }
