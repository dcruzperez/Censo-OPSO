"""Migración de DATOS de la HU-05: siembra las 16 regiones de Chile.

Mismo criterio que 0002_roles_iniciales y 0005_permisos_iniciales de la app
usuarios: los datos que el sistema necesita para funcionar son parte del código,
no algo que alguien tenga que escribir a mano en pgAdmin. Las ventajas son las
mismas tres:

  REPRODUCIBILIDAD -> cualquier persona que clone el repositorio y migre obtiene
                      exactamente las mismas 16 filas, con los mismos códigos.
  VERSIONADO       -> si mañana cambia el nombre oficial de una región, el cambio
                      queda en Git con fecha, autor y motivo.
  PRUEBAS          -> la base de datos de prueba se crea aplicando migraciones,
                      así que las regiones están disponibles en cada test sin
                      necesidad de fixtures.

--------------------------------------------------------------------------
¿POR QUÉ LAS REGIONES SE SIEMBRAN Y LAS COMUNAS NO?
--------------------------------------------------------------------------
Son 16 contra 346, y cumplen funciones distintas.

La región solo AGRUPA: nadie trabaja "en la Región del Biobío", se trabaja en
Concepción. Sembrar las 16 no ensucia nada y evita el problema real que tendría
el texto libre: que "Biobío", "Bío-Bío" y "VIII Región" convivieran como si
fueran tres regiones distintas y los listados agrupados dejaran de servir.

Las comunas, en cambio, son el lugar donde efectivamente se despliega el
operativo, y OPSO trabaja en unas pocas. Sembrar las 346 obligaría al
administrador a buscar entre 346 opciones las 4 que le interesan, y a los
reportes a mostrar 342 comunas sin una sola ficha. Por eso las da de alta él:
la lista queda corta y significa algo ("estas son las comunas de OPSO").

--------------------------------------------------------------------------
EL ORDEN: DE NORTE A SUR, NO ALFABÉTICO
--------------------------------------------------------------------------
El campo "orden" reproduce la secuencia geográfica con que se nombran las
regiones en Chile, de Arica al extremo austral. Es el orden en que cualquier
persona del país espera encontrarlas en un desplegable; el alfabético pondría
Antofagasta primero y Ñuble entre Metropolitana y Los Lagos, lo que obliga a
buscar en vez de recorrer.

Nótese que el orden geográfico NO coincide con el código: la Región Metropolitana
tiene el código 13 pero va en séptimo lugar, y Ñuble (16, creada en 2018) va
décima, entre Maule y Biobío. Por eso hacen falta las dos columnas: el código es
el identificador oficial y el orden es la presentación.

--------------------------------------------------------------------------
LOS CÓDIGOS
--------------------------------------------------------------------------
Son los códigos oficiales del Instituto Nacional de Estadísticas (INE), con dos
dígitos y cero a la izquierda. Se guardan como TEXTO y no como número entero por
una razón concreta: el cero de "08" es parte del código, y un entero lo perdería.
Además nunca se hace aritmética con ellos.

Igual que en las migraciones de datos anteriores, los valores se escriben como
literales y no importando nada desde models.py: una migración es la foto de un
momento y debe seguir aplicándose aunque el código del modelo cambie después.
"""

from django.db import migrations

# --------------------------------------------------------------------------
# (código INE, nombre oficial, orden geográfico norte -> sur)
# --------------------------------------------------------------------------
REGIONES = [
    ("15", "Región de Arica y Parinacota", 10),
    ("01", "Región de Tarapacá", 20),
    ("02", "Región de Antofagasta", 30),
    ("03", "Región de Atacama", 40),
    ("04", "Región de Coquimbo", 50),
    ("05", "Región de Valparaíso", 60),
    ("13", "Región Metropolitana de Santiago", 70),
    ("06", "Región del Libertador General Bernardo O'Higgins", 80),
    ("07", "Región del Maule", 90),
    ("16", "Región de Ñuble", 100),
    ("08", "Región del Biobío", 110),
    ("09", "Región de La Araucanía", 120),
    ("14", "Región de Los Ríos", 130),
    ("10", "Región de Los Lagos", 140),
    ("11", "Región de Aysén del General Carlos Ibáñez del Campo", 150),
    ("12", "Región de Magallanes y de la Antártica Chilena", 160),
]


def sembrar_regiones(apps, schema_editor):
    """Crea las 16 regiones si no existen.

    Se usa apps.get_model() y NO se importa Region desde operativos.models. Es
    la regla de oro de las migraciones de datos: aquí hay que trabajar con el
    modelo tal como era EN ESTE PUNTO de la historia. Si se importara la clase
    real, el día que el modelo gane un campo obligatorio esta migración
    empezaría a fallar al reconstruir la base desde cero.

    update_or_create y no create: hace la migración IDEMPOTENTE. Si alguien ya
    había insertado alguna región a mano, se actualiza en vez de estallar con un
    error de clave duplicada. El código es la clave de búsqueda porque es el
    identificador oficial y estable; el nombre puede corregirse.
    """
    Region = apps.get_model("operativos", "Region")

    for codigo, nombre, orden in REGIONES:
        Region.objects.update_or_create(
            codigo=codigo,
            defaults={"nombre": nombre, "orden": orden},
        )


def borrar_regiones(apps, schema_editor):
    """Revierte la siembra, pero solo si ninguna región está en uso.

    Una migración que no se puede revertir bloquea el desarrollo: basta un error
    en la siguiente para quedar sin camino de vuelta. Pero revertir a ciegas
    sería peor: si ya hay comunas colgando de una región, borrarla fallaría por
    la clave foránea PROTECT, o peor, arrastraría datos reales.

    Por eso se borran solo las regiones SIN comunas. Las que estén en uso se
    conservan, y la migración inversa termina bien igualmente: el estado
    resultante es coherente y no se pierde nada que alguien haya creado.
    """
    Region = apps.get_model("operativos", "Region")
    Region.objects.filter(comunas__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operativos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sembrar_regiones, borrar_regiones),
    ]
