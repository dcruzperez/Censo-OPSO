"""HU-11: la ubicación geográfica de la vivienda.

Cinco columnas y dos restricciones, todas sobre `fichas_vivienda`. Las
explicaciones están junto a cada campo en fichas/models.py; aquí interesan las dos
restricciones, porque son las que hacen el trabajo de «validar su ubicación
geográfica» que pide la historia.

  vivienda_coordenadas_completas -> latitud y longitud van juntas o no va ninguna.
                                    Media coordenada no ubica nada: una latitud sin
                                    longitud es una línea que cruza el planeta. Sin
                                    la restricción quedarían filas que PARECEN
                                    tener ubicación, y un mapa las dibujaría en
                                    cualquier parte.

  vivienda_coordenadas_en_chile  -> el punto cae dentro del territorio nacional.
                                    Atrapa los dos errores habituales al escribir
                                    coordenadas a mano: olvidar el signo (una
                                    latitud +36 en vez de -36 pone la vivienda en
                                    Argelia) e intercambiar latitud y longitud.

El rango de la segunda incluye el territorio INSULAR, no solo el continental. Si se
acotara a la longitud de Chile continental (-76 a -66), Rapa Nui (-109,4) quedaría
fuera, y es territorio nacional donde puede haber un operativo. Un límite que
rechaza datos verdaderos es peor que no tenerlo.

No hay datos que migrar: las columnas nacen vacías y las viviendas ya registradas
quedan «sin ubicación», que es la verdad. La pantalla lo muestra así y ofrece
capturarla al volver a pasar por la puerta.
"""

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fichas', '0004_borradores_y_cierre'),
        ('operativos', '0003_asignaciones'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='vivienda',
            name='latitud',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Grados decimales. En Chile siempre es negativa.', max_digits=9, null=True, verbose_name='latitud'),
        ),
        migrations.AddField(
            model_name='vivienda',
            name='longitud',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Grados decimales. En Chile siempre es negativa.', max_digits=9, null=True, verbose_name='longitud'),
        ),
        migrations.AddField(
            model_name='vivienda',
            name='precision_metros',
            field=models.PositiveIntegerField(blank=True, help_text='Radio de error en metros que informó el aparato. Sin este dato, un punto tomado dentro de una casa parece tan bueno como uno tomado en la calle.', null=True, verbose_name='precisión'),
        ),
        migrations.AddField(
            model_name='vivienda',
            name='ubicacion_capturada_en',
            field=models.DateTimeField(blank=True, help_text='Cuándo se tomó el punto.', null=True, verbose_name='ubicación capturada en'),
        ),
        migrations.AddField(
            model_name='vivienda',
            name='ubicacion_manual',
            field=models.BooleanField(default=False, help_text='True si las coordenadas se escribieron en vez de capturarlas del aparato. Un punto escrito a mano no tiene la misma confianza.', verbose_name='ubicación escrita a mano'),
        ),
        migrations.AddConstraint(
            model_name='vivienda',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('latitud__isnull', True), ('longitud__isnull', True)), models.Q(('latitud__isnull', False), ('longitud__isnull', False)), _connector='OR'), name='vivienda_coordenadas_completas'),
        ),
        migrations.AddConstraint(
            model_name='vivienda',
            constraint=models.CheckConstraint(condition=models.Q(('latitud__isnull', True), models.Q(('latitud__gte', Decimal('-56.6')), ('latitud__lte', Decimal('-17.4')), ('longitud__gte', Decimal('-109.6')), ('longitud__lte', Decimal('-66.3'))), _connector='OR'), name='vivienda_coordenadas_en_chile'),
        ),
    ]
