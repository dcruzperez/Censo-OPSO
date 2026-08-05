"""Registro de las encuestas en el panel de administración (HU-07 y HU-08).

Mismo reparto de funciones que explicó la HU-05 al registrar el territorio: las
pantallas de OPSO son la herramienta de OPERACIÓN y el admin es la herramienta
TÉCNICA de respaldo.

Desde la HU-08 el registro de una vivienda y de su grupo familiar SÍ tiene
pantalla propia (`/encuestas/viviendas/nueva/`), que es la que valida las reglas
del negocio: que la zona sea de un sector asignado, que el operativo esté abierto
y que la encuesta admita cambios. Nada de eso lo comprueba el admin, y por eso no
es el camino habitual.
"""

from django.contrib import admin

from .models import Encuesta, Fotografia, GrupoFamiliar, Integrante, Vivienda


class FotografiaInline(admin.TabularInline):
    """Las fotografías, dentro de su vivienda (HU-12).

    No se registra Fotografia con pantalla propia, al contrario que los demás
    modelos del módulo. Es deliberado: una pantalla que lista TODAS las fotografías
    del operativo es un álbum de casas de familias, y no hay ninguna tarea que la
    necesite. Desde la vivienda se ven las suyas, que es como se consultan.
    """

    model = Fotografia
    extra = 0
    fields = ("imagen", "tipo", "descripcion", "tomada_por", "tomada_en")
    readonly_fields = ("tomada_en",)
    autocomplete_fields = ("tomada_por",)


class EncuestaInline(admin.TabularInline):
    """Los hogares de una vivienda, visibles desde su ficha.

    Un inline es lo correcto aquí por lo mismo que ZonaInline en la HU-05: una
    encuesta no tiene sentido sin su vivienda. Y es además la forma más directa de
    ver el caso que la HU-08 vino a modelar bien: dos hogares colgando de la misma
    casa.
    """

    model = Encuesta
    extra = 0
    fields = ("censista", "estado", "iniciada_en", "cerrada_en")
    readonly_fields = ("iniciada_en", "cerrada_en")
    autocomplete_fields = ("censista",)
    show_change_link = True


@admin.register(Vivienda)
class ViviendaAdmin(admin.ModelAdmin):
    list_display = (
        "direccion",
        "zona",
        "sector",
        "tipo",
        "datos_completos",
        "total_hogares",
    )
    list_filter = (
        "tipo",
        "tenencia",
        "zona__sector__operativo",
        "zona__sector__comuna__region",
    )
    search_fields = ("direccion", "referencia", "zona__nombre", "zona__sector__nombre")
    readonly_fields = ("creada_en", "actualizada_en")
    autocomplete_fields = ("zona", "registrada_por")
    inlines = (EncuestaInline, FotografiaInline)
    list_select_related = ("zona", "zona__sector")

    @admin.display(description="sector", ordering="zona__sector__nombre")
    def sector(self, obj):
        return obj.zona.sector.nombre

    @admin.display(description="descrita", boolean=True)
    def datos_completos(self, obj):
        return obj.datos_completos

    @admin.display(description="hogares")
    def total_hogares(self, obj):
        return obj.encuestas.count()


class GrupoFamiliarInline(admin.StackedInline):
    """El hogar levantado, dentro de su encuesta.

    Es una relación uno a uno, así que `max_num=1`: ofrecer un segundo formulario
    invitaría a intentar algo que la base de datos va a rechazar.
    """

    model = GrupoFamiliar
    extra = 0
    max_num = 1
    readonly_fields = ("registrado_en", "actualizado_en")


@admin.register(Encuesta)
class EncuestaAdmin(admin.ModelAdmin):
    list_display = (
        "direccion",
        "zona",
        "sector",
        "censista",
        "estado",
        "iniciada_en",
        "cerrada_en",
    )
    list_filter = (
        "estado",
        "vivienda__zona__sector__operativo",
        "vivienda__zona__sector__comuna__region",
    )
    search_fields = (
        "vivienda__direccion",
        "vivienda__referencia",
        "censista__email",
        "censista__first_name",
        "censista__last_name",
        "vivienda__zona__nombre",
        "vivienda__zona__sector__nombre",
    )
    readonly_fields = ("creada_en", "actualizada_en")
    # La vivienda y las personas se eligen por autocompletado y no con un
    # desplegable: en un operativo real hay cientos de viviendas, y un <select>
    # con cientos de opciones es donde se elige la de al lado por error.
    autocomplete_fields = ("vivienda", "censista", "asignada_por")
    date_hierarchy = "creada_en"
    inlines = (GrupoFamiliarInline,)
    # Sin esto, mostrar la dirección, la zona, el sector y el encuestador de cada
    # fila costaría cuatro consultas por fila. `direccion` y `zona` son propiedades
    # que leen la vivienda, así que el select_related es imprescindible.
    list_select_related = (
        "vivienda",
        "vivienda__zona",
        "vivienda__zona__sector",
        "censista",
    )

    @admin.display(description="dirección", ordering="vivienda__direccion")
    def direccion(self, obj):
        return obj.vivienda.direccion

    @admin.display(description="zona", ordering="vivienda__zona__nombre")
    def zona(self, obj):
        return obj.vivienda.zona.nombre

    @admin.display(description="sector", ordering="vivienda__zona__sector__nombre")
    def sector(self, obj):
        return obj.vivienda.zona.sector.nombre


class IntegranteInline(admin.TabularInline):
    """Las personas del hogar, dentro de su hogar (HU-09).

    Un inline es lo correcto por lo mismo que ZonaInline en la HU-05: una persona
    de este modelo no tiene existencia independiente, es un integrante DE un hogar
    concreto. Verlas en su propia pantalla obligaría a elegir el hogar en un
    desplegable cada vez, que es justo donde se equivoca uno.
    """

    model = Integrante
    extra = 0
    fields = (
        "parentesco",
        "nombres",
        "apellidos",
        "rut",
        "sexo",
        "fecha_nacimiento",
        "nivel_educacional",
        "situacion_ocupacional",
    )


@admin.register(GrupoFamiliar)
class GrupoFamiliarAdmin(admin.ModelAdmin):
    """Los hogares levantados, con su propia pantalla además del inline.

    Sirve para lo que el inline no permite: buscar un jefe de hogar por nombre
    entre todos los operativos. Es consulta técnica sobre datos personales, así que
    la protege el mismo `is_staff` que el resto del admin.
    """

    list_display = (
        "jefe_hogar_nombre",
        "direccion",
        "integrantes_declarados",
        "registradas",
        "ingreso_mensual",
        "registrado_en",
    )
    list_filter = ("encuesta__estado", "encuesta__vivienda__zona__sector__operativo")
    search_fields = (
        "jefe_hogar_nombre",
        "jefe_hogar_rut",
        "encuesta__vivienda__direccion",
    )
    readonly_fields = ("registrado_en", "actualizado_en")
    autocomplete_fields = ("encuesta",)
    inlines = (IntegranteInline,)
    list_select_related = ("encuesta", "encuesta__vivienda")

    @admin.display(description="dirección")
    def direccion(self, obj):
        return obj.encuesta.vivienda.direccion

    @admin.display(description="personas registradas")
    def registradas(self, obj):
        return obj.integrantes.count()


@admin.register(Integrante)
class IntegranteAdmin(admin.ModelAdmin):
    """Las personas, con su propia pantalla además del inline.

    Sirve para lo que el inline no permite: buscar a una persona por RUT entre
    todos los operativos, o revisar cuántos menores hay en una zona. Es consulta
    técnica sobre datos personales de terceros, así que la protege el mismo
    `is_staff` que el resto del admin.
    """

    list_display = (
        "nombre_completo",
        "parentesco",
        "edad",
        "sexo",
        "hogar",
        "direccion",
    )
    list_filter = (
        "parentesco",
        "sexo",
        "nivel_educacional",
        "situacion_ocupacional",
        "tiene_discapacidad",
        "grupo_familiar__encuesta__vivienda__zona__sector__operativo",
    )
    search_fields = (
        "nombres",
        "apellidos",
        "rut",
        "grupo_familiar__jefe_hogar_nombre",
        "grupo_familiar__encuesta__vivienda__direccion",
    )
    readonly_fields = ("registrado_en", "actualizado_en")
    autocomplete_fields = ("grupo_familiar",)
    list_select_related = (
        "grupo_familiar",
        "grupo_familiar__encuesta",
        "grupo_familiar__encuesta__vivienda",
    )

    @admin.display(description="hogar")
    def hogar(self, obj):
        return obj.grupo_familiar.jefe_hogar_nombre

    @admin.display(description="dirección")
    def direccion(self, obj):
        return obj.grupo_familiar.encuesta.vivienda.direccion
