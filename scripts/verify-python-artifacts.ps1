param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$BackendArtifactDir,
    [string]$AgentArtifactDir,
    [switch]$SkipProcessTree
)

$ErrorActionPreference = "Stop"

$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$backendDir = if ($BackendArtifactDir) {
    (Resolve-Path -LiteralPath $BackendArtifactDir).Path
} else {
    Join-Path $resolvedRepoRoot "apps/backend/dist/zml-backend"
}
$agentDir = if ($AgentArtifactDir) {
    (Resolve-Path -LiteralPath $AgentArtifactDir).Path
} else {
    Join-Path $resolvedRepoRoot "apps/ocr-worker/dist/zml-ocr-worker"
}
$backendExe = Join-Path $backendDir "zml-backend.exe"
$agentExe = Join-Path $agentDir "zml-ocr-worker.exe"

foreach ($requiredPath in @($backendExe, $agentExe)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required packaged executable is missing: $requiredPath"
    }
}

$forbiddenBridgeEntries = @(
    Get-ChildItem -LiteralPath $backendDir -Recurse -Force |
        Where-Object { $_.Name -match "^(cv2|mss|numpy|opencv|tesserocr|tessdata|win32gui|win32ui)(\.|$)" }
)
if ($forbiddenBridgeEntries.Count -gt 0) {
    $paths = $forbiddenBridgeEntries.FullName -join [Environment]::NewLine
    throw "Backend still contains OCR-native artifacts:$([Environment]::NewLine)$paths"
}

foreach ($trainedData in @("eng.traineddata", "osd.traineddata")) {
    $path = Join-Path $agentDir "_internal/tessdata/$trainedData"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "OCR Worker tessdata is missing: $path"
    }
}

function Invoke-PackagedCommand {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )

    $output = & $Executable @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable $($Arguments -join ' ') failed with exit code $LASTEXITCODE`n$output"
    }
    $output | Write-Host
}

Invoke-PackagedCommand -Executable $agentExe -Arguments @("--version")
Invoke-PackagedCommand -Executable $agentExe -Arguments @("doctor")
Invoke-PackagedCommand -Executable $backendExe -Arguments @("config")

function Test-AgentProtocol {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $agentExe
    $startInfo.Arguments = "stdio"
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Failed to start packaged OCR Worker"
    }

    $helloLine = $process.StandardOutput.ReadLine()
    $hello = $helloLine | ConvertFrom-Json
    if ($hello.type -ne "hello" -or $hello.protocol_version -ne 1) {
        $process.Kill()
        throw "Expected protocol v1 hello, got: $helloLine"
    }

    $shutdown = @{
        protocol_version = 1
        type = "shutdown"
        command_id = "ffffffffffffffffffffffffffffffff"
        sent_ts_ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        payload = @{ reason = "backend_shutdown" }
    } | ConvertTo-Json -Compress -Depth 4
    $process.StandardInput.WriteLine($shutdown)
    $process.StandardInput.Flush()

    if (-not $process.WaitForExit(15000)) {
        $process.Kill()
        $process.WaitForExit()
        throw "Packaged OCR Worker did not accept shutdown"
    }

    $remainingOutput = $process.StandardOutput.ReadToEnd()
    $standardError = $process.StandardError.ReadToEnd()
    if ($process.ExitCode -ne 0) {
        throw "Packaged OCR Worker exited with $($process.ExitCode): $standardError"
    }

    $messages = @(
        $remainingOutput -split "`r?`n" |
            Where-Object { $_ } |
            ForEach-Object { $_ | ConvertFrom-Json }
    )
    $shutdownResult = $messages | Where-Object {
        $_.type -eq "command_result" -and
        $_.payload.command_type -eq "shutdown" -and
        $_.payload.status -eq "ok"
    }
    if (-not $shutdownResult) {
        throw "Packaged OCR Worker did not emit a successful shutdown result: $remainingOutput"
    }
}

Test-AgentProtocol

if (-not $SkipProcessTree) {
    $port = Get-Random -Minimum 20000 -Maximum 40000
    $smokeData = Join-Path $resolvedRepoRoot ".tmp/packaged-process-smoke-$([Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $smokeData -Force | Out-Null

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $backendExe
    $startInfo.Arguments = "serve --mode live"
    $startInfo.WorkingDirectory = $backendDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.EnvironmentVariables["ZML_HOST"] = "127.0.0.1"
    $startInfo.EnvironmentVariables["ZML_PORT"] = [string]$port
    $startInfo.EnvironmentVariables["ZML_APP_DATA_DIR"] = $smokeData
    $startInfo.EnvironmentVariables["ZML_CHAT_LOG_PATH"] = Join-Path $smokeData "chat.log"
    $startInfo.EnvironmentVariables["ZML_OCR_CAPTURE_HZ"] = "1"
    $startInfo.EnvironmentVariables["ZML_OCR_WORKER_PATH"] = $agentExe
    $startInfo.EnvironmentVariables["ZML_PARENT_MANAGED"] = "1"

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Failed to start packaged Backend"
    }

    try {
        $health = $null
        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        while ([DateTime]::UtcNow -lt $deadline) {
            try {
                $candidate = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 1
                $candidateOcr = $candidate.workers.ocr_worker
                if (
                    $candidateOcr.details.pid -and
                    $candidateOcr.details.applied_config_revision -eq 1
                ) {
                    $health = $candidate
                    break
                }
            } catch {
                # Startup races are expected while the packaged processes initialize.
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not $health) {
            throw "Packaged process tree did not become healthy"
        }

        $agentPid = [int]$health.workers.ocr_worker.details.pid
        $process.StandardInput.WriteLine("shutdown")
        $process.StandardInput.Flush()
        if (-not $process.WaitForExit(30000)) {
            throw "Packaged Backend did not stop after the parent shutdown command"
        }
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "Packaged Backend exited with $($process.ExitCode)"
        }

        $agentDeadline = [DateTime]::UtcNow.AddSeconds(5)
        while (
            [DateTime]::UtcNow -lt $agentDeadline -and
            (Get-Process -Id $agentPid -ErrorAction SilentlyContinue)
        ) {
            Start-Sleep -Milliseconds 100
        }
        if (Get-Process -Id $agentPid -ErrorAction SilentlyContinue) {
            throw "OCR Worker process $agentPid survived Backend shutdown"
        }
    } finally {
        if (-not $process.HasExited) {
            $process.Kill()
            $process.WaitForExit()
        }
    }
}

Write-Host "Packaged Python artifacts verified successfully."
