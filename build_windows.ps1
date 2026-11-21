$ErrorActionPreference = "Stop"

python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "L’installation des dépendances de compilation a échoué."
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name AnalysePME `
    --collect-all webview `
    --exclude-module webview.platforms.android `
    --hidden-import webview.platforms.edgechromium `
    lancer_analyse_pme.py

if ($LASTEXITCODE -ne 0) {
    throw "La génération de l’exécutable a échoué."
}

$webView2Bootstrapper = Join-Path (Get-Location) "build\MicrosoftEdgeWebView2Setup.exe"
if (-not (Test-Path $webView2Bootstrapper)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $webView2Bootstrapper) | Out-Null
    Invoke-WebRequest `
        -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" `
        -OutFile $webView2Bootstrapper
}

$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $compiler) {
    $compilerCandidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    $compilerPath = $compilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $compilerPath) {
        throw "Inno Setup 6 est requis pour créer l’installateur. Installez-le puis relancez ce script."
    }
} else {
    $compilerPath = $compiler.Source
}

& $compilerPath ".\installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "La création de l’installateur a échoué."
}

Write-Host ""
Write-Host "Installateur créé : dist\Installateur\AnalysePME-Setup.exe"
