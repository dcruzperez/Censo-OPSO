-- =========================================================================
-- OPSO — Creación de la base de datos y del usuario de la aplicación
--
-- ###   FORMA RECOMENDADA: usar el script de Python en su lugar   ###
--
--     cd backend
--     ..\.venv\Scripts\python.exe scripts\preparar_base_datos.py --migrar
--
-- Ese script hace lo mismo que este archivo, pero además:
--   · pide la contraseña sin que quede escrita en ningún archivo,
--   · consulta la configuración real del servidor y elige la codificación
--     y el ordenamiento que ese servidor sí acepta,
--   · genera una contraseña aleatoria fuerte y la escribe en .env,
--   · se puede volver a ejecutar sin romper nada (es idempotente).
--
-- Este archivo .sql se conserva como alternativa manual y como referencia
-- para el informe, porque muestra el SQL exacto que se ejecuta.
--
-- =========================================================================
-- USO MANUAL
--
--   1. Cambia 'CambiaEstaClave2026' por una contraseña propia.
--   2. Ejecuta (pedirá la contraseña del usuario postgres):
--
--        cd backend\scripts
--        "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f crear_base_datos.sql
--
--   3. Copia esa misma contraseña a DB_PASSWORD dentro de backend\.env
--
-- =========================================================================
-- ¿Por qué un usuario propio (opso_user) y no "postgres"?
--
-- Por el principio de PRIVILEGIO MÍNIMO: la aplicación solo necesita leer y
-- escribir en su propia base de datos. Si sus credenciales se filtraran, el
-- atacante no podría tocar otras bases del servidor, ni crear usuarios, ni
-- modificar la configuración de PostgreSQL.
-- =========================================================================


-- -------------------------------------------------------------------------
-- 1. Usuario (rol de conexión) exclusivo de la aplicación
-- -------------------------------------------------------------------------
-- NOSUPERUSER, NOCREATEDB y NOCREATEROLE son explícitos para dejar constancia
-- de que el rol está deliberadamente limitado.
CREATE ROLE opso_user WITH
    LOGIN
    PASSWORD 'CambiaEstaClave2026'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;


-- -------------------------------------------------------------------------
-- 2. Base de datos
-- -------------------------------------------------------------------------
-- ENCODING 'UTF8' es indispensable: los datos incluyen nombres de familias
-- con tildes y ñ, y UTF-8 es el estándar que Django asume.
--
-- ATENCIÓN CON EL ORDENAMIENTO (collation) EN WINDOWS:
--
-- En Windows, los nombres de locale de la biblioteca C no son los códigos
-- ISO ('es-CL'), sino cadenas como 'Spanish_Chile.1252'. Además, una base de
-- datos UTF8 no puede heredar el ordenamiento de una instalación cuyo locale
-- pertenece a otra codificación. Este servidor, por ejemplo, se inicializó
-- con 'Spanish_Spain.1252'.
--
-- Por eso se usa LC_COLLATE = 'C' junto con TEMPLATE = template0:
--   · 'C' es válido con cualquier codificación, en cualquier sistema operativo.
--   · TEMPLATE template0 es obligatorio al cambiar la codificación respecto
--     de la que tiene el servidor por defecto.
--
-- Contrapartida de 'C': el ordenamiento es por bytes, así que las palabras
-- con tilde se ordenan después de la Z ("Zúñiga" antes que "Álvarez"). Si eso
-- importa para los listados, usa la variante con ICU que está más abajo.
CREATE DATABASE opso_db
    WITH OWNER = opso_user
         ENCODING = 'UTF8'
         LC_COLLATE = 'C'
         LC_CTYPE = 'C'
         TEMPLATE = template0;

-- VARIANTE RECOMENDADA si el servidor tiene soporte ICU (PostgreSQL 15 o
-- superior, incluido en las compilaciones oficiales para Windows). Ordena
-- correctamente los acentos y la ñ según las reglas del español de Chile.
-- Para usarla, comenta el CREATE DATABASE de arriba y descomenta este:
--
-- CREATE DATABASE opso_db
--     WITH OWNER = opso_user
--          ENCODING = 'UTF8'
--          LOCALE_PROVIDER = 'icu'
--          ICU_LOCALE = 'es-CL'
--          LC_COLLATE = 'C'
--          LC_CTYPE = 'C'
--          TEMPLATE = template0;
--
-- Para comprobar si hay soporte ICU:
--     SELECT count(*) FROM pg_collation WHERE collprovider = 'i';


-- -------------------------------------------------------------------------
-- 3. Permisos sobre la base de datos
-- -------------------------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE opso_db TO opso_user;


-- -------------------------------------------------------------------------
-- 4. Zona horaria por defecto de las conexiones de este usuario
-- -------------------------------------------------------------------------
ALTER ROLE opso_user SET timezone TO 'America/Santiago';


-- -------------------------------------------------------------------------
-- 5. Permisos sobre el esquema public
-- -------------------------------------------------------------------------
-- IMPORTANTE: desde PostgreSQL 15 el esquema public ya NO es escribible por
-- cualquier usuario; hay que otorgarlo explícitamente. Sin este paso,
-- "python manage.py migrate" falla con:
--     permission denied for schema public
\connect opso_db
GRANT ALL ON SCHEMA public TO opso_user;
ALTER SCHEMA public OWNER TO opso_user;


-- -------------------------------------------------------------------------
-- 6. Verificación
-- -------------------------------------------------------------------------
\echo ''
\echo '--- Base de datos creada. Codificacion y ordenamiento resultantes: ---'
SELECT datname            AS base,
       pg_encoding_to_char(encoding) AS codificacion,
       datcollate         AS ordenamiento,
       pg_get_userbyid(datdba) AS propietario
FROM pg_database
WHERE datname = 'opso_db';

\echo ''
\echo '--- Siguiente paso: copia la contrasena a DB_PASSWORD en backend\.env ---'
\echo '--- Luego ejecuta:  python manage.py migrate                          ---'
