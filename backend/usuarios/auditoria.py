"""Registro de auditoría de la administración de usuarios (HU-03).

¿Por qué un módulo aparte y no código dentro de las vistas?

1. UNA SOLA FORMA DE REGISTRAR. Si cada vista armara su propia fila, tarde o
   temprano una olvidaría la IP o escribiría la acción con otro texto, y la
   bitácora dejaría de ser comparable.
2. SE PUEDE PROBAR SOLO. registrar_accion() es una función normal: una prueba
   la llama y verifica la fila resultante, sin simular una petición HTTP.
3. SE PUEDE REUTILIZAR. Mañana un comando de gestión o una API podrán registrar
   en la misma bitácora con la misma llamada.

Es el mismo criterio que ya se aplicó en la HU-01 con seguridad.py.
"""

import logging

from .models import AccionAuditoria, RegistroAuditoria, TipoObjetoAuditoria
from .seguridad import obtener_ip, obtener_user_agent

logger = logging.getLogger("usuarios")


def registrar_accion(
    administrador,
    accion,
    usuario_afectado=None,
    detalle="",
    request=None,
    rol_afectado=None,
    objeto_territorial=None,
    tipo_objeto=None,
):
    """Escribe una fila en la bitácora de auditoría y la devuelve.

    Parámetros:
        administrador      -> Usuario que ejecuta la acción (request.user).
        accion             -> valor de AccionAuditoria.
        usuario_afectado   -> Usuario sobre el que se actuó (HU-03).
        detalle            -> texto libre con el cambio exacto.
        request            -> para obtener IP y navegador (contexto forense).
        rol_afectado       -> Rol sobre el que se actuó (HU-04: permisos).
        objeto_territorial -> Operativo, Comuna, Sector o Zona (HU-05).
        tipo_objeto        -> valor de TipoObjetoAuditoria. Opcional: si no se
                              indica, se deduce del nombre de la clase del
                              objeto, que es lo correcto en todos los casos
                              reales y ahorra repetirlo en cada llamada.

    Se indica UNO de los tres objetos afectados, no varios: una acción recae
    sobre una cuenta (deshabilitarla), sobre un rol (cambiarle los permisos) o
    sobre un registro territorial (crear un sector). Si no se indica ninguno se
    levanta ValueError en vez de escribir una fila incompleta: una bitácora que
    no dice sobre qué se actuó no sirve de nada, y es mejor que el error salte en
    desarrollo que descubrir el hueco durante una auditoría real.

    Se guardan el correo y los nombres como texto además de las claves foráneas:
    si la cuenta o el rol se eliminaran físicamente algún día, la fila seguiría
    siendo legible (ver la explicación en el modelo RegistroAuditoria).
    """
    if usuario_afectado is None and rol_afectado is None and objeto_territorial is None:
        raise ValueError(
            "registrar_accion() necesita saber sobre qué se actuó: hay que "
            "indicar usuario_afectado, rol_afectado u objeto_territorial."
        )

    objeto_tipo, objeto_id, objeto_nombre = _describir_objeto_territorial(
        objeto_territorial, tipo_objeto
    )

    registro = RegistroAuditoria.objects.create(
        administrador=administrador if getattr(administrador, "pk", None) else None,
        administrador_email=getattr(administrador, "email", "") or "",
        accion=accion,
        usuario_afectado=usuario_afectado,
        usuario_afectado_email=usuario_afectado.email if usuario_afectado else "",
        rol_afectado=rol_afectado,
        rol_afectado_nombre=rol_afectado.nombre if rol_afectado else "",
        objeto_tipo=objeto_tipo,
        objeto_id=objeto_id,
        objeto_nombre=objeto_nombre,
        detalle=detalle,
        ip=obtener_ip(request),
        user_agent=obtener_user_agent(request),
    )

    # El log en texto es un segundo respaldo: si la base de datos se corrompiera
    # o alguien lograra borrar filas, el archivo de log conserva el rastro.
    logger.info(
        "AUDITORÍA | %s | admin=%s | afectado=%s | %s",
        AccionAuditoria(accion).label,
        registro.administrador_email or "(desconocido)",
        registro.objetivo,
        detalle or "sin detalle",
    )
    return registro


def _describir_objeto_territorial(objeto, tipo_objeto=None):
    """Traduce un objeto territorial a la terna (tipo, id, nombre) de la bitácora.

    Se aísla en su propia función por lo mismo que registrar_accion() existe:
    para que la conversión se escriba UNA vez. Si cada vista armara la terna,
    alguna guardaría `str(sector)` ("Los Boldos") en vez de
    `sector.nombre_completo` ("Los Boldos · Concepción"), y la bitácora dejaría
    de ser comparable entre filas.

    El tipo se DEDUCE del nombre de la clase. Es deliberado: obliga a que
    TipoObjetoAuditoria y los modelos de la app operativos usen los mismos
    nombres, y así agregar una entidad territorial no requiere tocar esta
    función. Si el nombre de la clase no está en el catálogo se levanta
    ValueError, porque escribir una fila con el tipo vacío la dejaría fuera de
    cualquier filtro por tipo sin que nadie lo note.
    """
    if objeto is None:
        return "", None, ""

    if tipo_objeto is None:
        nombre_clase = objeto.__class__.__name__.upper()
        if nombre_clase not in TipoObjetoAuditoria.values:
            raise ValueError(
                f"{objeto.__class__.__name__} no está en TipoObjetoAuditoria. "
                "Agrégalo al catálogo o pasa tipo_objeto explícitamente."
            )
        tipo_objeto = nombre_clase

    # nombre_completo cuando el modelo lo define (incluye el camino: la zona con
    # su sector y su comuna); str() en los que no lo necesitan, como Operativo,
    # cuyo nombre ya es único en todo el sistema.
    nombre = getattr(objeto, "nombre_completo", None) or str(objeto)

    return tipo_objeto, objeto.pk, nombre


def describir_cambio_de_conjunto(
    antes, despues, clave, etiqueta, verbo_entra, verbo_sale
):
    """Compara dos conjuntos de objetos y describe qué entró y qué salió.

    Es la parte común de "cambiaron los permisos de un rol" (HU-04) y "cambiaron
    los censistas de un sector" (HU-06). Las dos operaciones son la misma en el
    fondo —se envía el conjunto completo y hay que averiguar la diferencia— y solo
    se distinguen en tres cosas: cómo se identifica cada elemento, cómo se lee, y
    con qué palabras se narra el movimiento. Esos tres puntos son los parámetros.

    Se extrajo al agregar el segundo caso, no al escribir el primero. Antes de la
    HU-06 no había nada que compartir, y generalizar con un solo caso de uso lleva
    a inventar parámetros que nadie necesita.

    Parámetros:
        antes, despues -> colecciones de objetos (el estado anterior y el nuevo)
        clave          -> función que devuelve el identificador estable de uno
        etiqueta       -> función que devuelve su nombre legible
        verbo_entra    -> cómo se narra lo que se agregó ("concedidos")
        verbo_sale     -> cómo se narra lo que se quitó ("revocados")

    Devuelve cadena vacía si no hubo ningún cambio. Las vistas usan ese valor para
    NO escribir una fila de auditoría: guardar un formulario sin tocar nada no es
    un hecho auditable, y una bitácora llena de filas "no cambió nada" esconde las
    que sí importan.

    El orden alfabético del resultado es deliberado: hace el texto comparable
    entre filas y estable entre ejecuciones, así que dos cambios idénticos se leen
    idénticos.
    """
    mapa_antes = {clave(objeto): objeto for objeto in antes}
    mapa_despues = {clave(objeto): objeto for objeto in despues}

    entraron = sorted(
        etiqueta(objeto) for k, objeto in mapa_despues.items() if k not in mapa_antes
    )
    salieron = sorted(
        etiqueta(objeto) for k, objeto in mapa_antes.items() if k not in mapa_despues
    )

    partes = []
    if entraron:
        partes.append(f"{verbo_entra}: {', '.join(entraron)}")
    if salieron:
        partes.append(f"{verbo_sale}: {', '.join(salieron)}")

    return "; ".join(partes)


def describir_cambio_permisos(permisos_antes, permisos_despues):
    """Arma el detalle de un cambio de permisos: qué se concedió y qué se revocó.

    Recibe dos colecciones de objetos Permiso (el estado anterior y el nuevo) y
    devuelve una cadena como:

        concedidos: Validar fichas, Exportar reportes; revocados: Crear cuentas

    ¿Por qué el nombre visible y no el código?
    Porque la bitácora la lee una persona. "revocados: fichas.validar" obliga a
    ir a buscar qué era eso; "revocados: Validar fichas levantadas" se entiende
    solo. El código sigue estando en la base de datos si hace falta precisión.
    """
    return describir_cambio_de_conjunto(
        permisos_antes,
        permisos_despues,
        clave=lambda permiso: permiso.codigo,
        etiqueta=lambda permiso: permiso.nombre,
        verbo_entra="concedidos",
        verbo_sale="revocados",
    )


def describir_cambio_asignaciones(censistas_antes, censistas_despues):
    """Arma el detalle de un cambio en el reparto de un sector (HU-06).

    Recibe dos colecciones de objetos Usuario y devuelve una cadena como:

        asignados: Marta Soto (censista@opso.cl); desasignados: Juan Vera (jvera@opso.cl)

    Se guarda el nombre Y el correo. El nombre porque la bitácora la lee una
    persona y "Marta Soto" se entiende sola; el correo porque es el identificador
    único de la cuenta y en un operativo grande puede haber dos personas con el
    mismo nombre. Con los dos datos la fila es legible y además inequívoca.
    """
    return describir_cambio_de_conjunto(
        censistas_antes,
        censistas_despues,
        clave=lambda usuario: usuario.pk,
        etiqueta=lambda usuario: (
            f"{usuario.get_full_name() or usuario.email} ({usuario.email})"
        ),
        verbo_entra="asignados",
        verbo_sale="desasignados",
    )


def _valor_legible(formulario, nombre_campo, valor):
    """Convierte un valor interno en algo entendible por una persona.

    Sin esta traducción, la bitácora diría "rol: 3 -> 2" (los identificadores
    de la tabla usuarios_rol), que no le sirve a nadie en una revisión.
    """
    if valor is None or valor == "":
        return "(vacío)"

    if isinstance(valor, bool):
        return "Activo" if valor else "Inactivo"

    campo = formulario.fields.get(nombre_campo)

    # Los campos de clave foránea (ModelChoiceField) tienen "queryset". El valor
    # llega como objeto (desde cleaned_data) o como id (desde form.initial).
    if campo is not None and hasattr(campo, "queryset"):
        if hasattr(valor, "pk"):
            return str(valor)
        objeto = campo.queryset.filter(pk=valor).first()
        return str(objeto) if objeto else "(vacío)"

    return str(valor)


def describir_cambios(formulario):
    """Arma el texto del detalle a partir de los campos realmente modificados.

    form.changed_data es una lista que Django calcula comparando el valor
    inicial (lo que había en la base de datos) con el valor enviado. Solo se
    registra lo que cambió: una bitácora con los 8 campos en cada edición sería
    ruido y escondería lo importante.

    Resultado de ejemplo:
        rol: «Censista» -> «Supervisor»; teléfono: «(vacío)» -> «+56 9 1234 5678»
    """
    partes = []

    for nombre_campo in formulario.changed_data:
        campo = formulario.fields.get(nombre_campo)
        if campo is None:
            continue

        etiqueta = campo.label or nombre_campo
        antes = _valor_legible(
            formulario, nombre_campo, formulario.initial.get(nombre_campo)
        )
        despues = _valor_legible(
            formulario, nombre_campo, formulario.cleaned_data.get(nombre_campo)
        )

        if antes != despues:
            partes.append(f"{etiqueta}: «{antes}» → «{despues}»")

    return "; ".join(partes)
