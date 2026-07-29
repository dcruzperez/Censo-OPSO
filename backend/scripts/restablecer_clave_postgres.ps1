<#
=============================================================================
 OPSO - Restablecer la contrasena del superusuario "postgres"
=============================================================================

 PARA QUE SIRVE
 Recupera el acceso a PostgreSQL cuando se olvido la contrasena del usuario
 "postgres", SIN reinstalar y SIN perder datos.

 COMO SE USA
   1. Abre PowerShell COMO ADMINISTRADOR
      (tecla Windows -> escribe "PowerShell" -> clic derecho ->
       "Ejecutar como administrador")
   2. Ejecuta:

        cd "c:\Users\Familia Cruz Perez\Documents\proyecto titulo\stock-flow-main\backend\scripts"
        powershell -ExecutionPolicy Bypass -File .\restablecer_clave_postgres.ps1

   3. Te pedira la contrasena NUEVA que quieras ponerle a "postgres".

=============================================================================
 COMO FUNCIONA (esto es lo que conviene entender para la defensa)

 PostgreSQL decide COMO autenticar cada conexion en un archivo llamado
 pg_hba.conf ("host based authentication"). Cada linea dice: para este tipo
 de conexion, desde esta direccion, usa este metodo.

 Ahora mismo tu servidor usa el metodo "scram-sha-256", que exige contrasena.
 El procedimiento consiste en:

   1. Cambiar temporalmente ese metodo a "trust", que significa
      "confia en quien se conecte localmente, sin pedir contrasena".
   2. Recargar la configuracion.
   3. Entrar sin contrasena y ejecutar ALTER USER para definir una nueva.
   4. DEVOLVER pg_hba.conf a como estaba.
   5. Recargar otra vez.

 El paso 4 es el critico: dejar "trust" permanentemente significaria que
 cualquier programa del equipo puede entrar a la base de datos sin
 credenciales. Por eso el script restaura el archivo dentro de un bloque
 "finally": se ejecuta SIEMPRE, incluso si algo falla en medio.

 Este es el procedimiento documentado oficialmente para esta situacion; no es
 un truco ni una vulnerabilidad.
=============================================================================
#>

[CmdletBinding()]
param(
    # Version de PostgreSQL instalada.
    [string]$Version = "18",

    # Ruta de instalacion, si no es la predeterminada.
    [string]$RutaInstalacion = ""
)

$ErrorActionPreference = "Stop"

function Escribir-Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 70)
    Write-Host "  $texto"
    Write-Host ("=" * 70)
}

function Escribir-Paso($numero, $texto) {
    Write-Host ""
    Write-Host "[$numero] $texto"
}

function Escribir-Ok($texto) {
    Write-Host "    OK   $texto" -ForegroundColor Green
}

function Escribir-Aviso($texto) {
    Write-Host "    !    $texto" -ForegroundColor Yellow
}

function Escribir-Error2($texto) {
    Write-Host "    X    $texto" -ForegroundColor Red
}

Escribir-Titulo "OPSO - Restablecer la contrasena de 'postgres'"

# -------------------------------------------------------------------------
# 1. Verificar que se este ejecutando como administrador
# -------------------------------------------------------------------------
# Sin privilegios elevados no se puede reiniciar el servicio de PostgreSQL
# ni escribir de forma fiable en Program Files.
Escribir-Paso 1 "Verificando privilegios"

$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidad)
$esAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $esAdmin) {
    Escribir-Error2 "Este script necesita privilegios de administrador."
    Write-Host ""
    Write-Host "    Cierra esta ventana y abre PowerShell asi:"
    Write-Host "      tecla Windows -> escribe 'PowerShell' -> clic derecho"
    Write-Host "      -> 'Ejecutar como administrador'"
    Write-Host ""
    exit 1
}
Escribir-Ok "Ejecutando como administrador"

# -------------------------------------------------------------------------
# 2. Localizar la instalacion
# -------------------------------------------------------------------------
Escribir-Paso 2 "Localizando PostgreSQL $Version"

if ([string]::IsNullOrWhiteSpace($RutaInstalacion)) {
    $RutaInstalacion = "C:\Program Files\PostgreSQL\$Version"
}

$archivoHba   = Join-Path $RutaInstalacion "data\pg_hba.conf"
$psql         = Join-Path $RutaInstalacion "bin\psql.exe"
$nombreServicio = "postgresql-x64-$Version"

if (-not (Test-Path $archivoHba)) {
    Escribir-Error2 "No se encontro $archivoHba"
    Write-Host "    Usa -RutaInstalacion para indicar la carpeta correcta, o -Version."
    exit 1
}
if (-not (Test-Path $psql)) {
    Escribir-Error2 "No se encontro $psql"
    exit 1
}

$servicio = Get-Service -Name $nombreServicio -ErrorAction SilentlyContinue
if ($null -eq $servicio) {
    Escribir-Error2 "No existe el servicio '$nombreServicio'."
    Write-Host "    Servicios de PostgreSQL encontrados en este equipo:"
    Get-Service -Name "*postgres*" | ForEach-Object { Write-Host "      $($_.Name)" }
    exit 1
}

Escribir-Ok "Instalacion: $RutaInstalacion"
Escribir-Ok "Servicio   : $nombreServicio ($($servicio.Status))"

# -------------------------------------------------------------------------
# 3. Pedir la contrasena nueva
# -------------------------------------------------------------------------
Escribir-Paso 3 "Contrasena NUEVA para el usuario 'postgres'"
Write-Host "    Anotala: la necesitaras para el script preparar_base_datos.py."
Write-Host "    No se muestra al escribirla."

$segura1 = Read-Host "    Contrasena nueva" -AsSecureString
$segura2 = Read-Host "    Repitela" -AsSecureString

# Se convierten a texto plano solo en memoria y por el tiempo minimo necesario.
$claveNueva  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura1))
$claveNueva2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura2))

if ($claveNueva -ne $claveNueva2) {
    Escribir-Error2 "Las contrasenas no coinciden. No se hizo ningun cambio."
    exit 1
}
if ([string]::IsNullOrWhiteSpace($claveNueva)) {
    Escribir-Error2 "La contrasena no puede estar vacia."
    exit 1
}
if ($claveNueva.Length -lt 8) {
    Escribir-Aviso "La contrasena es corta (menos de 8 caracteres)."
}
if ($claveNueva -match "'") {
    Escribir-Error2 "La contrasena no puede contener comillas simples ( ' )."
    exit 1
}
Escribir-Ok "Contrasena aceptada"

# -------------------------------------------------------------------------
# 4. Respaldar pg_hba.conf
# -------------------------------------------------------------------------
Escribir-Paso 4 "Respaldando pg_hba.conf"

$marca    = Get-Date -Format "yyyyMMdd-HHmmss"
$respaldo = "$archivoHba.opso-backup-$marca"
Copy-Item -Path $archivoHba -Destination $respaldo -Force

# Se guarda el contenido en memoria para poder restaurarlo con exactitud.
$contenidoOriginal = Get-Content -Path $archivoHba -Raw -Encoding UTF8

Escribir-Ok "Respaldo: $(Split-Path $respaldo -Leaf)"

# -------------------------------------------------------------------------
# 5. Cambiar a 'trust', restablecer la clave y volver a 'scram-sha-256'
# -------------------------------------------------------------------------
# Todo dentro de try/finally: el archivo se restaura SIEMPRE, incluso si algo
# falla a mitad de camino. Dejar 'trust' activo seria un problema real de
# seguridad, y esa es justamente la parte que no se puede olvidar.

$restaurado = $false

try {
    Escribir-Paso 5 "Activando el modo 'trust' temporalmente"

    # Se reescriben solo las lineas de conexion LOCAL, dejando intactos los
    # comentarios y cualquier regla para direcciones remotas.
    $lineasNuevas = @()
    $cambiadas = 0

    foreach ($linea in ($contenidoOriginal -split "`r?`n")) {
        if ($linea -match '^\s*#' -or $linea -match '^\s*$') {
            # Comentario o linea vacia: se deja igual.
            $lineasNuevas += $linea
            continue
        }

        $campos = $linea -split '\s+' | Where-Object { $_ -ne "" }

        $esLocal = $false
        if ($campos.Count -ge 4 -and $campos[0] -eq "local") {
            $esLocal = $true
        }
        if ($campos.Count -ge 5 -and $campos[0] -eq "host" -and
            ($campos[3] -eq "127.0.0.1/32" -or $campos[3] -eq "::1/128")) {
            $esLocal = $true
        }

        if ($esLocal) {
            # Se reemplaza el ultimo campo (el metodo) por 'trust'.
            $campos[$campos.Count - 1] = "trust"
            $lineasNuevas += ($campos -join "`t")
            $cambiadas++
        }
        else {
            $lineasNuevas += $linea
        }
    }

    if ($cambiadas -eq 0) {
        throw "No se encontraron reglas de conexion local en pg_hba.conf."
    }

    # Se escribe SIN BOM: PostgreSQL no interpreta bien un BOM en pg_hba.conf.
    $sinBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($archivoHba, ($lineasNuevas -join "`r`n"), $sinBom)

    Escribir-Ok "$cambiadas regla(s) local(es) cambiadas a 'trust'"

    # ---------------------------------------------------------------------
    Escribir-Paso 6 "Reiniciando el servicio para aplicar el cambio"
    Restart-Service -Name $nombreServicio -Force
    Start-Sleep -Seconds 3

    $servicio = Get-Service -Name $nombreServicio
    if ($servicio.Status -ne "Running") {
        throw "El servicio no quedo en ejecucion (estado: $($servicio.Status))."
    }
    Escribir-Ok "Servicio reiniciado"

    # ---------------------------------------------------------------------
    Escribir-Paso 7 "Definiendo la contrasena nueva"

    # La instruccion se envia por la ENTRADA ESTANDAR y no como argumento de
    # linea de comandos. Motivo: los argumentos son visibles en la lista de
    # procesos del sistema, y la contrasena quedaria expuesta unos instantes.
    $sql = "ALTER USER postgres WITH PASSWORD '$claveNueva';"
    $salida = $sql | & $psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "psql devolvio un error: $salida"
    }
    Escribir-Ok "Contrasena actualizada en el servidor"
}
finally {
    # -----------------------------------------------------------------
    Escribir-Paso 8 "Restaurando pg_hba.conf (paso obligatorio)"

    $sinBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($archivoHba, $contenidoOriginal, $sinBom)
    $restaurado = $true
    Escribir-Ok "Archivo restaurado a su contenido original"

    Escribir-Paso 9 "Reiniciando el servicio con la configuracion original"
    try {
        Restart-Service -Name $nombreServicio -Force
        Start-Sleep -Seconds 3
        Escribir-Ok "Servicio reiniciado: la autenticacion por contrasena esta activa otra vez"
    }
    catch {
        Escribir-Error2 "No se pudo reiniciar el servicio: $($_.Exception.Message)"
        Escribir-Aviso "Reinicialo manualmente:  Restart-Service $nombreServicio"
    }
}

# -------------------------------------------------------------------------
# 10. Verificar que la contrasena nueva funciona
# -------------------------------------------------------------------------
Escribir-Paso 10 "Verificando la contrasena nueva"

$env:PGPASSWORD = $claveNueva
try {
    $resultado = & $psql -U postgres -d postgres -t -A -c "SELECT 'conexion correcta'" 2>&1
    if ($LASTEXITCODE -eq 0 -and $resultado -match "conexion correcta") {
        Escribir-Ok "La contrasena nueva funciona"
        $exito = $true
    }
    else {
        Escribir-Error2 "No se pudo verificar: $resultado"
        $exito = $false
    }
}
finally {
    # Se limpia la variable de entorno para que la contrasena no quede en la
    # sesion de PowerShell.
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

# -------------------------------------------------------------------------
# Cierre
# -------------------------------------------------------------------------
if ($exito -and $restaurado) {
    Escribir-Titulo "LISTO"
    Write-Host "  La contrasena de 'postgres' quedo restablecida y la"
    Write-Host "  autenticacion por contrasena sigue activa (no se quedo en 'trust')."
    Write-Host ""
    Write-Host "  Siguiente paso: crear la base de datos de OPSO." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "      cd `"$(Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)`""
    Write-Host "      cd backend"
    Write-Host "      ..\.venv\Scripts\python.exe scripts\preparar_base_datos.py --migrar"
    Write-Host ""
    Write-Host "  Te pedira la contrasena que acabas de definir."
    Write-Host ""
    Write-Host "  El respaldo de pg_hba.conf quedo en:"
    Write-Host "      $respaldo"
    Write-Host "  Puedes borrarlo cuando quieras."
    Write-Host ""
}
else {
    Escribir-Titulo "REVISAR"
    Write-Host "  Algo no quedo bien. Comprueba que pg_hba.conf este correcto:"
    Write-Host "      $archivoHba"
    Write-Host "  Si hiciera falta, restauralo desde el respaldo:"
    Write-Host "      Copy-Item '$respaldo' '$archivoHba' -Force"
    Write-Host "      Restart-Service $nombreServicio"
    Write-Host ""
    exit 1
}
