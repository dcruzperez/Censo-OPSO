"""
OPSO — Preparación de la base de datos PostgreSQL.

QUÉ HACE (todo en un solo paso, y se puede volver a ejecutar sin problemas):

  1. Pide la contraseña del superusuario "postgres" de forma interactiva.
     No se escribe en pantalla, no queda en el historial del terminal y no se
     guarda en ningún archivo.
  2. Se conecta y muestra la configuración real del servidor.
  3. Genera una contraseña aleatoria fuerte para el usuario de la aplicación.
  4. Crea el rol "opso_user" y la base "opso_db" con la codificación y el
     ordenamiento correctos para Windows (los elige según lo que soporte
     este servidor concreto).
  5. Otorga los permisos necesarios sobre el esquema public.
  6. Escribe la contraseña generada en el archivo .env.
  7. Verifica la conexión ya como usuario de la aplicación.

USO:

    cd backend
    ..\\.venv\\Scripts\\python.exe scripts\\preparar_base_datos.py

    # o haciendo además las migraciones y los usuarios de demostración:
    ..\\.venv\\Scripts\\python.exe scripts\\preparar_base_datos.py --migrar

POR QUÉ UN SCRIPT DE PYTHON Y NO UN ARCHIVO .sql:
  - Un .sql es "ciego": ejecuta siempre lo mismo. Si la codificación o el
    locale no coinciden con los de este servidor, falla con un error difícil
    de interpretar. Este script consulta primero y decide después.
  - Permite pedir la contraseña con getpass, sin que quede en un archivo.
  - Es idempotente: detecta lo que ya existe y no lo vuelve a crear.
"""

import argparse
import getpass
import os
import re
import secrets
import string
import subprocess
import sys
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError:
    sys.exit(
        "ERROR: falta psycopg. Ejecuta primero:\n"
        "    ..\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    )

# El script vive en backend/scripts/, así que la raíz del proyecto Django
# (donde está manage.py y .env) es la carpeta superior.
DIRECTORIO_BACKEND = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = DIRECTORIO_BACKEND / ".env"


# ==========================================================================
# Salida a prueba de codificaciones
# ==========================================================================
# La consola de Windows suele usar cp1252, que no puede representar todos los
# caracteres Unicode. PostgreSQL devuelve sus mensajes de error en el idioma y
# la codificación del servidor (aquí Spanish_Spain.1252); al decodificarlos,
# los bytes que no calzan se convierten en el carácter de reemplazo U+FFFD, y
# ese carácter NO existe en cp1252.
#
# Sin esta línea, imprimir un mensaje de error de PostgreSQL provoca un
# UnicodeEncodeError: el manejador de errores fallaría justo cuando más se
# necesita, mostrando una traza de Python en vez de una explicación clara.
# errors="replace" sustituye lo que no se puede representar por "?" en lugar
# de lanzar una excepción.
for flujo in (sys.stdout, sys.stderr):
    try:
        flujo.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass  # entorno sin soporte (por ejemplo, salida redirigida a un objeto)


# ==========================================================================
# Utilidades de presentación (solo ASCII: la consola de Windows usa cp1252
# y los caracteres de dibujo tipo box-drawing provocarían errores)
# ==========================================================================


def titulo(texto):
    print()
    print("=" * 70)
    print(f"  {texto}")
    print("=" * 70)


def paso(numero, texto):
    print(f"\n[{numero}] {texto}")


def ok(texto):
    print(f"    OK   {texto}")


def aviso(texto):
    print(f"    !    {texto}")


def pedir_contrasena_superusuario(nombre_superusuario):
    """Obtiene la contrasena del superusuario por el medio mas seguro disponible.

    Orden de preferencia:
      1. La variable de entorno PGPASSWORD, si esta definida. Es la convencion
         estandar de PostgreSQL y sirve para automatizar (por ejemplo, en un
         script de despliegue).
      2. getpass, que la pide por teclado SIN mostrarla en pantalla. Es el
         camino normal cuando una persona ejecuta el script.
      3. La entrada estandar, si el script se ejecuta de forma no interactiva
         (por ejemplo con una tuberia). En Windows getpass lee directamente de
         la consola e ignora las tuberias, por lo que sin este respaldo el
         script se quedaria esperando indefinidamente.
    """
    if os.environ.get("PGPASSWORD"):
        aviso("Usando la contrasena de la variable de entorno PGPASSWORD")
        return os.environ["PGPASSWORD"]

    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass(f"    Contrasena de '{nombre_superusuario}': ")

    aviso("Entrada no interactiva: se lee la contrasena de la entrada estandar")
    linea = sys.stdin.readline() if sys.stdin else ""
    return linea.rstrip("\r\n")


# ==========================================================================
# Generación de la contraseña de la aplicación
# ==========================================================================


def generar_contrasena(largo=28):
    """Genera una contraseña aleatoria criptograficamente segura.

    Se usa secrets y no random: random es predecible si se conoce su estado
    interno, y no debe emplearse para nada relacionado con seguridad.

    Se excluyen los caracteres que complican los archivos .env y las cadenas
    de conexion: comillas, espacios, #, = y la barra invertida.
    """
    alfabeto = string.ascii_letters + string.digits + "-_.+~!*"
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


# ==========================================================================
# Escritura en el archivo .env
# ==========================================================================


def actualizar_env(claves_valores):
    """Reemplaza el valor de las claves indicadas dentro de .env.

    Conserva comentarios, orden y el resto de las variables. Si una clave no
    existe todavia, la agrega al final.
    """
    if not ARCHIVO_ENV.exists():
        sys.exit(
            f"ERROR: no existe {ARCHIVO_ENV}\n"
            "Copia primero la plantilla:  copy .env.example .env"
        )

    lineas = ARCHIVO_ENV.read_text(encoding="utf-8").splitlines()
    pendientes = dict(claves_valores)
    salida = []

    for linea in lineas:
        coincidencia = re.match(r"^(\s*)([A-Z0-9_]+)\s*=", linea)
        if coincidencia and coincidencia.group(2) in pendientes:
            clave = coincidencia.group(2)
            salida.append(f"{clave}={pendientes.pop(clave)}")
        else:
            salida.append(linea)

    for clave, valor in pendientes.items():
        salida.append(f"{clave}={valor}")

    ARCHIVO_ENV.write_text("\n".join(salida) + "\n", encoding="utf-8")


# ==========================================================================
# Creación de la base de datos
# ==========================================================================

# Se intentan tres variantes, de la mejor a la mas compatible. Motivo: en
# Windows los nombres de locale de la biblioteca C no son los codigos ISO
# ("es-CL"), sino cadenas como "Spanish_Chile.1252". Ademas, una base UTF8 no
# puede heredar un locale de una codificacion distinta. Probar en cascada
# evita adivinar y evita un error incomprensible para quien ejecuta el script.

VARIANTES_CREACION = [
    (
        "UTF8 con ordenamiento ICU es-CL (lo ideal: acentos y ñ se ordenan bien)",
        """
        CREATE DATABASE {db}
            WITH OWNER = {rol}
                 ENCODING = 'UTF8'
                 LOCALE_PROVIDER = 'icu'
                 ICU_LOCALE = 'es-CL'
                 LC_COLLATE = 'C'
                 LC_CTYPE = 'C'
                 TEMPLATE = template0
        """,
    ),
    (
        "UTF8 con ordenamiento C (compatible siempre; ordena por bytes)",
        """
        CREATE DATABASE {db}
            WITH OWNER = {rol}
                 ENCODING = 'UTF8'
                 LC_COLLATE = 'C'
                 LC_CTYPE = 'C'
                 TEMPLATE = template0
        """,
    ),
    (
        "Heredando la configuracion por defecto del servidor",
        """
        CREATE DATABASE {db} WITH OWNER = {rol}
        """,
    ),
]


def crear_base(cursor, nombre_db, nombre_rol):
    """Crea la base probando las variantes en orden. Devuelve la usada."""
    ultimo_error = None

    for descripcion, plantilla in VARIANTES_CREACION:
        try:
            cursor.execute(
                sql.SQL(plantilla).format(
                    db=sql.Identifier(nombre_db),
                    rol=sql.Identifier(nombre_rol),
                )
            )
            return descripcion
        except psycopg.Error as error:
            ultimo_error = error
            aviso(f"No se pudo con: {descripcion}")
            aviso(f"     motivo: {str(error).strip().splitlines()[0]}")

    raise SystemExit(f"\nERROR: no fue posible crear la base de datos.\n{ultimo_error}")


# ==========================================================================
# Programa principal
# ==========================================================================


def main():
    analizador = argparse.ArgumentParser(
        description="Crea la base de datos y el usuario de PostgreSQL para OPSO.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analizador.add_argument("--host", default="localhost")
    analizador.add_argument("--port", default="5432")
    analizador.add_argument("--superusuario", default="postgres",
                            help="Superusuario de PostgreSQL (por defecto: postgres)")
    analizador.add_argument("--db", default="opso_db",
                            help="Nombre de la base de datos (por defecto: opso_db)")
    analizador.add_argument("--rol", default="opso_user",
                            help="Usuario de la aplicacion (por defecto: opso_user)")
    analizador.add_argument("--migrar", action="store_true",
                            help="Ejecuta migrate y crear_usuarios_demo al terminar")
    argumentos = analizador.parse_args()

    titulo("OPSO - Preparacion de la base de datos PostgreSQL")
    print(f"  Servidor : {argumentos.host}:{argumentos.port}")
    print(f"  Base     : {argumentos.db}")
    print(f"  Usuario  : {argumentos.rol}")

    # ---------------------------------------------------------------- 1
    paso(1, "Contrasena del superusuario de PostgreSQL")
    print("    Es la que definiste al instalar PostgreSQL.")
    print("    No se muestra al escribirla y no queda guardada en ningun archivo.")
    clave_super = pedir_contrasena_superusuario(argumentos.superusuario)

    if not clave_super:
        sys.exit("\nERROR: no se ingreso ninguna contrasena.")

    # ---------------------------------------------------------------- 2
    paso(2, "Conectando al servidor")
    try:
        # autocommit=True es OBLIGATORIO: PostgreSQL no permite ejecutar
        # CREATE DATABASE dentro de una transaccion.
        conexion = psycopg.connect(
            host=argumentos.host,
            port=argumentos.port,
            user=argumentos.superusuario,
            password=clave_super,
            dbname="postgres",
            autocommit=True,
            connect_timeout=10,
        )
    except psycopg.OperationalError as error:
        mensaje = str(error)
        print(f"    ERROR: {mensaje.strip().splitlines()[0]}")

        # La deteccion se hace en espanol e ingles porque el idioma del mensaje
        # depende del lc_messages del servidor.
        texto = mensaje.lower()
        if "authentication" in texto or "autentif" in texto or "password" in texto:
            print()
            print("    La contrasena del superusuario no es correcta.")
            print("    Es la que definiste durante la instalacion de PostgreSQL,")
            print("    en la pantalla que pedia la clave del usuario 'postgres'.")
            print()
            print("    Si no la recuerdas, tienes dos caminos:")
            print("      a) Reinstalar PostgreSQL (aun no hay datos que perder).")
            print("      b) Restablecerla poniendo 'trust' temporalmente en:")
            print(r"         C:\Program Files\PostgreSQL\18\data\pg_hba.conf")
        elif "could not connect" in texto or "no se pudo conectar" in texto or "refused" in texto:
            print()
            print("    No se pudo contactar al servidor. Verifica que este activo:")
            print('        Get-Service "*postgres*"')
            print("        Start-Service postgresql-x64-18")
        else:
            print()
            print("    Revisa el host, el puerto y que el servicio este ejecutandose.")
        sys.exit(1)

    ok("Conexion establecida")

    with conexion.cursor() as cursor:
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0].split(",")[0]

        cursor.execute(
            """
            SELECT pg_encoding_to_char(encoding), datcollate, datctype
            FROM pg_database WHERE datname = 'template1'
            """
        )
        codificacion, colacion, ctype = cursor.fetchone()

        cursor.execute("SELECT count(*) FROM pg_collation WHERE collprovider = 'i'")
        tiene_icu = cursor.fetchone()[0] > 0

    print(f"    {version}")
    print(f"    Codificacion por defecto : {codificacion}")
    print(f"    Ordenamiento por defecto : {colacion}")
    print(f"    Soporte ICU              : {'si' if tiene_icu else 'no'}")

    if codificacion != "UTF8":
        aviso(f"El servidor usa {codificacion}, no UTF8.")
        aviso("La base de OPSO se creara en UTF8 de todas formas (se explica abajo).")

    # ---------------------------------------------------------------- 3
    paso(3, "Generando la contrasena del usuario de la aplicacion")
    clave_app = generar_contrasena()
    ok(f"Contrasena de {len(clave_app)} caracteres generada (se guardara en .env)")

    # ---------------------------------------------------------------- 4
    paso(4, f"Creando el rol '{argumentos.rol}'")
    with conexion.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (argumentos.rol,))
        existe_rol = cursor.fetchone() is not None

        if existe_rol:
            aviso("El rol ya existia: se actualiza su contrasena")
            cursor.execute(
                sql.SQL("ALTER ROLE {rol} WITH LOGIN PASSWORD {clave}").format(
                    rol=sql.Identifier(argumentos.rol),
                    clave=sql.Literal(clave_app),
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {rol} WITH LOGIN PASSWORD {clave}").format(
                    rol=sql.Identifier(argumentos.rol),
                    clave=sql.Literal(clave_app),
                )
            )
            ok("Rol creado")

        # Zona horaria por defecto de las conexiones de este usuario.
        cursor.execute(
            sql.SQL("ALTER ROLE {rol} SET timezone TO 'America/Santiago'").format(
                rol=sql.Identifier(argumentos.rol)
            )
        )
        # PRIVILEGIO MINIMO: el rol solo puede iniciar sesion y trabajar en su
        # propia base. No es superusuario, no crea bases ni otros roles. Si sus
        # credenciales se filtraran, el dano queda acotado a esta base de datos.
        cursor.execute(
            sql.SQL("ALTER ROLE {rol} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                rol=sql.Identifier(argumentos.rol)
            )
        )
        ok("Privilegios acotados (no es superusuario)")

    # ---------------------------------------------------------------- 5
    paso(5, f"Creando la base de datos '{argumentos.db}'")
    with conexion.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (argumentos.db,))
        existe_db = cursor.fetchone() is not None

    if existe_db:
        aviso("La base ya existia: no se recrea (asi no se pierden datos)")
        with conexion.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER DATABASE {db} OWNER TO {rol}").format(
                    db=sql.Identifier(argumentos.db),
                    rol=sql.Identifier(argumentos.rol),
                )
            )
    else:
        with conexion.cursor() as cursor:
            variante = crear_base(cursor, argumentos.db, argumentos.rol)
        ok(f"Base creada -> {variante}")

    conexion.close()

    # ---------------------------------------------------------------- 6
    paso(6, "Otorgando permisos sobre el esquema public")
    # Desde PostgreSQL 15 el esquema public ya no es escribible por cualquiera:
    # hay que otorgarlo explicitamente. Sin este paso, "migrate" fallaria con
    # "permission denied for schema public".
    conexion_db = psycopg.connect(
        host=argumentos.host,
        port=argumentos.port,
        user=argumentos.superusuario,
        password=clave_super,
        dbname=argumentos.db,
        autocommit=True,
        connect_timeout=10,
    )
    with conexion_db.cursor() as cursor:
        for instruccion in (
            "GRANT ALL ON SCHEMA public TO {rol}",
            "ALTER SCHEMA public OWNER TO {rol}",
            "GRANT ALL ON DATABASE {db} TO {rol}",
        ):
            cursor.execute(
                sql.SQL(instruccion).format(
                    rol=sql.Identifier(argumentos.rol),
                    db=sql.Identifier(argumentos.db),
                )
            )
    conexion_db.close()
    ok("Permisos otorgados")

    # La contrasena del superusuario ya no se necesita: se descarta de memoria.
    del clave_super

    # ---------------------------------------------------------------- 7
    paso(7, "Escribiendo la configuracion en .env")
    actualizar_env(
        {
            "DB_ENGINE": "postgresql",
            "DB_NAME": argumentos.db,
            "DB_USER": argumentos.rol,
            "DB_PASSWORD": clave_app,
            "DB_HOST": argumentos.host,
            "DB_PORT": argumentos.port,
        }
    )
    ok(f"Actualizado {ARCHIVO_ENV.name} (no se versiona en Git)")

    # ---------------------------------------------------------------- 8
    paso(8, "Verificando la conexion como usuario de la aplicacion")
    try:
        prueba = psycopg.connect(
            host=argumentos.host,
            port=argumentos.port,
            user=argumentos.rol,
            password=clave_app,
            dbname=argumentos.db,
            connect_timeout=10,
        )
        with prueba.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), current_user, "
                "pg_encoding_to_char(encoding) FROM pg_database "
                "WHERE datname = current_database()"
            )
            base, usuario, codif = cursor.fetchone()
        prueba.close()
    except psycopg.Error as error:
        sys.exit(f"\nERROR al verificar la conexion:\n{error}")

    ok(f"Conectado a '{base}' como '{usuario}' (codificacion {codif})")

    # ---------------------------------------------------------------- 9
    if argumentos.migrar:
        paso(9, "Aplicando migraciones y creando usuarios de demostracion")
        for comando in (["migrate"], ["crear_usuarios_demo"]):
            print(f"\n    > manage.py {' '.join(comando)}")
            resultado = subprocess.run(
                [sys.executable, "manage.py", *comando],
                cwd=DIRECTORIO_BACKEND,
            )
            if resultado.returncode != 0:
                sys.exit(f"\nERROR: fallo 'manage.py {' '.join(comando)}'")

    # ---------------------------------------------------------------- Fin
    titulo("LISTO")
    if argumentos.migrar:
        print("  La base de datos esta creada y migrada.")
        print()
        print("  Siguiente paso:")
        print("      python manage.py createsuperuser")
        print("      python manage.py runserver")
    else:
        print("  La base de datos y el usuario estan creados.")
        print()
        print("  Siguientes pasos:")
        print("      python manage.py migrate")
        print("      python manage.py crear_usuarios_demo")
        print("      python manage.py createsuperuser")
        print("      python manage.py runserver")
    print()
    print("  La contrasena de la base quedo guardada en backend/.env")
    print("  No necesitas anotarla ni recordarla.")
    print()


if __name__ == "__main__":
    main()
