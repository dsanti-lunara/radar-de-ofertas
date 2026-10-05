param()

$ErrorActionPreference = 'Stop'
$publicationRoot = $PSScriptRoot
$manifestPath = Join-Path $publicationRoot 'publication-plan.json'
$publicationEncoding = New-Object System.Text.UTF8Encoding($false)

function Invoke-GitHubCommand {
    param([string[]]$GhArgs)
    $commandOutput = @(& gh @GhArgs 2>&1)
    $commandExitCode = $LASTEXITCODE
    $commandText = ($commandOutput | ForEach-Object { $_.ToString() }) -join "`n"
    if ($commandExitCode -ne 0) { throw "gh falhou ($commandExitCode): $commandText" }
    return $commandText
}

function Save-PublicationManifest {
    $manifestJson = $publicationPlan | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($manifestPath, $manifestJson + "`n", $publicationEncoding)
    $indexLines = @('# Issues publicadas do Radar V1', '', 'Publicação retomável; registro somente de URLs confirmadas pelo GitHub.', '')
    foreach ($publishedTicket in $publicationPlan.published) {
        $indexLines += "- [$($publishedTicket.id)]($($publishedTicket.url)) — $($publishedTicket.title)"
    }
    [System.IO.File]::WriteAllText((Join-Path $publicationRoot 'PUBLISHED.md'), ($indexLines -join "`n") + "`n", $publicationEncoding)
}

$publicationPlan = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($publicationPlan.approval.status -ne 'approved') { throw 'Breakdown ainda não aprovado no manifesto.' }
$repositoryName = $publicationPlan.repository
if ($repositoryName -ne 'dsanti-lunara/radar-de-ofertas') { throw 'Repositório fora do escopo aprovado.' }
if ($publicationPlan.tickets.Count -ne 67) { throw 'Plano diverge dos 67 tickets aprovados.' }
$knownTicketIds = @($publicationPlan.tickets | ForEach-Object { $_.id })

# Validar todo o pacote antes da primeira escrita remota.
foreach ($plannedTicket in $publicationPlan.tickets) {
    $plannedBodyPath = [System.IO.Path]::GetFullPath((Join-Path $publicationRoot $plannedTicket.bodyFile))
    $allowedIssuesRoot = [System.IO.Path]::GetFullPath((Join-Path $publicationRoot 'issues')) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $plannedBodyPath.StartsWith($allowedIssuesRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Body fora do pacote: $($plannedTicket.id)" }
    if (-not (Test-Path -LiteralPath $plannedBodyPath -PathType Leaf)) { throw "Body ausente: $($plannedTicket.id)" }
    foreach ($blockingId in $plannedTicket.blockedBy) {
        if ($blockingId -notin $knownTicketIds -or [int]$blockingId.Substring(4) -ge [int]$plannedTicket.id.Substring(4)) { throw "Aresta inválida: $($plannedTicket.id) -> $blockingId" }
    }
    foreach ($route in $plannedTicket.alternativeRoutes) {
        foreach ($routeId in $route) {
            if ($routeId -notin $knownTicketIds -or [int]$routeId.Substring(4) -ge [int]$plannedTicket.id.Substring(4)) { throw "Rota alternativa inválida: $($plannedTicket.id) -> $routeId" }
        }
    }
}

$remoteRepo = Invoke-GitHubCommand -GhArgs @('api', "repos/$repositoryName") | ConvertFrom-Json
if (-not $remoteRepo.permissions.push -and -not $remoteRepo.permissions.admin) { throw 'Conta atual sem permissão de escrita confirmada no repositório.' }
$existingIssues = @(Invoke-GitHubCommand -GhArgs @('issue', 'list', '--repo', $repositoryName, '--state', 'all', '--limit', '1000', '--json', 'number,title,url,state,labels') | ConvertFrom-Json)
if ($existingIssues.Count -ge 1000) { throw 'Inventário truncado: resolver paginação antes de publicar para evitar duplicação.' }
$existingLabels = @(Invoke-GitHubCommand -GhArgs @('label', 'list', '--repo', $repositoryName, '--limit', '1000', '--json', 'name') | ConvertFrom-Json)
if ($publicationPlan.label -notin @($existingLabels | ForEach-Object { $_.name })) {
    Invoke-GitHubCommand -GhArgs @('label', 'create', $publicationPlan.label, '--repo', $repositoryName, '--color', '0E8A16', '--description', 'Escopo especificado; executar somente com blockers e gates satisfeitos.') | Out-Null
}

$publicationPlan.status = 'publishing'
$publicationPlan.blockedReason = $null
Save-PublicationManifest

try {
    foreach ($plannedTicket in $publicationPlan.tickets) {
        $alreadyRecorded = @($publicationPlan.published | Where-Object { $_.id -eq $plannedTicket.id })
        $remoteMatches = @($existingIssues | Where-Object { $_.title.StartsWith("[$($plannedTicket.id)] ") })
        if ($remoteMatches.Count -gt 1 -or $alreadyRecorded.Count -gt 1) { throw "Identificador duplicado: $($plannedTicket.id)" }
        if ($remoteMatches.Count -eq 1 -and $remoteMatches[0].state -ne 'OPEN') { throw "Issue existente fechada: $($plannedTicket.id). Não reabrir automaticamente." }

        $renderedBody = Get-Content -LiteralPath (Join-Path $publicationRoot $plannedTicket.bodyFile) -Raw -Encoding UTF8
        foreach ($reference in @($publicationPlan.published | Where-Object { [int]$_.id.Substring(4) -lt [int]$plannedTicket.id.Substring(4) })) {
            $referencePattern = '\b' + [regex]::Escape($reference.id) + '\b'
            $renderedBody = [regex]::Replace($renderedBody, $referencePattern, "[$($reference.id)]($($reference.url))")
        }
        foreach ($blockingId in $plannedTicket.blockedBy) {
            if ($blockingId -notin @($publicationPlan.published | ForEach-Object { $_.id })) { throw "Bloqueador sem URL real: $blockingId" }
        }
        $renderedBodyPath = Join-Path $publicationRoot "publish-$($plannedTicket.id).md"
        [System.IO.File]::WriteAllText($renderedBodyPath, $renderedBody, $publicationEncoding)

        if ($alreadyRecorded.Count -eq 1) {
            $issueNumber = $alreadyRecorded[0].number
            $issueUrl = $alreadyRecorded[0].url
        } elseif ($remoteMatches.Count -eq 1) {
            $issueNumber = $remoteMatches[0].number
            $issueUrl = $remoteMatches[0].url
        } else {
            $issueUrl = (Invoke-GitHubCommand -GhArgs @('issue', 'create', '--repo', $repositoryName, '--title', "[$($plannedTicket.id)] $($plannedTicket.title)", '--body-file', $renderedBodyPath, '--label', $publicationPlan.label)).Trim()
            if ($issueUrl -notmatch '^https://github\.com/dsanti-lunara/radar-de-ofertas/issues/(\d+)$') { throw "Retorno inesperado ao criar $($plannedTicket.id); consultar tracker antes de tentar novamente." }
            $issueNumber = [int]$Matches[1]
        }

        if ($alreadyRecorded.Count -eq 0) {
            $publicationPlan.published = @($publicationPlan.published) + [pscustomobject]@{
                id = $plannedTicket.id; title = $plannedTicket.title; number = $issueNumber; url = $issueUrl
                databaseId = $null; verified = $false; nativeBlocking = 'pending'
            }
            Save-PublicationManifest
        }
        $publishedRecord = $publicationPlan.published | Where-Object { $_.id -eq $plannedTicket.id }
        $remoteIssue = Invoke-GitHubCommand -GhArgs @('api', "repos/$repositoryName/issues/$issueNumber") | ConvertFrom-Json
        if ($remoteIssue.title -ne "[$($plannedTicket.id)] $($plannedTicket.title)") { throw "Título divergente: $($plannedTicket.id). Preservar edição externa e revisar." }
        if (($remoteIssue.body -replace "`r`n", "`n").Trim() -ne ($renderedBody -replace "`r`n", "`n").Trim()) { throw "Body divergente: $($plannedTicket.id). Não sobrescrever automaticamente." }
        if ($publicationPlan.label -notin @($remoteIssue.labels | ForEach-Object { $_.name })) { throw "Label ausente: $($plannedTicket.id). Revisar antes de retomar." }
        $publishedRecord.databaseId = $remoteIssue.id
        $publishedRecord.verified = $true
        Save-PublicationManifest

        # Usar blocking nativo quando o endpoint estiver disponível; a alternativa OR fica no body.
        if ($plannedTicket.blockedBy.Count -gt 0) {
            $dependencyEndpoint = "repos/$repositoryName/issues/$issueNumber/dependencies/blocked_by"
            try {
                $remoteDependencies = @(Invoke-GitHubCommand -GhArgs @('api', $dependencyEndpoint) | ConvertFrom-Json)
                foreach ($blockingId in $plannedTicket.blockedBy) {
                    $blockingRecord = $publicationPlan.published | Where-Object { $_.id -eq $blockingId }
                    if (-not $blockingRecord.databaseId) { throw "ID remoto ausente para $blockingId" }
                    if ($blockingRecord.databaseId -notin @($remoteDependencies | ForEach-Object { $_.id })) {
                        Invoke-GitHubCommand -GhArgs @('api', '--method', 'POST', $dependencyEndpoint, '-F', "issue_id=$($blockingRecord.databaseId)") | Out-Null
                    }
                }
                $publishedRecord.nativeBlocking = 'applied'
            } catch {
                if ($_.Exception.Message -match 'HTTP (404|410)') {
                    $publishedRecord.nativeBlocking = 'endpoint-unavailable; real links preserved in body'
                    Write-Warning "Blocking nativo indisponível para $($plannedTicket.id); referências reais preservadas no body."
                } else { throw }
            }
        } else { $publishedRecord.nativeBlocking = 'no-unconditional-blockers' }
        Save-PublicationManifest
        Write-Host "$($plannedTicket.id): $issueUrl"
    }
    $publicationPlan.status = 'published'
    Save-PublicationManifest
    Write-Host '67 issues publicadas e verificadas. Nenhuma implementação foi iniciada.'
} catch {
    $publicationPlan.status = 'publication-interrupted'
    $publicationPlan.blockedReason = $_.Exception.Message
    Save-PublicationManifest
    throw
}
