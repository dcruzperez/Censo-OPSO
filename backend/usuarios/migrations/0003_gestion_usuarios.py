# Generada automáticamente por Django 6.0.7 (comando: makemigrations)
#
# MIGRACIÓN DE LA HU-03 · Administración de usuarios
#
# QUÉ HACE ESTA MIGRACIÓN (traducción a SQL, en orden):
#
#   1. CREATE TABLE usuarios_registro_auditoria
#      Nueva bitácora de acciones administrativas. Incluye:
#        - CHECK/choices sobre "accion" (catálogo cerrado de acciones),
#        - dos columnas de texto con copia de los correos (desnormalización
#          deliberada: la bitácora sigue siendo legible aunque una cuenta se
#          elimine y las claves foráneas queden en NULL),
#        - índice en "accion" y en "ocurrido_en" (db_index=True).
#
#   2. ALTER TABLE usuarios_usuario ADD COLUMN nombre_usuario VARCHAR(30)
#         NULL UNIQUE
#      Identificador corto y legible. Es NULL-able a propósito: así la columna
#      se puede agregar a una tabla que YA tiene filas sin pedir un valor por
#      defecto, y en SQL varios NULL no violan la restricción UNIQUE (varias
#      cadenas vacías sí lo harían).
#
#   3. CREATE INDEX idx_usuario_estado_nombre ON usuarios_usuario
#         (is_active, first_name, last_name)
#      Es exactamente la consulta del listado de administración: se filtra por
#      estado y se ordena por nombre. Sin índice, PostgreSQL tendría que leer y
#      ordenar la tabla completa en cada página.
#
#   4. ALTER TABLE usuarios_registro_auditoria ADD FOREIGN KEY (administrador_id)
#      ALTER TABLE usuarios_registro_auditoria ADD FOREIGN KEY (usuario_afectado_id)
#      Ambas con ON DELETE SET NULL: si se borrara una cuenta, la fila de
#      auditoría se conserva. La trazabilidad es más importante que la
#      integridad referencial estricta en una bitácora.
#
#   5. CREATE INDEX idx_auditoria_afectado ON usuarios_registro_auditoria
#         (usuario_afectado_id, ocurrido_en DESC)
#      Acelera el historial que muestra la ficha de cada usuario.
#
# NO se debe editar a mano una vez aplicada: si el modelo cambia, se genera una
# migración nueva.

import django.db.models.deletion
import django.utils.timezone
import usuarios.validators
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('usuarios', '0002_roles_iniciales'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistroAuditoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('administrador_email', models.CharField(blank=True, help_text='Copia fija: sobrevive aunque la cuenta se elimine.', max_length=254, verbose_name='correo del administrador')),
                ('accion', models.CharField(choices=[('CREAR', 'Creó la cuenta'), ('EDITAR', 'Editó los datos'), ('CAMBIAR_ROL', 'Cambió el rol'), ('DESHABILITAR', 'Deshabilitó la cuenta'), ('HABILITAR', 'Habilitó la cuenta'), ('ENVIAR_ENLACE', 'Envió enlace de contraseña')], db_index=True, max_length=20, verbose_name='acción')),
                ('usuario_afectado_email', models.CharField(blank=True, max_length=254, verbose_name='correo del usuario afectado')),
                ('detalle', models.TextField(blank=True, help_text='Qué cambió exactamente, campo por campo.', verbose_name='detalle')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='dirección IP')),
                ('user_agent', models.CharField(blank=True, max_length=300, verbose_name='navegador')),
                ('ocurrido_en', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='fecha y hora')),
            ],
            options={
                'verbose_name': 'registro de auditoría',
                'verbose_name_plural': 'registros de auditoría',
                'db_table': 'usuarios_registro_auditoria',
                'ordering': ['-ocurrido_en', '-id'],
            },
        ),
        migrations.AddField(
            model_name='usuario',
            name='nombre_usuario',
            field=models.CharField(blank=True, help_text='Identificador corto para listados y planillas (ej.: msoto). NO se usa para iniciar sesión: la credencial es el correo.', max_length=30, null=True, unique=True, validators=[usuarios.validators.validar_nombre_usuario], verbose_name='nombre de usuario'),
        ),
        migrations.AddIndex(
            model_name='usuario',
            index=models.Index(fields=['is_active', 'first_name', 'last_name'], name='idx_usuario_estado_nombre'),
        ),
        migrations.AddField(
            model_name='registroauditoria',
            name='administrador',
            field=models.ForeignKey(blank=True, help_text='Quién ejecutó la acción.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acciones_realizadas', to=settings.AUTH_USER_MODEL, verbose_name='administrador'),
        ),
        migrations.AddField(
            model_name='registroauditoria',
            name='usuario_afectado',
            field=models.ForeignKey(blank=True, help_text='Sobre qué cuenta se ejecutó la acción.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acciones_recibidas', to=settings.AUTH_USER_MODEL, verbose_name='usuario afectado'),
        ),
        migrations.AddIndex(
            model_name='registroauditoria',
            index=models.Index(fields=['usuario_afectado', '-ocurrido_en'], name='idx_auditoria_afectado'),
        ),
    ]
