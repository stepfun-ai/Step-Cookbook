param([switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$packageDir = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $packageDir
$architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
if ($architecture -ne 'AMD64') { throw '本版本的 Windows 入口支持 x64 处理器。' }
$runtimeDir = Join-Path $packageDir '.runtime'
$uvDir = Join-Path $runtimeDir 'uv-x86_64-pc-windows-msvc'
$uvBin = Join-Path $uvDir 'uv.exe'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if (!(Test-Path -LiteralPath $uvBin)) {
    Write-Host '[1/3] 下载环境管理器 uv 0.12.19……'
    $stageDir = Join-Path $runtimeDir ('download.' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stageDir | Out-Null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $archive = Join-Path $stageDir 'uv.zip'
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 -Uri 'https://github.com/astral-sh/uv/releases/download/0.12.19/uv-x86_64-pc-windows-msvc.zip' -OutFile $archive
        $expected = '6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0'
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw '下载校验未通过，请再次启动以重新下载。'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $stageDir 'expanded')
        $binary = Get-ChildItem -LiteralPath (Join-Path $stageDir 'expanded') -Recurse -Filter 'uv.exe' | Select-Object -First 1
        if (!$binary) { throw '压缩包没有 uv.exe。' }
        New-Item -ItemType Directory -Force -Path $uvDir | Out-Null
        Copy-Item -LiteralPath $binary.FullName -Destination $uvBin
    } finally {
        Remove-Item -LiteralPath $stageDir -Recurse -Force
    }
}
$env:UV_CACHE_DIR = Join-Path $runtimeDir 'cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeDir 'python'
$env:UV_PYTHON_BIN_DIR = Join-Path $runtimeDir 'bin'
$env:UV_NO_CONFIG = '1'
$env:UV_NO_PROGRESS = '1'
$env:UV_HTTP_TIMEOUT = '120'
$env:UV_HTTP_RETRIES = '2'
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONNOUSERSITE = '1'
Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$pythonBin = Join-Path $packageDir '.venv\Scripts\python.exe'
$ready = $false
if (Test-Path -LiteralPath $pythonBin) {
    & $pythonBin setup/check_env.py --quiet
    $ready = $LASTEXITCODE -eq 0
}
if (!$ready) {
    Write-Host '[2/3] 准备专用 Python 3.12.14 和虚拟环境……'
    if (Test-Path -LiteralPath '.venv') {
        Move-Item -LiteralPath '.venv' -Destination (Join-Path $runtimeDir ('previous-env.' + [guid]::NewGuid().ToString('N')))
    }
    & $uvBin venv --no-project --managed-python --python 3.12.14 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 环境准备未完成。' }
    Write-Host '[3/3] 准备本篇所需依赖……'
    if ((Get-Item -LiteralPath setup/requirements.lock).Length -gt 0) {
    & $uvBin pip sync --python $pythonBin --require-hashes --only-binary :all: --default-index https://pypi.org/simple setup/requirements.lock
    if ($LASTEXITCODE -ne 0) { throw '依赖安装未完成。' }
    } else {
        Write-Host '本篇仅使用 Python 标准库，环境已齐全。'
    }
    & $pythonBin setup/check_env.py --mark
    if ($LASTEXITCODE -ne 0) { throw '环境检查未完成。' }
} else {
    Write-Host '环境已就绪，复用本地 Python 与依赖。'
}
if ($SetupOnly) {
    & $pythonBin setup/check_env.py
} else {
    & $pythonBin launcher.py
}
exit $LASTEXITCODE
