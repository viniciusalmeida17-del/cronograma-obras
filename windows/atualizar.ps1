# Atualiza o Cronograma de Obras: fecha o app se estiver aberto, faz git pull e instala o requirements.txt no .venv.
# Mostra numa janela se deu certo ou qual foi o erro. Registro completo em logs\atualizacao.log.
# -Reabrir: pedido pelo botão "Atualizar agora" da tela. Abre o app de novo no fim (a página recarrega sozinha)
#           e só mostra janela se der erro.
param([switch]$Reabrir)
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'

$raiz = Split-Path -Parent $PSScriptRoot
$titulo = 'Atualizar Cronograma de Obras'
$shell = New-Object -ComObject WScript.Shell
$pastaLogs = Join-Path $raiz 'logs'
New-Item -ItemType Directory -Force -Path $pastaLogs | Out-Null
$log = Join-Path $pastaLogs 'atualizacao.log'
$porta = if ($env:PORTA) { $env:PORTA } else { '5000' }

function Registrar([string]$texto) {
    Add-Content -Path $log -Encoding UTF8 -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $texto)
}

function Janela([string]$texto, [int]$icone) {
    # 16 = erro, 64 = informação; 0 = espera o OK
    [void]$shell.Popup($texto, 0, $titulo, $icone)
}

function Final([string]$texto, [int]$limite = 1200) {
    $texto = $texto.Trim()
    if ($texto.Length -gt $limite) { $texto = '...' + $texto.Substring($texto.Length - $limite) }
    return $texto
}

function Rodar([string]$exe, [string[]]$argumentos) {
    Registrar ("> $exe " + ($argumentos -join ' '))
    $saida = & $exe @argumentos 2>&1 | ForEach-Object { "$_" } | Out-String
    $codigo = $LASTEXITCODE
    Registrar $saida
    return @{ Codigo = $codigo; Saida = $saida }
}

function Abrir-App {
    # a aba que pediu a atualização recarrega sozinha: não abre outra
    $env:ABRIR_NAVEGADOR = '0'
    $vbs = Join-Path $raiz 'windows\abrir.vbs'
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\wscript.exe') -ArgumentList ('"' + $vbs + '"')
    Registrar 'App aberto de novo.'
}

function Falhou([string]$texto) {
    Registrar "ERRO: $texto"
    $extra = ''
    if ($Reabrir) {
        Abrir-App
        $extra = "`n`nO app foi aberto de novo na versão anterior."
    }
    Janela ($texto + $extra + "`n`nRegistro completo em logs\atualizacao.log.") 16
    exit 1
}

Registrar '=== Atualização iniciada ==='
Set-Location $raiz

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Falhou "Não encontrei o Git neste computador.`n`nInstale o Git for Windows (git-scm.com) e tente de novo."
}
$python = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Falhou "Não encontrei o ambiente do Python (.venv) em:`n$raiz`n`nCrie com os comandos da seção ""Windows (uma vez só)"" do README.md."
}

# avisa que começou (some sozinho em 4 segundos); pela tela, a própria página já avisa
if (-not $Reabrir) { [void]$shell.Popup("Atualizando... pode levar alguns minutos.`nAparece outra janela quando terminar.", 4, $titulo, 64) }

# o app aberto prende arquivos do .venv: fecha antes de instalar
$fechouApp = $false
try {
    $sobre = Invoke-RestMethod -Uri "http://127.0.0.1:$porta/api/sobre" -TimeoutSec 2
    if ($sobre.app -eq 'cronograma-obras') {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$porta/api/fechar" -Headers @{ 'X-Fechar' = '1' } -TimeoutSec 5 | Out-Null
        # espera o app terminar de fechar (até 15 s)
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            try { Invoke-RestMethod -Uri "http://127.0.0.1:$porta/api/sobre" -TimeoutSec 1 | Out-Null } catch { break }
        }
        $fechouApp = $true
        Registrar 'App aberto: fechado antes de atualizar.'
    }
} catch {}

$antes = (Rodar 'git' @('rev-parse', '--short', 'HEAD')).Saida.Trim()
$pull = Rodar 'git' @('pull', '--ff-only')
if ($pull.Codigo -ne 0) {
    Falhou ("O git pull falhou (nada foi alterado no app):`n`n" + (Final $pull.Saida))
}
$depois = (Rodar 'git' @('rev-parse', '--short', 'HEAD')).Saida.Trim()

$pip = Rodar $python @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.txt')
if ($pip.Codigo -ne 0) {
    Falhou ("O código foi atualizado, mas a instalação dos pacotes (requirements.txt) falhou:`n`n" + (Final $pip.Saida))
}

if ($antes -eq $depois) {
    $msg = "Tudo certo: o app já estava na versão mais recente ($depois).`nPacotes do Python conferidos."
} else {
    $novidades = (Rodar 'git' @('log', '--format=- %s', "$antes..$depois")).Saida
    $msg = "Atualizado com sucesso ($antes -> $depois).`n`nNovidades:`n" + (Final $novidades 900)
}
Registrar 'Atualização concluída.'
if ($Reabrir) {
    Abrir-App
} else {
    if ($fechouApp) { $msg += "`n`nO app estava aberto e foi fechado. Abra de novo pelo atalho." }
    Janela $msg 64
}
