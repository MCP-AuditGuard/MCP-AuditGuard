$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DatasetRoot = Join-Path $ProjectRoot "vulnerable-lab\snyk-aligned-mcp03-100"
$AllToolsPath = Join-Path $DatasetRoot "all-tools.json"
$ExpectedLabelsPath = Join-Path $DatasetRoot "expected-labels.json"

if (-not (Test-Path -LiteralPath $DatasetRoot)) {
    throw "Dataset not found: $DatasetRoot"
}

$caseDirs = Get-ChildItem -LiteralPath $DatasetRoot -Directory |
    Sort-Object Name |
    ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Directory | Sort-Object Name
    }

$tools = New-Object System.Collections.Generic.List[object]
$labels = New-Object System.Collections.Generic.List[object]

foreach ($caseDir in $caseDirs) {
    $toolsPath = Join-Path $caseDir.FullName "tools.json"
    $labelPath = Join-Path $caseDir.FullName "label.json"

    if (-not (Test-Path -LiteralPath $toolsPath)) {
        throw "Missing tools.json: $toolsPath"
    }
    if (-not (Test-Path -LiteralPath $labelPath)) {
        throw "Missing label.json: $labelPath"
    }

    $toolsDoc = Get-Content -LiteralPath $toolsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $label = Get-Content -LiteralPath $labelPath -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($tool in $toolsDoc.tools) {
        if ($null -eq $tool._meta) {
            $tool | Add-Member -NotePropertyName "_meta" -NotePropertyValue ([pscustomobject]@{})
        }

        $tool._meta | Add-Member -NotePropertyName "aggregate_source" -NotePropertyValue ($caseDir.FullName.Substring($DatasetRoot.Length + 1) -replace "\\", "/") -Force
        $tools.Add($tool)
    }

    $labels.Add([ordered]@{
        scenario_id = $label.scenario_id
        tool_name = $toolsDoc.tools[0].name
        expected = $label.expected
        should_auditguard_detect = $label.should_auditguard_detect
        mcp_category = $label.mcp_category
        snyk_issue_code = $label.snyk_issue_code
        snyk_issue_title = $label.snyk_issue_title
        attack_surface = $label.attack_surface
        difficulty = $label.difficulty
        source_path = ($caseDir.FullName.Substring($DatasetRoot.Length + 1) -replace "\\", "/")
    })
}

$allTools = [ordered]@{
    server_name = "snyk-aligned-mcp03-100-aggregate"
    dataset = "snyk-aligned-mcp03-100"
    generated_from = "individual scenario tools.json files"
    tools = $tools
}

$expectedLabels = [ordered]@{
    dataset = "snyk-aligned-mcp03-100"
    total_cases = $labels.Count
    malicious_cases = ($labels | Where-Object { $_.expected -ne "benign" }).Count
    benign_cases = ($labels | Where-Object { $_.expected -eq "benign" }).Count
    labels = $labels
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText(
    $AllToolsPath,
    ($allTools | ConvertTo-Json -Depth 30),
    $utf8NoBom
)
[System.IO.File]::WriteAllText(
    $ExpectedLabelsPath,
    ($expectedLabels | ConvertTo-Json -Depth 20),
    $utf8NoBom
)

Write-Output "Wrote $AllToolsPath"
Write-Output "Wrote $ExpectedLabelsPath"
Write-Output "Tools: $($tools.Count)"
Write-Output "Labels: $($labels.Count)"
