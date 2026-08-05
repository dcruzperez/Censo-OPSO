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


