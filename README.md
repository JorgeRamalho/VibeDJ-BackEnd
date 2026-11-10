# VibeDJ Stems

Backend local que separa uma faixa em vocals, bass, other, drums, kick, snare, cymbals e toms. Fica na bandeja do Windows e atende o laboratório em `http://127.0.0.1:8777`.

A v1 roda na CPU. O provedor ONNX entra em `%LOCALAPPDATA%\VibeDJStems\config.json`, para a etapa com CUDA trocar a lista sem mudar código:

```json
{
  "origens": ["https://seu-dominio.netlify.app"],
  "provedores": ["CPUExecutionProvider"]
}
```

`localhost` e `127.0.0.1` em qualquer porta já são aceitos. O domínio publicado precisa estar em `origens`.

## Rodar em desenvolvimento

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m vibedj_stems
```

Na primeira abertura os dois modelos (cerca de 500 MB) baixam para `%LOCALAPPDATA%\VibeDJStems\models`. O ícone fica em "Carregando" até as sessões abrirem, e em "Pronto" depois. Sair está no menu do ícone.

## Executável

```powershell
.\build.ps1
```

O resultado é um único `dist\VibeDJStems.exe`. As bibliotecas vão dentro dele; não há pasta de DLLs para copiar junto.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```
