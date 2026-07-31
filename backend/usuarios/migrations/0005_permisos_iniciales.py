"""Migración de DATOS de la HU-04: siembra el catálogo de permisos.

Mismo criterio que 0002_roles_iniciales: los permisos son parte del código, no
datos que alguien tenga que escribir a mano en pgAdmin. Ventajas idénticas —
reproducibilidad, versionado en Git y disponibilidad automática en la base de
datos de prueba.

Igual que en 0002, los valores se escriben como TEXTO y no importando
ModuloPermiso desde models.py: una migración es la foto de un momento y debe
seguir aplicándose aunque el código del modelo cambie más adelante.

--------------------------------------------------------------------------
¿POR QUÉ ESTOS PERMISOS Y NO OTROS?
--------------------------------------------------------------------------
No se inventaron: salen de dos fuentes que ya existen en el proyecto.

  a) Los módulos YA IMPLEMENTADOS (usuarios, auditoría, roles), cuyas acciones
     son exactamente las rutas que hoy protege SoloAdministradorMixin.
  b) Las DESCRIPCIONES DE LOS ROLES sembradas en 0002, que ya nombran el trabajo
     de terreno: "valida las fichas levantadas por los censistas", "asigna
     sectores", "accede a todos los reportes". Esas frases se traducen aquí a
     permisos concretos.

Por eso el catálogo incluye permisos de módulos que todavía no tienen pantallas
(fichas, operativos, reportes). Es deliberado y es la demostración de la ventaja
del diseño: cuando esas historias se implementen, la autorización ya está
modelada y solo hay que consultarla. Un permiso sin pantalla no autoriza nada
—no hay vista que lo compruebe—, así que no abre ningún hueco de seguridad.

--------------------------------------------------------------------------
ASIGNACIÓN INICIAL
--------------------------------------------------------------------------
Se aplica el PRINCIPIO DE MÍNIMO PRIVILEGIO: cada rol recibe lo mínimo que
necesita para su trabajo, no todo lo que podría llegar a necesitar.

  ADMINISTRADOR -> todos. Coherente con Usuario.tiene_permiso(), que se los
                   concede de forma implícita; sembrarlos hace que la matriz
                   muestre la verdad en vez de una fila vacía engañosa.
  SUPERVISOR    -> ver el trabajo de terreno, validarlo y reportar. NO administra
                   cuentas ni permisos: si necesitara crear un censista, lo pide
                   al administrador. Así una cuenta de supervisor comprometida no
                   permite fabricar usuarios nuevos ni ampliar privilegios.
  CENSISTA      -> solo sus propias fichas. Ni ve las de otros ni valida nada,
                   porque validar su propio trabajo anularía el control cruzado.

El reparto inicial reproduce EXACTAMENTE el acceso que el sistema ya tenía antes
de esta historia, cuando estaba escrito a mano en cada vista. Eso es deliberado:
una migración de este tipo no debe cambiar quién puede hacer qué, solo trasladar
dónde está escrita la regla. Lo que cambia es que a partir de ahora el reparto se
puede ajustar desde la matriz, sin tocar código.
"""

from django.db import migrations

# --------------------------------------------------------------------------
# CATÁLOGO
# El campo "orden" ordena de menos a más poder dentro de cada módulo (ver antes
# que crear, crear antes que borrar), que es como se lee una matriz de permisos.
# --------------------------------------------------------------------------
PERMISOS = [
    # --- Usuarios (HU-03, ya implementado) ---
    ("usuarios.ver", "Ver el listado y las fichas de usuarios", "USUARIOS", 10,
     "Consultar quién tiene cuenta, con qué rol y en qué estado."),
    ("usuarios.crear", "Crear cuentas de usuario", "USUARIOS", 20,
     "Dar de alta una cuenta nueva y enviarle el enlace para definir su contraseña."),
    ("usuarios.editar", "Editar los datos de una cuenta", "USUARIOS", 30,
     "Modificar nombre, correo, RUT, teléfono y el rol asignado."),
    ("usuarios.cambiar_estado", "Habilitar o deshabilitar cuentas", "USUARIOS", 40,
     "Cortar o devolver el acceso conservando todos los datos de la persona."),
    ("usuarios.enviar_enlace", "Reenviar el enlace de contraseña", "USUARIOS", 50,
     "Enviar de nuevo el correo con el enlace para definir la contraseña."),

    # --- Roles y permisos (HU-04, esta historia) ---
    ("roles.ver", "Consultar los roles y sus permisos", "ROLES", 10,
     "Ver la matriz de permisos sin poder modificarla."),
    ("roles.asignar_permisos", "Modificar los permisos de los roles", "ROLES", 20,
     "Conceder o revocar permisos en la matriz. Es el permiso más delicado del "
     "sistema: quien lo tiene puede ampliar los privilegios de cualquier rol."),

    # --- Auditoría (HU-01 y HU-03, ya implementado) ---
    ("auditoria.ver", "Consultar la bitácora de acciones administrativas", "AUDITORIA", 10,
     "Ver quién creó, editó, habilitó o deshabilitó cuentas, y cuándo."),
    ("auditoria.ver_accesos", "Consultar la bitácora de intentos de acceso", "AUDITORIA", 20,
     "Ver quién intentó entrar al sistema, desde qué IP y con qué resultado."),

    # --- Fichas de familias (historia futura) ---
    ("fichas.ver_propias", "Ver las fichas que levantó la propia persona", "FICHAS", 10,
     "Acceso a las fichas de las que es autor, y solo a esas."),
    ("fichas.ver_todas", "Ver las fichas de todo el operativo", "FICHAS", 20,
     "Acceso a las fichas levantadas por cualquier censista."),
    ("fichas.crear", "Registrar una ficha nueva", "FICHAS", 30,
     "Levantar la información de una familia en terreno."),
    ("fichas.editar", "Corregir una ficha", "FICHAS", 40,
     "Modificar los datos de una ficha ya registrada."),
    ("fichas.validar", "Validar o rechazar una ficha levantada", "FICHAS", 50,
     "Revisar el trabajo de un censista y aprobarlo o devolverlo con "
     "observaciones. Es el control de calidad del censo."),

    # --- Operativos y sectores (historia futura) ---
    ("operativos.ver", "Consultar los operativos y sectores", "OPERATIVOS", 10,
     "Ver qué operativos existen y cómo está dividido el territorio."),
    ("operativos.asignar_sector", "Asignar censistas a un sector", "OPERATIVOS", 20,
     "Distribuir el trabajo de terreno entre el personal disponible."),
    ("operativos.gestionar", "Crear y configurar operativos y sectores", "OPERATIVOS", 30,
     "Definir el operativo, sus fechas y la división territorial."),

    # --- Reportes (historia futura) ---
    ("reportes.ver", "Consultar los reportes de avance", "REPORTES", 10,
     "Ver el estado del operativo: fichas levantadas, validadas y pendientes."),
    ("reportes.exportar", "Exportar los reportes consolidados", "REPORTES", 20,
     "Descargar la información agregada del censo para su análisis externo."),
]

# --------------------------------------------------------------------------
# ASIGNACIÓN POR ROL
# El administrador no se enumera: recibe todos (ver más abajo).
# --------------------------------------------------------------------------
PERMISOS_SUPERVISOR = [
    # NADA del módulo Usuarios ni del módulo Roles. Es la decisión que la HU-03
    # ya documentó y justificó en su sección "¿Por qué solamente un administrador
    # debe administrar usuarios?": concentrar la gestión de cuentas en un solo
    # perfil reduce la superficie de ataque. Si un supervisor necesita un
    # censista nuevo, lo pide; así una cuenta de supervisor comprometida no
    # permite fabricar usuarios ni ampliar privilegios.
    #
    # El administrador puede concedérselos desde la matriz si algún operativo lo
    # requiere: la decisión queda abierta sin quedar tomada por defecto.
    "fichas.ver_propias",
    "fichas.ver_todas",
    "fichas.validar",
    "operativos.ver",
    "operativos.asignar_sector",
    "reportes.ver",
    "reportes.exportar",
]

PERMISOS_CENSISTA = [
    "fichas.ver_propias",
    "fichas.crear",
    "fichas.editar",
]


def sembrar_permisos(apps, schema_editor):
    """Crea el catálogo y lo reparte entre los tres roles."""
    Permiso = apps.get_model("usuarios", "Permiso")
    Rol = apps.get_model("usuarios", "Rol")

    # 1. El catálogo. update_or_create hace la migración idempotente: se puede
    #    volver a aplicar sin duplicar filas ni chocar con el UNIQUE del código.
    por_codigo = {}
    for codigo, nombre, modulo, orden, descripcion in PERMISOS:
        permiso, _ = Permiso.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "modulo": modulo,
                "orden": orden,
                "descripcion": descripcion,
                "activo": True,
            },
        )
        por_codigo[codigo] = permiso

    # 2. La asignación. Se usa set() y no add(): set() deja EXACTAMENTE los
    #    permisos indicados, así que aplicar la migración dos veces no acumula
    #    permisos de más. add() sería aditivo y el resultado dependería de
    #    cuántas veces se ejecutó.
    asignaciones = {
        "ADMINISTRADOR": list(por_codigo),  # todos
        "SUPERVISOR": PERMISOS_SUPERVISOR,
        "CENSISTA": PERMISOS_CENSISTA,
    }

    for codigo_rol, codigos in asignaciones.items():
        rol = Rol.objects.filter(codigo=codigo_rol).first()
        # Si el rol no existe (base parcialmente migrada o rol borrado a mano)
        # se omite en silencio en vez de romper la migración: el catálogo de
        # permisos es útil igual y 0002 ya se encarga de los roles.
        if rol is None:
            continue
        rol.permisos.set([por_codigo[c] for c in codigos if c in por_codigo])


def borrar_permisos(apps, schema_editor):
    """Operación inversa, para poder revertir con `migrate usuarios 0004`.

    Basta con borrar los permisos: PostgreSQL elimina en cascada las filas de
    usuarios_rol_permisos que los referencian, porque una tabla intermedia de
    muchos-a-muchos no tiene sentido sin sus dos extremos. No hay que limpiarla
    a mano.
    """
    Permiso = apps.get_model("usuarios", "Permiso")
    Permiso.objects.filter(codigo__in=[p[0] for p in PERMISOS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        # Necesita las tablas de 0004 y los roles de 0002 (que 0004 ya arrastra).
        ("usuarios", "0004_permisos"),
    ]

    operations = [
        migrations.RunPython(sembrar_permisos, borrar_permisos),
    ]
