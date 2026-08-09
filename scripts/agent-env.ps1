$ErrorActionPreference = "Stop"
$Command = [string[]] $args

$scriptPath = $PSCommandPath
if (-not $scriptPath) {
    $scriptPath = $MyInvocation.MyCommand.Path
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $scriptPath) "..")
$agentTempRoot = Join-Path $repoRoot ".tmp"

$env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"
$env:TEMP = $agentTempRoot
$env:TMP = $agentTempRoot

if (-not $env:COREPACK_HOME) {
    $env:COREPACK_HOME = Join-Path $repoRoot ".corepack"
}

New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:TEMP, $env:COREPACK_HOME | Out-Null

$preferredToolDirs = @(
    "Y:\Software\just",
    "Y:\Software\nodes\nodejs"
)

$toolDirsToPrepend = $preferredToolDirs.Clone()
[array]::Reverse($toolDirsToPrepend)
foreach ($toolDir in $toolDirsToPrepend) {
    if ((Test-Path -LiteralPath $toolDir) -and (($env:Path -split ";") -notcontains $toolDir)) {
        $env:Path = "$toolDir;$env:Path"
    }
}

function global:pnpm {
    corepack pnpm @args
}

function global:zml-agent-env {
    [PSCustomObject]@{
        RepoRoot      = $repoRoot.Path
        UV_CACHE_DIR  = $env:UV_CACHE_DIR
        COREPACK_HOME = $env:COREPACK_HOME
        TEMP          = $env:TEMP
        Just          = (Get-Command just -ErrorAction SilentlyContinue).Source
        Corepack      = (Get-Command corepack -ErrorAction SilentlyContinue).Source
        Node          = (Get-Command node -ErrorAction SilentlyContinue).Source
    }
}

if ($Command.Count -gt 0) {
    if ($Command[0] -eq "--") {
        $Command = if ($Command.Count -gt 1) { $Command[1..($Command.Count - 1)] } else { @() }
    }
}

if ($Command.Count -gt 0) {
    $program = $Command[0]
    $programArgs = if ($Command.Count -gt 1) { $Command[1..($Command.Count - 1)] } else { @() }

    if ($program -eq "pnpm") {
        & corepack pnpm @programArgs
    } else {
        & $program @programArgs
    }

    exit $LASTEXITCODE
}

zml-agent-env
