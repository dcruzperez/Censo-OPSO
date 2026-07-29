"""Vistas de la administración de usuarios (HU-03).

Se usan VISTAS BASADAS EN CLASES genéricas (ListView, CreateView, UpdateView,
DetailView) porque este módulo es un CRUD clásico y esas clases ya resuelven,
correctamente y sin código propio:

  ListView   -> consulta, ordenamiento, paginación y contexto de la plantilla.
  CreateView -> GET muestra el formulario vacío; POST valida, guarda y redirige.
  UpdateView -> igual, pero cargando primero el objeto por su clave primaria y
                devolviendo 404 si no existe.
  DetailView -> carga un objeto y lo entrega a la plantilla.

Lo único que se escribe es lo específico de OPSO: el control de acceso por rol,
los filtros, la auditoría y las reglas de negocio (no autodeshabilitarse, no
quedarse sin administradores).

CONTROL DE ACCESO — tres capas, no una:
  1. LoginRequiredMiddleware (settings): ninguna vista responde sin sesión.
  2. RolRequeridoMixin (reutilizado de la HU-01): exige el rol Administrador.
  3. Reglas por objeto dentro de cada vista: qué puede hacer este administrador
     con ESTA cuenta concreta.
La capa 3 es la que impide la "modificación por URL": no basta con ser
administrador, la acción concreta también tiene que estar permitida.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .auditoria import describir_cambios, registrar_accion
from .forms_gestion import CrearUsuarioForm, EditarUsuarioForm, FiltroUsuariosForm
from .mixins import RolRequeridoMixin
from .models import AccionAuditoria, RegistroAuditoria, Rol, RolCodigo, Usuario
from .seguridad import enviar_enlace_contrasena


class SoloAdministradorMixin(RolRequeridoMixin):
    """Puerta de entrada común a todo el módulo.

    Se declara una sola vez y todas las vistas heredan de aquí. Ventaja
    concreta: es imposible agregar una vista nueva a este módulo y olvidar
    protegerla, porque la protección viene en la clase base.

    RolRequeridoMixin ya se escribió y se probó en la HU-01. No se reimplementa
    nada: se reutiliza.
    """

    roles_permitidos = (RolCodigo.ADMINISTRADOR,)
    mensaje_sin_permiso = (
        "Solo el rol Administrador puede acceder a la administración de usuarios."
    )

    def verificar_superusuario(self, usuario):
        """Impide que un administrador común toque una cuenta de superusuario.

        El superusuario tiene acceso total, incluido /admin/ y la base de datos
        a través de él. Si un administrador normal pudiera editarlo o
        deshabilitarlo, podría escalar privilegios (cambiarle el correo y pedir
        un enlace de contraseña a una casilla propia). Es el principio de
        mínimo privilegio aplicado entre cuentas del mismo módulo.
        """
        if usuario.is_superuser and not self.request.user.is_superuser:
            raise PermissionDenied(
                "Solo un superusuario puede modificar otra cuenta de superusuario."
            )


# ==========================================================================
# 1. LISTAR
# ==========================================================================


class UsuarioListView(SoloAdministradorMixin, ListView):
    """Listado de usuarios con búsqueda, filtros y paginación.

    URL: /usuarios/
    """

    model = Usuario
    template_name = "usuarios/gestion/usuarios_list.html"
    context_object_name = "usuarios"

    # 10 filas por página. La paginación no es solo estética: sin ella, con
    # 2.000 censistas la consulta traería 2.000 filas a la memoria del servidor
    # y el navegador tendría que dibujarlas todas.
    paginate_by = 10

    def get_queryset(self):
        """Construye la consulta SQL según los filtros recibidos por la URL.

        El QuerySet es PEREZOSO (lazy): cada .filter() solo agrega condiciones
        y no toca la base de datos. La consulta se ejecuta UNA sola vez, cuando
        el paginador corta el trozo que corresponde a la página pedida
        (LIMIT/OFFSET en SQL).
        """
        self.filtro = FiltroUsuariosForm(self.request.GET or None)

        termino = rol = estado = None
        if self.filtro.is_valid():
            termino = self.filtro.cleaned_data.get("q")
            rol = self.filtro.cleaned_data.get("rol")
            estado = self.filtro.cleaned_data.get("estado")

        # buscar() vive en el manager (managers.py) y devuelve todos los
        # usuarios cuando el término está vacío, así que sirve como punto de
        # partida de la cadena en los dos casos.
        consulta = Usuario.objects.buscar(termino).select_related("rol")

        if rol:
            consulta = consulta.filter(rol=rol)

        if estado == "activos":
            consulta = consulta.filter(is_active=True)
        elif estado == "inactivos":
            consulta = consulta.filter(is_active=False)

        # Se agrega "id" al ordenamiento a propósito. Si dos personas se llaman
        # igual, PostgreSQL puede devolverlas en distinto orden en cada
        # consulta y una misma fila aparecería en dos páginas o en ninguna.
        # Un orden TOTAL (que no admite empates) hace la paginación estable.
        return consulta.order_by("first_name", "last_name", "id")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Administración de usuarios"
        contexto["filtro"] = self.filtro

        # Contadores globales (no dependen de los filtros ni de la página).
        contexto["total_usuarios"] = Usuario.objects.count()
        contexto["total_activos"] = Usuario.objects.filter(is_active=True).count()
        contexto["total_inactivos"] = Usuario.objects.filter(is_active=False).count()

        # Los filtros vigentes, sin el número de página, para que los enlaces
        # "Siguiente"/"Anterior" no pierdan la búsqueda que el usuario escribió.
        parametros = self.request.GET.copy()
        parametros.pop("page", None)
        contexto["parametros"] = parametros.urlencode()

        return contexto


# ==========================================================================
# 2. CREAR
# ==========================================================================


class UsuarioCreateView(SoloAdministradorMixin, CreateView):
    """Creación de una cuenta nueva.

    URL: /usuarios/nuevo/
    """

    model = Usuario
    form_class = CrearUsuarioForm
    template_name = "usuarios/gestion/usuario_create.html"
    success_url = reverse_lazy("usuarios:lista")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Crear usuario"
        # Se muestran los roles con su descripción para que el administrador
        # sepa qué está otorgando antes de elegir.
        contexto["roles"] = Rol.objects.filter(activo=True).order_by("nombre")
        return contexto

    def form_valid(self, form):
        """El formulario es válido: se crea la cuenta y se audita.

        transaction.atomic() envuelve la creación del usuario y su registro de
        auditoría: o se guardan las dos cosas, o ninguna. Un usuario creado sin
        rastro en la bitácora sería un agujero en la trazabilidad.

        El correo se envía FUERA de la transacción, a propósito: enviar un
        correo puede tardar segundos y mantener abierta una transacción mientras
        se espera a un servidor externo bloquea filas de PostgreSQL sin
        necesidad. Además, un correo ya enviado no se puede "deshacer" si la
        transacción se revirtiera.
        """
        with transaction.atomic():
            respuesta = super().form_valid(form)  # guarda y deja self.object

            registrar_accion(
                administrador=self.request.user,
                accion=AccionAuditoria.CREAR,
                usuario_afectado=self.object,
                detalle=(
                    f"Rol: {self.object.rol.nombre if self.object.rol_id else '(sin rol)'}; "
                    f"estado: {self.object.etiqueta_estado}; "
                    f"nombre de usuario: {self.object.nombre_usuario}"
                ),
                request=self.request,
            )

        nombre = self.object.get_full_name() or self.object.email

        if form.requiere_enlace:
            enviado = enviar_enlace_contrasena(
                self.object, self.request, es_nueva_cuenta=True
            )
            if enviado:
                messages.success(
                    self.request,
                    f"Usuario «{nombre}» creado. Se envió a {self.object.email} un "
                    "enlace para que defina su contraseña.",
                )
            else:
                # No se oculta el problema: la cuenta existe pero la persona no
                # puede entrar. El administrador tiene que saberlo para volver a
                # enviar el enlace desde la ficha del usuario.
                messages.warning(
                    self.request,
                    f"Usuario «{nombre}» creado, pero NO se pudo enviar el correo "
                    "con el enlace. Revisa la configuración de correo y usa el "
                    "botón «Enviar enlace de contraseña» en su ficha.",
                )
        else:
            messages.success(
                self.request,
                f"Usuario «{nombre}» creado con la contraseña inicial que definiste. "
                "Indícale que la cambie en su primer ingreso.",
            )

        return respuesta

    def form_invalid(self, form):
        messages.error(
            self.request,
            "No se pudo crear el usuario: revisa los campos marcados en rojo.",
        )
        return super().form_invalid(form)


# ==========================================================================
# 3. EDITAR
# ==========================================================================


class UsuarioUpdateView(SoloAdministradorMixin, UpdateView):
    """Edición de los datos de una cuenta.

    URL: /usuarios/<pk>/editar/
    """

    model = Usuario
    form_class = EditarUsuarioForm
    template_name = "usuarios/gestion/usuario_edit.html"
    context_object_name = "usuario"

    def get_queryset(self):
        return Usuario.objects.select_related("rol")

    def get_object(self, queryset=None):
        """Carga el objeto y aplica la regla de acceso POR OBJETO.

        Aquí se bloquea el ataque de "modificación por URL": aunque el
        administrador escriba a mano /usuarios/1/editar/, si esa cuenta es un
        superusuario y él no lo es, recibe un 403 y no ve nada.
        """
        usuario = super().get_object(queryset)
        self.verificar_superusuario(usuario)
        return usuario

    def get_form_kwargs(self):
        """Entrega al formulario quién está editando.

        El formulario necesita ese dato para bloquear el rol y el estado cuando
        alguien se edita a sí mismo (ver EditarUsuarioForm.__init__).
        """
        kwargs = super().get_form_kwargs()
        kwargs["usuario_actual"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("usuarios:detalle", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Editar usuario"
        contexto["es_su_propia_cuenta"] = self.request.user.pk == self.object.pk
        return contexto

    def form_valid(self, form):
        """Guarda los cambios y los registra en la bitácora, campo por campo.

        El detalle se calcula ANTES de guardar, porque describir_cambios()
        compara form.initial (lo que había en la base de datos) con
        form.cleaned_data (lo que llegó del navegador). Después del save() el
        "antes" ya se perdió.
        """
        detalle = describir_cambios(form)
        cambio_rol = "rol" in form.changed_data
        cambio_estado = "is_active" in form.changed_data
        activado = form.cleaned_data.get("is_active")

        with transaction.atomic():
            respuesta = super().form_valid(form)

            if not form.changed_data:
                messages.info(self.request, "No se modificó ningún dato.")
                return respuesta

            # Se registran acciones SEPARADAS según su naturaleza: así una
            # consulta puede responder "muéstrame todos los cambios de rol del
            # semestre" sin tener que leer texto libre.
            if cambio_rol:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.CAMBIAR_ROL,
                    usuario_afectado=self.object,
                    detalle=detalle,
                    request=self.request,
                )

            if cambio_estado:
                registrar_accion(
                    administrador=self.request.user,
                    accion=(
                        AccionAuditoria.HABILITAR
                        if activado
                        else AccionAuditoria.DESHABILITAR
                    ),
                    usuario_afectado=self.object,
                    detalle=detalle,
                    request=self.request,
                )

            otros_cambios = [
                campo
                for campo in form.changed_data
                if campo not in ("rol", "is_active")
            ]
            if otros_cambios:
                registrar_accion(
                    administrador=self.request.user,
                    accion=AccionAuditoria.EDITAR,
                    usuario_afectado=self.object,
                    detalle=detalle,
                    request=self.request,
                )

        messages.success(
            self.request,
            f"Los datos de «{self.object.get_full_name() or self.object.email}» "
            "se actualizaron correctamente.",
        )
        return respuesta

    def form_invalid(self, form):
        messages.error(
            self.request,
            "No se pudo guardar: revisa los campos marcados en rojo.",
        )
        return super().form_invalid(form)


# ==========================================================================
# 4. VER DETALLE (ficha del usuario)
# ==========================================================================


class UsuarioDetailView(SoloAdministradorMixin, DetailView):
    """Ficha completa de una cuenta, con su historial.

    URL: /usuarios/<pk>/

    No es una pantalla decorativa: reúne en un solo lugar los datos, los
    últimos accesos y las modificaciones administrativas. Es la vista que
    permite responder una consulta real ("¿por qué esta persona no puede
    entrar?") sin abrir la base de datos.
    """

    model = Usuario
    template_name = "usuarios/gestion/usuario_detail.html"
    context_object_name = "usuario"

    def get_queryset(self):
        return Usuario.objects.select_related("rol")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Ficha del usuario"

        # Últimos accesos de esta persona (bitácora de la HU-01).
        contexto["accesos"] = self.object.intentos_acceso.all()[:10]

        # Historial administrativo de esta cuenta (bitácora de la HU-03).
        contexto["auditoria"] = self.object.acciones_recibidas.select_related(
            "administrador"
        )[:15]

        contexto["es_su_propia_cuenta"] = self.request.user.pk == self.object.pk
        contexto["es_ultimo_administrador"] = (
            self.object.es_ultimo_administrador_activo()
        )
        return contexto


# ==========================================================================
# 5. DESHABILITAR / HABILITAR (borrado lógico)
# ==========================================================================


class CambiarEstadoUsuarioView(SoloAdministradorMixin, View):
    """Habilita o deshabilita una cuenta. NUNCA borra la fila.

    URLs: /usuarios/<pk>/deshabilitar/  y  /usuarios/<pk>/habilitar/
    Una sola clase atiende las dos rutas; el atributo `activar` (definido en
    urls.py) decide el sentido de la operación. Así la lógica de validación y
    auditoría no se escribe dos veces.

    ¿POR QUÉ DOS PASOS (GET muestra, POST ejecuta)?
    Porque cambiar el estado MODIFICA datos, y las peticiones GET deben ser
    seguras e idempotentes (regla de HTTP). Si se pudiera deshabilitar con un
    GET, bastaría con que alguien insertara en cualquier página
    <img src="https://opso.cl/usuarios/5/deshabilitar/"> para que el navegador
    del administrador ejecutara la acción sin que él lo notara: es un ataque
    CSRF. Con POST + token CSRF eso es imposible.

    Y de paso, el GET sirve como PANTALLA DE CONFIRMACIÓN, que es el otro
    requisito de la historia de usuario. Se implementa como página completa y
    no como ventana emergente de JavaScript para que funcione igual con JS
    deshabilitado.
    """

    #: True = habilitar, False = deshabilitar. Se define en urls.py.
    activar = False

    template_name = "usuarios/gestion/usuario_confirmar_estado.html"

    def get_usuario(self):
        usuario = get_object_or_404(
            Usuario.objects.select_related("rol"), pk=self.kwargs["pk"]
        )
        self.verificar_superusuario(usuario)
        return usuario

    def validar(self, usuario):
        """Devuelve un mensaje de error si la operación no está permitida.

        Estas reglas se comprueban en el GET (para avisar antes) y otra vez en
        el POST (para que valgan de verdad). Validar solo en el GET sería un
        control puramente visual: alguien podría enviar el POST directamente.
        """
        if usuario.is_active == self.activar:
            estado = "habilitada" if self.activar else "deshabilitada"
            return f"La cuenta ya se encuentra {estado}."

        if self.activar:
            return None

        # --- Reglas que solo aplican al DESHABILITAR ---

        if usuario.pk == self.request.user.pk:
            return (
                "No puedes deshabilitar tu propia cuenta: quedarías fuera del "
                "sistema en el acto. Debe hacerlo otro administrador."
            )

        if usuario.es_ultimo_administrador_activo():
            return (
                "Es el único administrador activo del sistema. Si se "
                "deshabilita, nadie podría volver a administrar usuarios. "
                "Habilita o crea otro administrador antes."
            )

        return None

    def get(self, request, *args, **kwargs):
        """Muestra la pantalla de confirmación."""
        usuario = self.get_usuario()

        return render(
            request,
            self.template_name,
            {
                "usuario": usuario,
                "activar": self.activar,
                "error": self.validar(usuario),
                "titulo_pagina": (
                    "Habilitar usuario" if self.activar else "Deshabilitar usuario"
                ),
            },
        )

    def post(self, request, *args, **kwargs):
        """Ejecuta el cambio de estado."""
        usuario = self.get_usuario()

        error = self.validar(usuario)
        if error:
            messages.error(request, error)
            return redirect("usuarios:detalle", pk=usuario.pk)

        with transaction.atomic():
            usuario.is_active = self.activar

            # update_fields limita el UPDATE a las columnas necesarias: es más
            # eficiente y, sobre todo, evita sobrescribir por accidente algún
            # otro campo que otra persona haya modificado entretanto.
            # "actualizado_en" debe ir en la lista o su valor auto_now no se
            # escribiría en la base de datos.
            usuario.save(update_fields=["is_active", "actualizado_en"])

            registrar_accion(
                administrador=request.user,
                accion=(
                    AccionAuditoria.HABILITAR
                    if self.activar
                    else AccionAuditoria.DESHABILITAR
                ),
                usuario_afectado=usuario,
                detalle=(
                    f"Estado: «{'Inactivo' if self.activar else 'Activo'}» → "
                    f"«{usuario.etiqueta_estado}»"
                ),
                request=request,
            )

        nombre = usuario.get_full_name() or usuario.email
        if self.activar:
            messages.success(
                request,
                f"La cuenta de «{nombre}» quedó habilitada y ya puede iniciar sesión.",
            )
        else:
            messages.success(
                request,
                f"La cuenta de «{nombre}» quedó deshabilitada. Sus datos y su "
                "historial se conservan íntegros; solo perdió el acceso.",
            )

        return redirect("usuarios:detalle", pk=usuario.pk)


# ==========================================================================
# 6. ENVIAR ENLACE DE CONTRASEÑA
# ==========================================================================


class EnviarEnlaceContrasenaView(SoloAdministradorMixin, View):
    """Reenvía el enlace para que la persona defina su contraseña.

    URL: /usuarios/<pk>/enviar-enlace/  (solo POST)

    Resuelve dos situaciones reales:
      1. A la persona le venció el enlace de invitación (dura 60 minutos).
      2. Perdió el acceso al correo y ya lo recuperó, o simplemente pide ayuda.

    El administrador NO ve ni define la contraseña: solo dispara el envío del
    enlace. El secreto sigue siendo conocido únicamente por su titular, que es
    la propiedad que hace creíble la auditoría ("esta acción la hizo esta
    persona, porque nadie más pudo autenticarse como ella").
    """

    def post(self, request, *args, **kwargs):
        usuario = get_object_or_404(Usuario, pk=self.kwargs["pk"])
        self.verificar_superusuario(usuario)

        if not usuario.is_active:
            messages.error(
                request,
                "La cuenta está deshabilitada: habilítala primero. Un usuario "
                "inactivo no puede iniciar sesión aunque cambie su contraseña.",
            )
            return redirect("usuarios:detalle", pk=usuario.pk)

        if enviar_enlace_contrasena(usuario, request, es_nueva_cuenta=False):
            registrar_accion(
                administrador=request.user,
                accion=AccionAuditoria.ENVIAR_ENLACE,
                usuario_afectado=usuario,
                detalle=f"Enlace enviado a {usuario.email}",
                request=request,
            )
            messages.success(
                request,
                f"Se envió a {usuario.email} un enlace para crear una contraseña "
                "nueva. Es válido por 60 minutos y sirve una sola vez.",
            )
        else:
            messages.error(
                request,
                "No se pudo enviar el correo. Revisa la configuración SMTP en "
                "el archivo .env.",
            )

        return redirect("usuarios:detalle", pk=usuario.pk)


# ==========================================================================
# 7. BITÁCORA DE AUDITORÍA
# ==========================================================================


class AuditoriaListView(SoloAdministradorMixin, ListView):
    """Historial completo de acciones administrativas.

    URL: /usuarios/auditoria/

    Una bitácora que nadie puede leer no cumple su función. Esta pantalla la
    hace consultable desde la propia aplicación, sin depender de que alguien
    sepa SQL.
    """

    model = RegistroAuditoria
    template_name = "usuarios/gestion/auditoria_list.html"
    context_object_name = "registros"
    paginate_by = 20

    def get_queryset(self):
        # select_related trae administrador y usuario afectado en la MISMA
        # consulta: sin esto, 20 filas producirían 41 consultas (problema N+1).
        return RegistroAuditoria.objects.select_related(
            "administrador", "usuario_afectado"
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["titulo_pagina"] = "Auditoría de usuarios"
        contexto["total_registros"] = RegistroAuditoria.objects.count()
        return contexto
