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

from .models import AccionAuditoria, RegistroAuditoria
from .seguridad import obtener_ip, obtener_user_agent

logger = logging.getLogger("usuarios")


def registrar_accion(
    administrador,
    accion,
    usuario_afectado=None,
    detalle="",
    request=None,
    rol_afectado=None,
):
    """Escribe una fila en la bitácora de auditoría y la devuelve.

    Parámetros:
        administrador    -> Usuario que ejecuta la acción (request.user).
        accion           -> valor de AccionAuditoria.
        usuario_afectado -> Usuario sobre el que se actuó (HU-03).
        detalle          -> texto libre con el cambio exacto.
        request          -> para obtener IP y navegador (contexto forense).
        rol_afectado     -> Rol sobre el que se actuó (HU-04: permisos).

    Se indica UNO de los dos objetos afectados, no los dos: una acción recae
    sobre una cuenta (deshabilitarla) o sobre un rol (cambiarle los permisos).
    Si no se indica ninguno se levanta ValueError en vez de escribir una fila
    incompleta: una bitácora que no dice sobre qué se actuó no sirve de nada, y
    es mejor que el error salte en desarrollo que descubrir el hueco durante una
    auditoría real.

    Se guardan el correo y el nombre como texto además de las claves foráneas: si
    la cuenta o el rol se eliminaran físicamente algún día, la fila seguiría
    siendo legible (ver la explicación en el modelo RegistroAuditoria).
    """
    if usuario_afectado is None and rol_afectado is None:
        raise ValueError(
            "registrar_accion() necesita saber sobre qué se actuó: "
            "hay que indicar usuario_afectado o rol_afectado."
        )

    registro = RegistroAuditoria.objects.create(
        administrador=administrador if getattr(administrador, "pk", None) else None,
        administrador_email=getattr(administrador, "email", "") or "",
        accion=accion,
        usuario_afectado=usuario_afectado,
        usuario_afectado_email=usuario_afectado.email if usuario_afectado else "",
        rol_afectado=rol_afectado,
        rol_afectado_nombre=rol_afectado.nombre if rol_afectado else "",
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


def describir_cambio_permisos(permisos_antes, permisos_despues):
    """Arma el detalle de un cambio de permisos: qué se concedió y qué se revocó.

    Recibe dos colecciones de objetos Permiso (el estado anterior y el nuevo) y
    devuelve una cadena como:

        concedidos: Validar fichas, Exportar reportes; revocados: Crear cuentas

    ¿Por qué el nombre visible y no el código?
    Porque la bitácora la lee una persona. "revocados: fichas.validar" obliga a
    ir a buscar qué era eso; "revocados: Validar fichas levantadas" se entiende
    solo. El código sigue estando en la base de datos si hace falta precisión.

    Devuelve cadena vacía si no hubo ningún cambio. La vista usa ese valor para
    NO escribir una fila de auditoría: guardar el formulario sin tocar nada no es
    un hecho auditable, y una bitácora llena de filas "no cambió nada" esconde
    las que sí importan.
    """
    antes = {permiso.codigo: permiso for permiso in permisos_antes}
    despues = {permiso.codigo: permiso for permiso in permisos_despues}

    concedidos = sorted(p.nombre for c, p in despues.items() if c not in antes)
    revocados = sorted(p.nombre for c, p in antes.items() if c not in despues)

    partes = []
    if concedidos:
        partes.append(f"concedidos: {', '.join(concedidos)}")
    if revocados:
        partes.append(f"revocados: {', '.join(revocados)}")

    return "; ".join(partes)


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
