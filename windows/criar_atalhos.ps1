# Cria os atalhos "Cronograma de Obras" e "Atualizar Cronograma de Obras" na área de trabalho e no menu Iniciar.
# Rode uma vez, na pasta do projeto:
#     powershell -ExecutionPolicy Bypass -File windows\criar_atalhos.ps1
# Pode rodar de novo quando quiser (por exemplo, se mudar a pasta do projeto de lugar): os atalhos são substituídos.
$ErrorActionPreference = 'Stop'

$raiz = Split-Path -Parent $PSScriptRoot
$pastaWindows = Join-Path $raiz 'windows'
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'
$shell = New-Object -ComObject WScript.Shell

# Área de trabalho de verdade, mesmo quando o OneDrive a leva para "OneDrive\Área de Trabalho"
$areaDeTrabalho = [Environment]::GetFolderPath('Desktop')
if (-not $areaDeTrabalho -or -not (Test-Path $areaDeTrabalho)) {
    $areaDeTrabalho = $shell.SpecialFolders.Item('Desktop')
}
$menuIniciar = [Environment]::GetFolderPath('Programs')   # menu Iniciar do usuário (não precisa de administrador)

function Criar-Atalho([string]$pasta, [string]$nome, [string]$vbs, [string]$icone, [string]$descricao) {
    $caminho = Join-Path $pasta ($nome + '.lnk')
    $atalho = $shell.CreateShortcut($caminho)
    $atalho.TargetPath = $wscript
    $atalho.Arguments = '"' + (Join-Path $pastaWindows $vbs) + '"'
    $atalho.WorkingDirectory = $raiz
    $atalho.IconLocation = (Join-Path $pastaWindows $icone) + ',0'
    $atalho.Description = $descricao
    $atalho.WindowStyle = 1
    $atalho.Save()
    Write-Host "  $caminho"
}

Write-Host 'Criando atalhos:'
foreach ($pasta in @($areaDeTrabalho, $menuIniciar)) {
    Criar-Atalho $pasta 'Cronograma de Obras' 'abrir.vbs' 'cronograma.ico' 'Abre o Cronograma de Obras no navegador'
    Criar-Atalho $pasta 'Atualizar Cronograma de Obras' 'atualizar.vbs' 'atualizar.ico' 'Baixa a versão nova (git pull) e instala os pacotes'
}

if (-not (Test-Path (Join-Path $raiz '.venv\Scripts\pythonw.exe'))) {
    Write-Host ''
    Write-Host 'Atenção: ainda não existe o .venv nesta pasta. Crie com os comandos do README antes de usar o atalho.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Pronto. Abra o app com dois cliques em "Cronograma de Obras".'
