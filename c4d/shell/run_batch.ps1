# run_batch.ps1
# Orchestrateur générique : relance un process c4dpy.exe frais pour chaque fichier trouvé dans un dossier,
# plutôt que de tout traiter dans un seul process long-terme.
# C4D headless (c4dpy) peut accumuler des fuites mémoire sur de gros batches et finir par planter.
# En isolant chaque fichier dans son propre process, un plantage se limite à un seul fichier, les autres continuent normalement.
#
# Fonctionne avec n'importe quel script c4dpy concu sur le modèle "un fichier = un argument = un process"
# (le script recoit le chemin complet du fichier en argv[1] et sort avec un code non-nul en cas d'échec).
#
# Usage :
#   .\run_batch.ps1 -C4dpyPath "C:\...\c4dpy.exe" -ScriptPath "...\script.py" -SourceFolder "..." -Extension ".usdz"
# Ou sans paramètres : le script demande tout interactivement

param(
    [string]$C4dpyPath,
    [string]$ScriptPath,
    [string]$SourceFolder,
    [string]$Extension,
    [string]$LogFolder
)

# Filet de securité si un chemin collé garde ses guillemets (via "Copier en tant que chemin d'accès").
function Strip-Quotes([string]$Path) {
    if ($Path) { return $Path.Trim('"') }
    return $Path
}

if (-not $SourceFolder) {
    $SourceFolder = Read-Host "Dossier contenant les fichiers à traiter"
}
$SourceFolder = Strip-Quotes $SourceFolder

if (-not $Extension) {
    $Extension = Read-Host "Extension des fichiers à traiter (ex: .usdz)"
}
if ($Extension -and -not $Extension.StartsWith(".")) {
    $Extension = ".$Extension"
}

if (-not $ScriptPath) {
    $scriptFolder = Read-Host "Dossier contenant le script .py à lancer"
    $scriptFolder = Strip-Quotes $scriptFolder

    if ($scriptFolder -and (Test-Path $scriptFolder)) {
        $pyFiles = Get-ChildItem -Path $scriptFolder -Filter *.py
        if ($pyFiles.Count -eq 1) {
            $ScriptPath = $pyFiles[0].FullName
        } elseif ($pyFiles.Count -gt 1) {
            Write-Host "Plusieurs scripts .py trouvés dans ce dossier :"
            for ($i = 0; $i -lt $pyFiles.Count; $i++) {
                Write-Host "  [$i] $($pyFiles[$i].Name)"
            }
            $choice = Read-Host "Lequel utiliser (numero)"
            if ($choice -match '^\d+$' -and [int]$choice -lt $pyFiles.Count) {
                $ScriptPath = $pyFiles[[int]$choice].FullName
            }
        }
    }
}
$ScriptPath = Strip-Quotes $ScriptPath

if (-not $C4dpyPath) {
    # On demande le dossier d'installation de C4D (ex: C:\Program Files\Maxon Cinema 4D 2026) plutôt que le chemin complet de c4dpy.exe
    # plus simple à trouver, le script complète le nom du .exe lui-même.
    $c4dInstallFolder = Read-Host "Dossier d'installation de Cinema 4D (ex: C:\Program Files\Maxon Cinema 4D 2026)"
    $c4dInstallFolder = Strip-Quotes $c4dInstallFolder
    if ($c4dInstallFolder) {
        $C4dpyPath = Join-Path $c4dInstallFolder "c4dpy.exe"
    }
}
$C4dpyPath = Strip-Quotes $C4dpyPath

# Validation avant de lancer
if (-not $Extension) {
    Write-Error "Aucune extension fournie."
    exit 1
}
if (-not (Test-Path $C4dpyPath)) {
    Write-Error "c4dpy.exe introuvable : $C4dpyPath"
    exit 1
}
if (-not $ScriptPath -or -not (Test-Path $ScriptPath)) {
    Write-Error "Script introuvable : $ScriptPath"
    exit 1
}
if (-not (Test-Path $SourceFolder)) {
    Write-Error "Dossier source introuvable : $SourceFolder"
    exit 1
}

$files = Get-ChildItem -Path $SourceFolder -Filter "*$Extension"
if ($files.Count -eq 0) {
    Write-Error "Aucun fichier $Extension trouvé dans $SourceFolder"
    exit 1
}

Write-Host "$($files.Count) fichier(s) $Extension trouvé(s)"

# Récapitulatif d'échecs de cet orchestrateur
# Par defaut dans <SourceFolder>\_logs, redéfinissable via -LogFolder.
# Crée seulement s'il y a effectivement des échecs à y consigner.
if (-not $LogFolder) {
    $LogFolder = Join-Path $SourceFolder "_logs"
}
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$summaryPath = Join-Path $LogFolder "run_${timestamp}_echecs.txt"

$failed = @()

foreach ($f in $files) {
    Write-Host "`n=== $($f.Name) ==="
    & $C4dpyPath $ScriptPath $f.FullName

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ATTENTION] c4dpy a quitté avec un code d'erreur ($LASTEXITCODE) pour $($f.Name) -- fichier suivant"
        $failed += [PSCustomObject]@{
            Fichier   = $f.Name
            ExitCode  = $LASTEXITCODE
            Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        }
    }
}

Write-Host "`nTermine."
if ($failed.Count -gt 0) {
    Write-Host "Fichier(s) en échec : $($failed.Fichier -join ', ')"

    New-Item -ItemType Directory -Path $LogFolder -Force | Out-Null
    $lines = $failed | ForEach-Object { "$($_.Timestamp)  $($_.Fichier)  (exit code $($_.ExitCode))" }
    Set-Content -Path $summaryPath -Value $lines -Encoding UTF8
    Write-Host "Récapitulatif écrit dans $summaryPath"
} else {
    Write-Host "Tous les fichiers ont été traités sans erreur de process."
}
