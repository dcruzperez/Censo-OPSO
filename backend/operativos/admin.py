"""Registro de los modelos territoriales en el panel de administración (HU-05).

¿QUÉ SENTIDO TIENE EL ADMIN SI YA HAY PANTALLAS PROPIAS?

Cumplen funciones distintas, igual que en la HU-04 con los permisos:

  Las pantallas de OPSO (/operativos/) son la herramienta de OPERACIÓN. Validan
  las reglas del negocio, dejan auditoría y explican las consecuencias antes de
  cada cambio. Es donde se planifica un operativo de verdad.

  El admin es la herramienta TÉCNICA de respaldo: consultar la tabla en crudo,
  corregir un dato a mano si hiciera falta, o revisar qué se sembró. No deja
  auditoría de OPSO (solo el log del propio admin) y por eso NO es el camino
  habitual.

Region se registra en modo SOLO LECTURA. Es coherente con la decisión del modelo:
las regiones de Chile no las administra un usuario de OPSO, las define la ley. Si
se creara una nueva se agrega con una migración de datos, que queda versionada en
Git; permitir crearlas aquí invitaría a inventar una región y ensuciar los datos
sin dejar rastro.
"""

from django.contrib import admin

from .models import AsignacionSector, Comuna, Operativo, Region, Sector, Zona


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    """Catálogo de regiones: se consulta, no se edita.

    Los tres has_*_permission devuelven False para que el admin no ofrezca
    botones de crear, editar ni borrar. Se hace así, y no solo poniendo todos los
    campos en readonly_fields, porque readonly deja igualmente el botón "Añadir"
    y el de "Eliminar": ocultaría la edición pero no el borrado, que es
    justamente el más grave (PROTECT lo impediría si tuviera comunas, pero una
    región sin comunas sí se podría borrar).
    """

    list_display = ("nombre", "codigo", "orden", "total_comunas")
    search_fields = ("nombre", "codigo")
    ordering = ("orden",)

    @admin.display(description="comunas registradas")
    def total_comunas(self, obj):
        return obj.comunas.count()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comuna)
class ComunaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "region", "activa", "total_sectores")
    list_filter = ("activa", "region")
    search_fields = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")
    # La región es una clave foránea a un catálogo de 16 filas: el desplegable
    # normal es perfecto. No hace falta raw_id_fields.
    ordering = ("region__orden", "nombre")

    @admin.display(description="sectores que la usan")
    def total_sectores(self, obj):
        return obj.sectores.count()


class ZonaInline(admin.TabularInline):
    """Las zonas se editan DENTRO de su sector.

    Un inline es lo correcto aquí porque una zona no tiene existencia
    independiente: es una subdivisión de un sector concreto. Verlas en su propia
    pantalla obligaría a elegir el sector en un desplegable cada vez, que es
    justo el paso donde se equivoca uno.
    """

    model = Zona
    extra = 0
    fields = ("nombre", "descripcion", "viviendas_estimadas", "activa")


class AsignacionSectorInline(admin.TabularInline):
    """El equipo de un sector, visible desde su ficha (HU-06).

    Se muestran también las asignaciones históricas (activa=False), a diferencia de
    la pantalla de OPSO, que solo ofrece las vigentes. El admin es la herramienta
    técnica: aquí interesa ver el registro completo del reparto, incluida la gente
    que pasó por el sector y ya no está.
    """

    model = AsignacionSector
    extra = 0
    fields = ("censista", "activa", "asignado_por", "asignado_en", "desasignado_en")
    readonly_fields = ("asignado_en",)
    autocomplete_fields = ("censista", "asignado_por")


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "comuna",
        "operativo",
        "activo",
        "total_zonas",
        "total_asignados",
    )
    list_filter = ("activo", "operativo", "comuna__region")
    search_fields = ("nombre", "comuna__nombre", "operativo__nombre")
    readonly_fields = ("creado_en", "actualizado_en")
    inlines = (ZonaInline, AsignacionSectorInline)
    # select_related en el listado: sin esto, mostrar la comuna y el operativo de
    # cada fila costaría dos consultas por fila.
    list_select_related = ("comuna", "operativo")

    @admin.display(description="zonas")
    def total_zonas(self, obj):
        return obj.zonas.count()

    @admin.display(description="censistas a cargo")
    def total_asignados(self, obj):
        return obj.asignaciones.filter(activa=True).count()


class SectorInline(admin.TabularInline):
    """Los sectores de un operativo, visibles desde su ficha.

    show_change_link deja un enlace a la pantalla completa del sector, que es
    donde están sus zonas: un inline dentro de otro inline no lo permite Django,
    y tampoco se leería.
    """

    model = Sector
    extra = 0
    fields = ("nombre", "comuna", "activo")
    show_change_link = True


@admin.register(Operativo)
class OperativoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "fecha_inicio",
        "fecha_termino",
        "estado",
        "total_sectores",
        "creado_por",
    )
    list_filter = ("estado",)
    search_fields = ("nombre", "descripcion")
    readonly_fields = ("creado_en", "actualizado_en")
    date_hierarchy = "fecha_inicio"
    inlines = (SectorInline,)
    list_select_related = ("creado_por",)

    @admin.display(description="sectores")
    def total_sectores(self, obj):
        return obj.sectores.count()


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    """Las zonas también tienen su propia pantalla, además del inline.

    Sirve para lo que el inline no permite: buscar una zona por nombre entre
    todos los operativos, o filtrar todas las que están desactivadas. Es una
    herramienta de consulta técnica, no el camino para crearlas.
    """

    list_display = ("nombre", "sector", "comuna", "viviendas_estimadas", "activa")
    list_filter = ("activa", "sector__operativo")
    search_fields = ("nombre", "sector__nombre")
    readonly_fields = ("creado_en", "actualizado_en")
    list_select_related = ("sector", "sector__comuna")

    @admin.display(description="comuna", ordering="sector__comuna__nombre")
    def comuna(self, obj):
        return obj.sector.comuna.nombre


@admin.register(AsignacionSector)
class AsignacionSectorAdmin(admin.ModelAdmin):
    """El reparto del trabajo, con su historial completo (HU-06).

    La pantalla propia existe para lo que el inline del sector no permite: buscar
    todos los sectores de una persona, o revisar quién repartió qué. Es consulta
    técnica; el reparto del día a día se hace en /operativos/<pk>/asignaciones/,
    que valida las reglas del negocio y deja auditoría.
    """

    list_display = (
        "censista",
        "sector",
        "operativo",
        "activa",
        "asignado_en",
        "desasignado_en",
        "asignado_por",
    )
    list_filter = ("activa", "sector__operativo", "sector__comuna__region")
    search_fields = (
        "censista__email",
        "censista__first_name",
        "censista__last_name",
        "sector__nombre",
    )
    readonly_fields = ("asignado_en",)
    autocomplete_fields = ("censista", "asignado_por", "sector")
    # Sin esto, mostrar el sector, su operativo y las dos personas de cada fila
    # costaría cuatro consultas por fila.
    list_select_related = (
        "censista",
        "sector",
        "sector__operativo",
        "asignado_por",
    )

    @admin.display(description="operativo", ordering="sector__operativo__nombre")
    def operativo(self, obj):
        return obj.sector.operativo.nombre
