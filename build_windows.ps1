$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name AnalysePME `
    --add-data "app_ventes.py;." `
    --collect-all streamlit `
    --collect-all altair `
    --collect-all plotly `
    --collect-all supabase `
    --collect-all supabase_auth `
    --collect-all postgrest `
    --collect-all realtime `
    --collect-all storage3 `
    lancer_analyse_pme.py

if ($LASTEXITCODE -ne 0) {
    throw "La génération de l’exécutable a échoué."
}

Write-Host ""
Write-Host "Exécutable créé : dist\AnalysePME\AnalysePME.exe"
Write-Host "Lancez l’exécutable depuis le dossier de distribution."
Write-Host "Configurez vos secrets dans dist\AnalysePME\.streamlit\secrets.toml, sans les partager."
