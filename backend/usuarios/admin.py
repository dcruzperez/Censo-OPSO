"""Registro de los modelos en el panel de administración de Django.

El admin es una interfaz CRUD generada automáticamente. Para OPSO cumple un
rol concreto: es la herramienta con la que el Administrador crea las cuentas
de los supervisores y censistas, y les asigna el rol.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import IntentoAcceso, RegistroAuditoria, Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "dashboard_url_name", "activo", "total_usuarios")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo")
    readonly_fields = ("creado_en", "actualizado_en")

    @admin.display(description="usuarios asignados")
    def total_usuarios(self, obj):
        return obj.usuarios.count()


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin del usuario personalizado.

    Hay que redefinir los "fieldsets" porque los que trae Django mencionan el
    campo username, que en OPSO no existe.
    """

    add_form = UsuarioCreationForm  # formulario de creación
    form = UsuarioChangeForm  # formulario de edición
    model = Usuario

    list_display = (
        "email",
        "nombre_usuario",
        "first_name",
        "last_name",
        "rol",
        "is_active",
        "last_login",
    )
    list_filter = ("rol", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "nombre_usuario", "first_name", "last_name", "rut")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined", "creado_en", "actualizado_en")

    # select_related evita una consulta extra por fila para obtener el rol.
    list_select_related = ("rol",)

    fieldsets = (
        ("Credenciales", {"fields": ("email", "nombre_usuario", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "rut", "telefono")}),
        ("Rol y permisos", {
            "fields": ("rol", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Fechas", {"fields": ("last_login", "date_joined", "creado_en", "actualizado_en")}),
    )

    # Formulario reducido al crear: solo lo indispensable.
    add_fieldsets = (
        (
            "Crear usuario",
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "nombre_usuario",
                    "first_name",
                    "last_name",
                    "rut",
                    "rol",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(IntentoAcceso)
class IntentoAccesoAdmin(admin.ModelAdmin):
    """Bitácora de accesos: solo lectura.

    No se permite crear ni editar registros: una bitácora que se puede
    modificar no sirve como evidencia de auditoría.
    """

    list_display = ("ocurrido_en", "email_ingresado", "exitoso", "ip", "usuario")
    list_filter = ("exitoso", "ocurrido_en")
    search_fields = ("email_ingresado", "ip")
    date_hierarchy = "ocurrido_en"
    list_select_related = ("usuario",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Bitácora de la administración de usuarios (HU-03): solo lectura.

    Mismo criterio que IntentoAccesoAdmin: se bloquean el alta y la
    modificación. La aplicación escribe en esta tabla, pero ninguna interfaz
    permite alterar lo ya escrito, ni siquiera al superusuario desde /admin/.
    Sin esa garantía, la bitácora no serviría como evidencia ante una auditoría
    real.
    """

    list_display = (
        "ocurrido_en",
        "administrador_email",
        "accion",
        "usuario_afectado_email",
        "ip",
    )
    list_filter = ("accion", "ocurrido_en")
    search_fields = ("administrador_email", "usuario_afectado_email", "detalle")
    date_hierarchy = "ocurrido_en"
    list_select_related = ("administrador", "usuario_afectado")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
