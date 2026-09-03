$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProofDir = Join-Path $Root "proof"
$ServerStdout = Join-Path $ProofDir "R016_LIVE_APP_SERVER.stdout.log"
$ServerStderr = Join-Path $ProofDir "R016_LIVE_APP_SERVER.stderr.log"
$OllamaStdout = Join-Path $ProofDir "R016_OWNED_OLLAMA.stdout.log"
$OllamaStderr = Join-Path $ProofDir "R016_OWNED_OLLAMA.stderr.log"
$OllamaProof = Join-Path $ProofDir "R016_OLLAMA_PREFLIGHT.json"
$E2EProof = Join-Path $ProofDir "LIVE_DECISION_GATE_PROOF_R016.json"
$HealthProof = Join-Path $ProofDir "R016_LIVE_APP_HEALTH.json"
$Query = "Should our team enable a newly announced AI platform capability in production this week?"
$ProposedAction = "Enable it for one bounded production workload after reviewing current release notes, operational limitations, and recent developer evidence."
$PreferredAppPort = 8765
$MaxAppPort = 8775
$BaseUrl = $null
$PortProof = Join-Path $ProofDir "R016_PORT_SELECTION.json"
$PreferredModel = "qwen3:1.7b"
$ProvenOllamaExe = "H:\Ollama\ollama.exe"
$ProvenModelStore = "H:\DZN32_OLLAMA_MODELS_R110"
$PreferredOwnedOllamaPort = 11438
$MaxOwnedOllamaPort = 11448
$OwnedOllamaHost = $null
$OwnedOllamaUrl = $null

$oldKey = $env:SERPAPI_API_KEY
$oldOllamaUrl = $env:OLLAMA_URL
$oldOllamaModel = $env:OLLAMA_MODEL
$oldOllamaHost = $env:OLLAMA_HOST
$oldOllamaModels = $env:OLLAMA_MODELS
$oldCudaVisible = $env:CUDA_VISIBLE_DEVICES
$oldOllamaVulkan = $env:OLLAMA_VULKAN
$oldVkVisible = $env:GGML_VK_VISIBLE_DEVICES
$oldPort = $env:PORT
$appProc = $null
$ownedOllamaProc = $null

function Restore-EnvValue([string]$Name, $Value) {
    if ($null -eq $Value) {
        Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue
    } else {
        Set-Item ("Env:" + $Name) $Value
    }
}

function Get-OllamaTags([string]$Url) {
    return Invoke-RestMethod -Uri ($Url.TrimEnd('/') + "/api/tags") -Method Get -TimeoutSec 4
}

function Test-OllamaChat([string]$Url, [string]$Model) {
    $body = @{
        model = $Model
        stream = $false
        messages = @(@{ role = "user"; content = "Reply with OK only." })
        options = @{ temperature = 0 }
    } | ConvertTo-Json -Depth 8
    return Invoke-RestMethod -Uri ($Url.TrimEnd('/') + "/api/chat") -Method Post -ContentType "application/json" -Body $body -TimeoutSec 90
}

function Wait-Ollama([string]$Url, [int]$Attempts = 30) {
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $tags = Get-OllamaTags $Url
            if ($null -ne $tags) { return $tags }
        } catch {}
        Start-Sleep -Seconds 1
    }
    throw "Owned Ollama did not become reachable at $Url"
}

function Test-LocalTcpPortFree([int]$Port) {
    try {
        $listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
        return ($listener.Count -eq 0)
    } catch {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $client.Connect("127.0.0.1", $Port)
            return $false
        } catch {
            return $true
        } finally {
            $client.Dispose()
        }
    }
}

Push-Location $Root
try {
    Write-Host "Diamond Evidence Gate - R016 live grounded decision demo capture"
    Write-Host "SerpApi key stays process-scoped. R016 reuses a proven exact-model Ollama service when safe, otherwise selects a free owned Ollama port without killing any process."
    $key = Read-Host "SerpApi API key" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key)
    try {
        $env:SERPAPI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }

    $attempts = @()
    $selectedRoute = $null
    $selectedUrl = $null
    $selectedModel = $null

    # Route A: accept an already-running Ollama only if the exact preferred model is listed
    # and a real /api/chat request succeeds. This avoids the R012 false-positive where
    # /api/tags alone was treated as sufficient readiness.
    $existingUrl = if ($env:OLLAMA_URL) { $env:OLLAMA_URL.Trim().TrimEnd('/') } else { "http://127.0.0.1:11434" }
    if ($existingUrl.EndsWith('/api')) { $existingUrl = $existingUrl.Substring(0, $existingUrl.Length - 4) }
    try {
        $tags = Get-OllamaTags $existingUrl
        $names = @($tags.models | ForEach-Object { $_.name })
        if ($names -contains $PreferredModel) {
            $smoke = Test-OllamaChat $existingUrl $PreferredModel
            $content = (($smoke.message).content | Out-String).Trim()
            if (-not $content) { throw "Chat smoke returned empty content." }
            $selectedRoute = "EXISTING_SERVICE_EXACT_MODEL_CHAT_PROVEN"
            $selectedUrl = $existingUrl
            $selectedModel = $PreferredModel
            $attempts += [ordered]@{ route = "existing_service"; url = $existingUrl; model = $PreferredModel; status = "PASS" }
        } else {
            $attempts += [ordered]@{ route = "existing_service"; url = $existingUrl; model = $PreferredModel; status = "MODEL_NOT_LISTED"; listed_models = $names }
        }
    } catch {
        $attempts += [ordered]@{ route = "existing_service"; url = $existingUrl; model = $PreferredModel; status = "FAIL"; error = $_.Exception.Message }
    }

    # Route B: if the default/existing service is not valid for qwen3:1.7b, start an
    # isolated owned Ollama server over the exact model-store path proven by the prior
    # Local AI R110 host readback. No model download, registry write, service install,
    # or persistent environment mutation is performed.
    if (-not $selectedRoute) {
        if (-not (Test-Path -LiteralPath $ProvenOllamaExe -PathType Leaf)) {
            throw "Owned Ollama executable not found at $ProvenOllamaExe"
        }
        if (-not (Test-Path -LiteralPath $ProvenModelStore -PathType Container)) {
            throw "Previously proven qwen3:1.7b model store not found at $ProvenModelStore"
        }
        # Route B0: a prior R013 run may have left the preferred owned port alive.
        # Reuse it only after exact-model listing + real /api/chat proof. We do not
        # infer PID/process ownership from the port and we never kill it here.
        $preferredOwnedHost = "127.0.0.1:$PreferredOwnedOllamaPort"
        $preferredOwnedUrl = "http://$preferredOwnedHost"
        try {
            $existingOwned = Get-OllamaTags $preferredOwnedUrl
            $existingOwnedNames = @($existingOwned.models | ForEach-Object { $_.name })
            if ($existingOwnedNames -contains $PreferredModel) {
                $existingOwnedSmoke = Test-OllamaChat $preferredOwnedUrl $PreferredModel
                $existingOwnedContent = (($existingOwnedSmoke.message).content | Out-String).Trim()
                if (-not $existingOwnedContent) { throw "Existing preferred owned-port chat smoke returned empty content." }
                $selectedRoute = "REUSED_PREFERRED_OWNED_PORT_EXACT_MODEL_CHAT_PROVEN"
                $selectedUrl = $preferredOwnedUrl
                $selectedModel = $PreferredModel
                $attempts += [ordered]@{ route = "preferred_owned_port_reuse"; url = $preferredOwnedUrl; model = $PreferredModel; status = "PASS"; process_ownership_claimed = $false; process_terminated = $false }
            } else {
                $attempts += [ordered]@{ route = "preferred_owned_port_reuse"; url = $preferredOwnedUrl; model = $PreferredModel; status = "MODEL_NOT_LISTED"; listed_models = $existingOwnedNames; process_terminated = $false }
            }
        } catch {
            $attempts += [ordered]@{ route = "preferred_owned_port_reuse"; url = $preferredOwnedUrl; model = $PreferredModel; status = "UNAVAILABLE_OR_CHAT_FAILED"; error = $_.Exception.Message; process_terminated = $false }
        }

        # Route B1: if preferred-port reuse is not valid, start a fresh owned server
        # on the first free port in the bounded range. No existing process is killed.
        if (-not $selectedRoute) {
            $selectedOwnedPort = $null
            for ($candidateOwnedPort = $PreferredOwnedOllamaPort; $candidateOwnedPort -le $MaxOwnedOllamaPort; $candidateOwnedPort++) {
                if (Test-LocalTcpPortFree $candidateOwnedPort) {
                    $selectedOwnedPort = $candidateOwnedPort
                    break
                }
            }
            if (-not $selectedOwnedPort) {
                throw "No free owned Ollama port found in range $PreferredOwnedOllamaPort-$MaxOwnedOllamaPort. No process was terminated by this runner."
            }
            $OwnedOllamaHost = "127.0.0.1:$selectedOwnedPort"
            $OwnedOllamaUrl = "http://$OwnedOllamaHost"

            $env:OLLAMA_HOST = $OwnedOllamaHost
            $env:OLLAMA_MODELS = $ProvenModelStore
            $env:CUDA_VISIBLE_DEVICES = "-1"
            $env:OLLAMA_VULKAN = "0"
            $env:GGML_VK_VISIBLE_DEVICES = "-1"
            Remove-Item $OllamaStdout -ErrorAction SilentlyContinue
            Remove-Item $OllamaStderr -ErrorAction SilentlyContinue
            $ownedOllamaProc = Start-Process -FilePath $ProvenOllamaExe -ArgumentList "serve" -PassThru -WindowStyle Hidden -RedirectStandardOutput $OllamaStdout -RedirectStandardError $OllamaStderr

            $ownedTags = Wait-Ollama $OwnedOllamaUrl 30
            $ownedNames = @($ownedTags.models | ForEach-Object { $_.name })
            if (-not ($ownedNames -contains $PreferredModel)) {
                throw "Owned model store is reachable but $PreferredModel is not listed. No model download is authorized by this runner."
            }
            $ownedSmoke = Test-OllamaChat $OwnedOllamaUrl $PreferredModel
            $ownedContent = (($ownedSmoke.message).content | Out-String).Trim()
            if (-not $ownedContent) { throw "Owned Ollama chat smoke returned empty content." }
            $selectedRoute = "OWNED_PROVEN_MODEL_STORE_DYNAMIC_PORT_CHAT_PROVEN"
            $selectedUrl = $OwnedOllamaUrl
            $selectedModel = $PreferredModel
            $attempts += [ordered]@{ route = "owned_proven_model_store_dynamic_port"; url = $OwnedOllamaUrl; model = $PreferredModel; model_store = $ProvenModelStore; status = "PASS"; selected_owned_port = $selectedOwnedPort; process_started_by_runner = $true }
        }
    }

    $env:OLLAMA_URL = $selectedUrl
    $env:OLLAMA_MODEL = $selectedModel

    $ollamaReadback = [ordered]@{
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        selected_route = $selectedRoute
        ollama_url = $selectedUrl
        model = $selectedModel
        chat_preflight = "PASS"
        attempts = $attempts
        model_download = $false
        persistent_environment_mutation = $false
        secret_material_in_proof = $false
    }
    $ollamaReadback | ConvertTo-Json -Depth 12 | Set-Content -Path $OllamaProof -Encoding UTF8
    Write-Host "Local Ollama grounded-synthesis preflight PASS: $selectedRoute / $selectedModel"

    $selectedAppPort = $null
    for ($candidatePort = $PreferredAppPort; $candidatePort -le $MaxAppPort; $candidatePort++) {
        if (Test-LocalTcpPortFree $candidatePort) {
            $selectedAppPort = $candidatePort
            break
        }
    }
    if (-not $selectedAppPort) {
        throw "No free local app port found in range $PreferredAppPort-$MaxAppPort. No process was terminated by this runner."
    }
    $env:PORT = [string]$selectedAppPort
    $BaseUrl = "http://127.0.0.1:$selectedAppPort"
    $portReadback = [ordered]@{
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        preferred_port = $PreferredAppPort
        selected_port = $selectedAppPort
        fallback_port_used = ($selectedAppPort -ne $PreferredAppPort)
        auto_kill_attempted = $false
        foreign_process_touched = $false
    }
    $portReadback | ConvertTo-Json -Depth 8 | Set-Content -Path $PortProof -Encoding UTF8
    Write-Host "Local app port selected: $selectedAppPort (no existing process terminated)"

    Remove-Item $ServerStdout -ErrorAction SilentlyContinue
    Remove-Item $ServerStderr -ErrorAction SilentlyContinue
    $appProc = Start-Process -FilePath "python" -ArgumentList "app.py" -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $ServerStdout -RedirectStandardError $ServerStderr

    $health = $null
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 2
            if ($health.status -eq "ok") { break }
        } catch {}
    }
    if (-not $health -or $health.status -ne "ok") {
        throw "Local app did not become healthy. See $ServerStdout and $ServerStderr"
    }
    if (-not $health.ollama_configured) {
        throw "App health did not inherit grounded Ollama configuration."
    }
    $health | ConvertTo-Json -Depth 8 | Set-Content -Path $HealthProof -Encoding UTF8

    $q = [uri]::EscapeDataString($Query)
    $a = [uri]::EscapeDataString($ProposedAction)
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/assess?q=$q&action=$a&max=5" -Method Get -TimeoutSec 180
    if ($response.serpapi_integration -ne "live") {
        throw "Expected serpapi_integration=live, got '$($response.serpapi_integration)'"
    }
    if ([int]$response.result_count -lt 1) {
        throw "Live app returned no usable evidence results."
    }
    if ($response.answer_mode -ne "ollama_grounded") {
        throw "Expected answer_mode=ollama_grounded after proven Ollama chat preflight, got '$($response.answer_mode)'. ai_error='$($response.ai_error)'"
    }
    if (@($response.flags) -contains "LOCAL_AI_SYNTHESIS_FAILED") {
        throw "Unexpected LOCAL_AI_SYNTHESIS_FAILED after proven Ollama chat preflight."
    }
    if ($response.gate_state -ne "READY_FOR_HUMAN") {
        throw "Expected gate_state=READY_FOR_HUMAN, got '$($response.gate_state)' with flags '$(@($response.flags) -join ',')'"
    }
    if (-not $response.packet_id) {
        throw "Expected non-empty packet_id for Human Gate binding."
    }

    $proof = [ordered]@{
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        proof_kind = "LIVE_DECISION_GATE_READY_FOR_HUMAN"
        query = $Query
        proposed_action = $ProposedAction
        ollama_preflight = $ollamaReadback
        health = $health
        live_response = $response
        secret_material_in_proof = $false
    }
    $proof | ConvertTo-Json -Depth 24 | Set-Content -Path $E2EProof -Encoding UTF8

    Write-Host ""
    Write-Host "LIVE DECISION GATE READY_FOR_HUMAN PASS"
    Write-Host "Proof: $E2EProof"
    Write-Host "Opening browser for the local demo."
    Start-Process $BaseUrl
    Write-Host ""
    Write-Host "Verify Gate: READY_FOR_HUMAN, Mode: ollama_grounded, SerpApi: live. Then choose Approve/Hold/Reject in the visible Human Gate. Do not show the API key."
    [void](Read-Host "Press ENTER after local verification/recording to stop the app and any Ollama server started by this runner")
}
finally {
    if ($appProc -and -not $appProc.HasExited) {
        Stop-Process -Id $appProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($ownedOllamaProc -and -not $ownedOllamaProc.HasExited) {
        Stop-Process -Id $ownedOllamaProc.Id -Force -ErrorAction SilentlyContinue
    }
    Restore-EnvValue "SERPAPI_API_KEY" $oldKey
    Restore-EnvValue "OLLAMA_URL" $oldOllamaUrl
    Restore-EnvValue "OLLAMA_MODEL" $oldOllamaModel
    Restore-EnvValue "OLLAMA_HOST" $oldOllamaHost
    Restore-EnvValue "OLLAMA_MODELS" $oldOllamaModels
    Restore-EnvValue "CUDA_VISIBLE_DEVICES" $oldCudaVisible
    Restore-EnvValue "OLLAMA_VULKAN" $oldOllamaVulkan
    Restore-EnvValue "GGML_VK_VISIBLE_DEVICES" $oldVkVisible
    Restore-EnvValue "PORT" $oldPort
    Pop-Location
}
