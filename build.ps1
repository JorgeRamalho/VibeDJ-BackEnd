# Gera dist\VibeDJStems\VibeDJStems.exe. Os modelos ficam em %LOCALAPPDATA%\VibeDJStems.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    # Na máquina local o launcher py aponta para o 3.12. No runner do GitHub
    # o actions/setup-python deixa python no PATH, e o py -3.12 pode faltar.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
    }
    if (-not (Test-Path .\.venv\Scripts\python.exe)) {
        python -m venv .venv
    }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

& .\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --onedir `
    --noconsole `
    --name VibeDJStems `
    --paths src `
    --collect-all onnxruntime `
    --collect-all pystray `
    --collect-all soundfile `
    --collect-all miniaudio `
    --collect-all soxr `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.lifespan.on `
    --hidden-import soxr `
    src\vibedj_stems\__main__.py

Write-Host "Pronto: dist\VibeDJStems\VibeDJStems.exe"
