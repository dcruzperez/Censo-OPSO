# Generada automáticamente por Django 6.0.7 (comando: makemigrations)
#
# QUÉ HACE ESTA MIGRACIÓN (traducción a SQL, en orden):
#   1. CREATE TABLE usuarios_rol           -> catálogo de roles + CHECK del código
#   2. CREATE TABLE usuarios_usuario       -> usuarios, con UNIQUE(email),
#      UNIQUE(rut) y FOREIGN KEY rol_id -> usuarios_rol(id) ON DELETE RESTRICT
#   3. CREATE TABLE usuarios_usuario_groups y usuarios_usuario_user_permissions
#      -> tablas intermedias de la relación muchos-a-muchos con el sistema de
#         permisos de Django (las crea el ManyToManyField heredado)
#   4. CREATE TABLE usuarios_intento_acceso -> bitácora de accesos
#   5. CREATE INDEX  -> índices para acelerar las consultas más frecuentes
#
# "initial = True" marca que es la primera migración de la app.
# "dependencies" indica que primero deben existir las tablas de django.contrib.auth
# (grupos y permisos), porque Usuario se relaciona con ellas.
#
# NO se debe editar a mano una vez aplicada: si el modelo cambia, se genera una
# migración nueva. El historial de migraciones es la "línea de tiempo" del
# esquema de la base de datos.

import django.db.models.deletion
import django.utils.timezone
import usuarios.managers
import usuarios.validators
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Rol',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(choices=[('ADMINISTRADOR', 'Administrador'), ('SUPERVISOR', 'Supervisor'), ('CENSISTA', 'Censista')], help_text='Identificador interno e inmutable del rol.', max_length=20, unique=True, verbose_name='código')),
                ('nombre', models.CharField(help_text='Nombre que se muestra en la interfaz.', max_length=60, verbose_name='nombre visible')),
                ('descripcion', models.TextField(blank=True, help_text='Qué puede hacer este rol dentro de OPSO.', verbose_name='descripción')),
                ('dashboard_url_name', models.CharField(help_text='Nombre de la URL de Django a la que se redirige tras iniciar sesión. Ej.: dashboards:supervisor', max_length=100, verbose_name='panel de destino')),
                ('activo', models.BooleanField(default=True, help_text='Si se desactiva, sus usuarios no podrán iniciar sesión.', verbose_name='activo')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
            ],
            options={
                'verbose_name': 'rol',
                'verbose_name_plural': 'roles',
                'db_table': 'usuarios_rol',
                'ordering': ['nombre'],
                'constraints': [models.CheckConstraint(condition=models.Q(('codigo__in', ['ADMINISTRADOR', 'SUPERVISOR', 'CENSISTA'])), name='rol_codigo_valido')],
            },
        ),
        migrations.CreateModel(
            name='Usuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('email', models.EmailField(help_text='Correo institucional con el que inicia sesión.', max_length=254, unique=True, verbose_name='correo electrónico')),
                ('rut', models.CharField(blank=True, help_text='Formato 12345678-9. Identifica a la persona en terreno.', max_length=12, null=True, unique=True, validators=[usuarios.validators.validar_rut], verbose_name='RUT')),
                ('telefono', models.CharField(blank=True, help_text='Contacto para coordinación del operativo.', max_length=20, verbose_name='teléfono')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='creado en')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='actualizado en')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
                ('rol', models.ForeignKey(blank=True, help_text='Determina qué puede ver y hacer en el sistema.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='usuarios', to='usuarios.rol', verbose_name='rol')),
            ],
            options={
                'verbose_name': 'usuario',
                'verbose_name_plural': 'usuarios',
                'db_table': 'usuarios_usuario',
                'ordering': ['first_name', 'last_name'],
            },
            managers=[
                ('objects', usuarios.managers.UsuarioManager()),
            ],
        ),
        migrations.CreateModel(
            name='IntentoAcceso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_ingresado', models.CharField(db_index=True, help_text='Lo que escribió la persona (puede no existir como cuenta).', max_length=254, verbose_name='correo ingresado')),
                ('exitoso', models.BooleanField(default=False, verbose_name='¿fue exitoso?')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='dirección IP')),
                ('user_agent', models.CharField(blank=True, max_length=300, verbose_name='navegador')),
                ('ocurrido_en', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='fecha y hora')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='intentos_acceso', to=settings.AUTH_USER_MODEL, verbose_name='usuario')),
            ],
            options={
                'verbose_name': 'intento de acceso',
                'verbose_name_plural': 'intentos de acceso',
                'db_table': 'usuarios_intento_acceso',
                'ordering': ['-ocurrido_en'],
                'indexes': [models.Index(fields=['email_ingresado', 'exitoso', 'ocurrido_en'], name='idx_intento_email_exito')],
            },
        ),
        migrations.AddIndex(
            model_name='usuario',
            index=models.Index(fields=['rol', 'is_active'], name='idx_usuario_rol_activo'),
        ),
    ]
