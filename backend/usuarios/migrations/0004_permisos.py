"""Migración de ESQUEMA de la HU-04 (roles y permisos).

Generada con `makemigrations` y no escrita a mano: el estado de las tablas lo
deduce Django comparando los modelos con las migraciones anteriores, y hacerlo
a mano solo introduce la posibilidad de que el esquema y el modelo no coincidan.

Qué cambia en la base de datos:

  1. CREA usuarios_permiso        -> el catálogo de acciones autorizables.
  2. CREA usuarios_rol_permisos   -> tabla intermedia rol <-> permiso.
  3. AÑADE rol_afectado y rol_afectado_nombre a usuarios_registro_auditoria,
     porque a partir de esta historia una acción auditada puede recaer sobre un
     ROL y no solo sobre una cuenta.
  4. ALTERA la columna "accion" de la bitácora para admitir el valor nuevo
     CAMBIAR_PERMISOS. Es solo la lista de opciones: en PostgreSQL el tipo
     sigue siendo varchar(20) y no hay que reescribir las filas existentes.

Los tres campos nuevos admiten NULL o van en blanco, así que la migración se
aplica sobre una base con datos sin pedir ningún valor por defecto y sin
invalidar las filas de auditoría ya escritas.

El catálogo de permisos NO se siembra aquí: eso lo hace 0005, que es una
migración de datos. Separarlas mantiene la distinción que ya estableció el par
0001/0002 (esquema vs. datos) y permite revertir los datos sin tirar las tablas.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_gestion_usuarios'),
    ]

    operations = [
        migrations.AddField(
            model_name='registroauditoria',
            name='rol_afectado',
            field=models.ForeignKey(blank=True, help_text='Sobre qué rol se ejecutó la acción (permisos).', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acciones_auditoria', to='usuarios.rol', verbose_name='rol afectado'),
        ),
        migrations.AddField(
            model_name='registroauditoria',
            name='rol_afectado_nombre',
            field=models.CharField(blank=True, help_text='Copia fija: sobrevive aunque el rol se elimine.', max_length=60, verbose_name='nombre del rol afectado'),
        ),
        migrations.AlterField(
            model_name='registroauditoria',
            name='accion',
            field=models.CharField(choices=[('CREAR', 'Creó la cuenta'), ('EDITAR', 'Editó los datos'), ('CAMBIAR_ROL', 'Cambió el rol'), ('DESHABILITAR', 'Deshabilitó la cuenta'), ('HABILITAR', 'Habilitó la cuenta'), ('ENVIAR_ENLACE', 'Envió enlace de contraseña'), ('CAMBIAR_PERMISOS', 'Cambió los permisos del rol')], db_index=True, max_length=20, verbose_name='acción'),
        ),
        migrations.CreateModel(
            name='Permiso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(help_text='Identificador interno con el que el código comprueba el permiso. Formato módulo.acción, ej.: fichas.validar', max_length=60, unique=True, verbose_name='código')),
                ('nombre', models.CharField(help_text='Cómo se lee el permiso en la matriz.', max_length=120, verbose_name='nombre visible')),
                ('modulo', models.CharField(choices=[('USUARIOS', 'Usuarios'), ('ROLES', 'Roles y permisos'), ('AUDITORIA', 'Auditoría'), ('FICHAS', 'Fichas de familias'), ('OPERATIVOS', 'Operativos y sectores'), ('REPORTES', 'Reportes')], db_index=True, help_text='Sección de OPSO a la que pertenece. Solo agrupa la vista.', max_length=20, verbose_name='módulo')),
                ('descripcion', models.TextField(blank=True, help_text='Qué habilita exactamente. Se muestra como ayuda en la matriz.', verbose_name='descripción')),
                ('orden', models.PositiveSmallIntegerField(default=100, help_text='Posición dentro de su módulo. Permite listar los permisos de menos a más poder (ver, crear, editar, borrar) en vez de alfabéticamente.', verbose_name='orden')),
                ('activo', models.BooleanField(default=True, help_text='Si se desactiva, deja de concederse aunque siga marcado en la matriz. Permite retirar un permiso sin borrar las filas que documentan quién lo tenía.', verbose_name='activo')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
            ],
            options={
                'verbose_name': 'permiso',
                'verbose_name_plural': 'permisos',
                'db_table': 'usuarios_permiso',
                'ordering': ['modulo', 'orden', 'nombre'],
                'constraints': [models.CheckConstraint(condition=models.Q(('modulo__in', ['USUARIOS', 'ROLES', 'AUDITORIA', 'FICHAS', 'OPERATIVOS', 'REPORTES'])), name='permiso_modulo_valido')],
            },
        ),
        migrations.AddField(
            model_name='rol',
            name='permisos',
            field=models.ManyToManyField(blank=True, db_table='usuarios_rol_permisos', help_text='Acciones que este rol tiene autorizadas dentro de OPSO.', related_name='roles', to='usuarios.permiso', verbose_name='permisos'),
        ),
    ]
