"""Vista de la matriz de permisos (HU-04).

Una sola pantalla: /roles/permisos/. Muestra una tabla con los permisos como
filas y los roles como columnas, y permite conceder o revocar marcando casillas.

¿POR QUÉ UNA MATRIZ Y NO UNA PANTALLA POR ROL?

Porque la pregunta que se hace el administrador casi nunca es "¿qué puede hacer
el supervisor?" sino "¿QUIÉN puede validar fichas?". Con una pantalla por rol esa
comparación exige abrir tres pantallas y recordar lo que decía cada una. En una
matriz se lee en una fila. Además hace visibles los errores por omisión: una fila
entera sin marcar salta a la vista, y significa que nadie puede hacer esa acción.

CONTROL DE ACCESO — protegida por ROL y no por permiso, a propósito.

Esta vista usa RolRequeridoMixin (rol Administrador) y NO el
PermisoRequeridoMixin que introduce esta misma historia. La razón está explicada
en mixins.py y es la regla de "no guardar la llave dentro de la caja que abre":
si el acceso a la matriz dependiera de un permiso, un administrador podría
revocárselo con un clic y nadie podría volver a entrar a repararlo desde la
aplicación. Habría que intervenir la base de datos a mano.
"""

from itertools import groupby

from django.contrib import messages
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .auditoria import describir_cambio_permisos, registrar_accion
from .forms_permisos import PermisosRolForm
from .models import AccionAuditoria, ModuloPermiso, Permiso, Rol
from .views_gestion import SoloAdministradorMixin


class MatrizPermisosView(SoloAdministradorMixin, View):
    """Consulta y edición de la matriz rol × permiso.

    URL: /roles/permisos/

    Se escribe como View "cruda" y no heredando de FormView o UpdateView porque
    ninguna de esas clases modela lo que aquí ocurre: hay VARIOS formularios
    (uno por rol) y ningún objeto único que se esté editando. Forzar FormView
    obligaría a sobrescribir get_form, get_context_data, form_valid y
    form_invalid hasta no dejar nada del comportamiento original. Con View se
    escriben los dos métodos que hacen falta, get() y post(), y se lee de corrido.
    """

    template_name = "usuarios/gestion/permisos_matriz.html"
    mensaje_sin_permiso = (
        "Solo el rol Administrador puede modificar los permisos de los roles."
    )

    # ------------------------------------------------------------------
    # Datos comunes a GET y POST
    # ------------------------------------------------------------------

    def obtener_roles(self):
        """Todos los roles, activos e inactivos, ordenados por nombre.

        Se incluyen los INACTIVOS a propósito. Un rol desactivado conserva sus
        permisos y puede volver a activarse; esconderlo daría la impresión de que
        no concede nada. La plantilla lo marca con una etiqueta para que no se
        confunda con uno vigente.
        """
        return Rol.objects.all().order_by("nombre")

    def obtener_permisos(self):
        """Permisos que se pueden conceder: los vigentes.

        Los desactivados no se muestran porque no se pueden conceder (ver
        Usuario.tiene_permiso, que exige activo=True). El formulario se encarga
        de no revocarlos si algún rol todavía los tuviera.

        Devuelve un QUERYSET y no una lista, por dos razones:

          1. ModelMultipleChoiceField.queryset solo acepta un queryset: al
             asignarlo llama internamente a .all() para clonarlo.
          2. Un queryset guarda su resultado en caché la primera vez que se
             recorre. Como la vista pasa SIEMPRE EL MISMO OBJETO a todos los
             formularios y a la matriz, la consulta a PostgreSQL se hace una sola
             vez, que es justo lo que se buscaba al materializarlo.

        ORDEN DE LOS MÓDULOS. El ordering del modelo Permiso ordena por el campo
        "modulo", que es el código guardado, y eso da un orden alfabético
        (Auditoría, Fichas, Operativos, Reportes, Roles, Usuarios). Sirve como
        valor por defecto para /admin/, pero para la matriz interesa otro: primero
        los módulos que ya tienen pantallas y después los que corresponden a
        historias futuras, que es exactamente el orden en que están declarados en
        ModuloPermiso.

        Se traduce a SQL con Case/When en vez de ordenar en Python, para que el
        orden lo aplique PostgreSQL y el queryset siga siendo un queryset (si se
        ordenara en memoria habría que convertirlo en lista y volveríamos al
        problema del punto 1).
        """
        orden_modulo = Case(
            *[
                When(modulo=codigo, then=Value(posicion))
                for posicion, codigo in enumerate(ModuloPermiso.values)
            ],
            # Un módulo que no esté en el catálogo (imposible por el
            # CheckConstraint, pero el ORM no lo sabe) va al final en vez de
            # romper la consulta.
            default=Value(len(ModuloPermiso.values)),
            output_field=IntegerField(),
        )

        return (
            Permiso.objects.filter(activo=True)
            .annotate(_orden_modulo=orden_modulo)
            .order_by("_orden_modulo", "orden", "nombre")
        )

    def construir_formularios(self, roles, permisos, datos=None):
        """Un formulario por cada rol EDITABLE, indexado por la clave del rol.

        El rol Administrador queda fuera: concede todo de forma implícita
        (Rol.concede_todo), así que no hay nada que marcar ni desmarcar. Dibujar
        casillas editables para él sería mentir sobre el efecto de un clic.
        """
        return {
            rol.pk: PermisosRolForm(
                datos,
                rol=rol,
                permisos_disponibles=permisos,
            )
            for rol in roles
            if not rol.concede_todo
        }

    def construir_matriz(self, roles, permisos, formularios):
        """Arma la estructura que la plantilla recorre para dibujar la tabla.

        Se construye AQUÍ, en Python, y no con lógica dentro de la plantilla. El
        lenguaje de plantillas de Django no permite operaciones como "¿está el
        permiso 7 en la lista del rol 2?", y forzarlo llevaría a inventar filtros
        propios. Preparar los datos en la vista es la solución simple: la
        plantilla solo recorre y escribe HTML.

        Resultado:
            [
              {"modulo": "Usuarios",
               "filas": [
                  {"permiso": <Permiso>,
                   "celdas": [{"rol":..., "nombre_campo":..., "valor":...,
                               "marcado": bool, "editable": bool}, ...]}
               ]}
            ]
        """
        # Qué tiene marcado cada rol. Para los editables se pregunta al
        # formulario (que sabe distinguir un POST reenviado de la base de datos);
        # el resto se resuelve con concede_todo.
        marcados_por_rol = {
            rol.pk: formularios[rol.pk].pks_seleccionados()
            for rol in roles
            if rol.pk in formularios
        }

        grupos = []
        # groupby exige que la lista venga ordenada por la misma clave; el
        # ordering del modelo Permiso ya garantiza ["modulo", "orden", "nombre"].
        for codigo_modulo, permisos_del_modulo in groupby(
            permisos, key=lambda permiso: permiso.modulo
        ):
            filas = []
            for permiso in permisos_del_modulo:
                celdas = []
                for rol in roles:
                    editable = not rol.concede_todo
                    celdas.append(
                        {
                            "rol": rol,
                            "editable": editable,
                            "marcado": (
                                permiso.pk in marcados_por_rol[rol.pk]
                                if editable
                                else True  # concede_todo: siempre concedido
                            ),
                            "nombre_campo": (
                                formularios[rol.pk].nombre_campo_html
                                if editable
                                else ""
                            ),
                            "valor": permiso.pk,
                        }
                    )
                filas.append({"permiso": permiso, "celdas": celdas})

            grupos.append(
                {
                    "modulo": ModuloPermiso(codigo_modulo).label,
                    "filas": filas,
                }
            )

        return grupos

    def contexto(self, roles, permisos, formularios):
        return {
            "titulo_pagina": "Roles y permisos",
            "roles": roles,
            "grupos": self.construir_matriz(roles, permisos, formularios),
            "formularios": formularios.values(),
            "total_permisos": len(permisos),
        }

    # ------------------------------------------------------------------
    # GET: mostrar la matriz
    # ------------------------------------------------------------------

    def get(self, request, *args, **kwargs):
        # prefetch_related trae de una vez los permisos de todos los roles. Sin
        # esto, dibujar la matriz lanzaría una consulta por cada rol (N+1).
        roles = list(self.obtener_roles().prefetch_related("permisos"))
        permisos = self.obtener_permisos()
        formularios = self.construir_formularios(roles, permisos)

        return render(
            request, self.template_name, self.contexto(roles, permisos, formularios)
        )

    # ------------------------------------------------------------------
    # POST: guardar los cambios
    # ------------------------------------------------------------------

    def post(self, request, *args, **kwargs):
        roles = list(self.obtener_roles().prefetch_related("permisos"))
        permisos = self.obtener_permisos()
        formularios = self.construir_formularios(roles, permisos, datos=request.POST)

        # Un formulario solo puede ser inválido si llegó un identificador que no
        # corresponde a ningún permiso vigente, lo que no ocurre usando la
        # pantalla: implica una petición manipulada. Se rechaza el POST completo
        # en vez de guardar los roles válidos, porque aplicar a medias un cambio
        # de permisos dejaría el sistema en un estado que nadie decidió.
        if not all(formulario.is_valid() for formulario in formularios.values()):
            messages.error(
                request,
                "No se pudo guardar: la solicitud contenía permisos que no "
                "existen. No se aplicó ningún cambio.",
            )
            return render(
                request,
                self.template_name,
                self.contexto(roles, permisos, formularios),
            )

        roles_modificados = []

        # Una sola transacción para TODOS los roles: si algo falla a mitad, no
        # queda un reparto de permisos parcial. Y cada cambio va junto con su
        # fila de auditoría, igual que en la creación de usuarios de la HU-03.
        with transaction.atomic():
            for formulario in formularios.values():
                antes, despues = formulario.guardar()
                detalle = describir_cambio_permisos(antes, despues)

                # Sin cambios no se escribe en la bitácora: guardar el formulario
                # sin tocar nada no es un hecho auditable, y una bitácora llena
                # de filas vacías esconde las que importan.
                if not detalle:
                    continue

                registrar_accion(
                    administrador=request.user,
                    accion=AccionAuditoria.CAMBIAR_PERMISOS,
                    rol_afectado=formulario.rol,
                    detalle=detalle,
                    request=request,
                )
                roles_modificados.append(formulario.rol.nombre)

        if roles_modificados:
            messages.success(
                request,
                "Permisos actualizados para "
                f"{', '.join(roles_modificados)}. El cambio afecta de inmediato "
                "a todas las personas con ese rol.",
            )
        else:
            messages.info(request, "No hiciste ningún cambio en los permisos.")

        # Redirección tras un POST correcto (patrón POST-redirect-GET): evita que
        # al recargar la página el navegador reenvíe el formulario.
        return redirect(reverse("usuarios:permisos"))
