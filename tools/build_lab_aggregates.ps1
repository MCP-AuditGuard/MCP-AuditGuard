$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

$Datasets = @(
    [ordered]@{
        root = "vulnerable-lab\expanded-112"
        dataset = "expanded-112"
        default_expected = "malicious"
        default_should_detect_mode = "mcp03_only"
    },
    [ordered]@{
        root = "vulnerable-lab\benign-lab\mcp03-benign-100"
        dataset = "mcp03-benign-100"
        default_expected = "benign"
        default_should_detect_mode = "none"
    },
    [ordered]@{
        root = "vulnerable-lab\benign-lab\general-benign-100"
        dataset = "general-benign-100"
        default_expected = "benign"
        default_should_detect_mode = "none"
    }
)

function Get-RelativePath {
    param(
        [string]$Root,
        [string]$Path
    )

    return (($Path.Substring($Root.Length + 1)) -replace "\\", "/")
}

function Get-MetaValue {
    param(
        [object]$Meta,
        [string]$Name,
        [object]$Default = $null
    )

    if ($null -eq $Meta) {
        return $Default
    }

    if ($Meta.PSObject.Properties.Name -contains $Name) {
        return $Meta.$Name
    }

    return $Default
}

function Get-ExpectedLabel {
    param(
        [string]$DefaultExpected,
        [string]$ScenarioPath,
        [object]$Meta
    )

    $text = "$ScenarioPath $(Get-MetaValue $Meta 'category' '') $(Get-MetaValue $Meta 'expected_result' '') $(Get-MetaValue $Meta 'expected_signal' '')"

    if ($text -match "(?i)benign|false-positive control|no finding") {
        return "benign"
    }

    return $DefaultExpected
}

function Get-ShouldDetect {
    param(
        [string]$Mode,
        [string]$Expected,
        [object]$Meta
    )

    if ($Expected -eq "benign") {
        return $false
    }

    if ($Mode -eq "none") {
        return $false
    }

    if ($Mode -eq "all_malicious") {
        return $true
    }

    if ($Mode -eq "mcp03_only") {
        $category = [string](Get-MetaValue $Meta "category" "")
        return $category -match "MCP03"
    }

    return $false
}

function Build-Aggregate {
    param([hashtable]$Dataset)

    $datasetRoot = Join-Path $ProjectRoot $Dataset.root
    if (-not (Test-Path -LiteralPath $datasetRoot)) {
        throw "Dataset not found: $datasetRoot"
    }

    $allToolsPath = Join-Path $datasetRoot "all-tools.json"
    $expectedLabelsPath = Join-Path $datasetRoot "expected-labels.json"

    $toolsJsonFiles = Get-ChildItem -LiteralPath $datasetRoot -Recurse -Filter "tools.json" |
        Where-Object {
            $_.FullName -notlike "*\all-tools.json" -and
            $_.FullName -notlike "*\expected-labels.json"
        } |
        Sort-Object FullName

    $tools = New-Object System.Collections.Generic.List[object]
    $labels = New-Object System.Collections.Generic.List[object]

    foreach ($toolsJson in $toolsJsonFiles) {
        $caseDir = Split-Path -Parent $toolsJson.FullName
        $sourcePath = Get-RelativePath -Root $datasetRoot -Path $caseDir
        $toolsDoc = Get-Content -LiteralPath $toolsJson.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

        foreach ($tool in $toolsDoc.tools) {
            if ($null -eq $tool._meta) {
                $tool | Add-Member -NotePropertyName "_meta" -NotePropertyValue ([pscustomobject]@{})
            }

            $meta = $tool._meta
            $scenarioId = Get-MetaValue $meta "scenario_id" (Get-MetaValue $meta "benign_id" $tool.name)
            $expected = Get-ExpectedLabel -DefaultExpected $Dataset.default_expected -ScenarioPath $sourcePath -Meta $meta
            $shouldDetect = Get-ShouldDetect -Mode $Dataset.default_should_detect_mode -Expected $expected -Meta $meta

            $meta | Add-Member -NotePropertyName "aggregate_source" -NotePropertyValue $sourcePath -Force
            $tools.Add($tool)

            $labels.Add([ordered]@{
                scenario_id = $scenarioId
                tool_name = $tool.name
                expected = $expected
                should_auditguard_detect = $shouldDetect
                category = Get-MetaValue $meta "category" ""
                difficulty = Get-MetaValue $meta "difficulty" ""
                expected_signal = Get-MetaValue $meta "expected_signal" (Get-MetaValue $meta "expected_result" "")
                source_path = $sourcePath
            })
        }
    }

    $allTools = [ordered]@{
        server_name = "$($Dataset.dataset)-aggregate"
        dataset = $Dataset.dataset
        generated_from = "individual scenario tools.json files"
        tools = $tools
    }

    $expectedLabels = [ordered]@{
        dataset = $Dataset.dataset
        total_cases = $labels.Count
        malicious_cases = ($labels | Where-Object { $_.expected -ne "benign" }).Count
        benign_cases = ($labels | Where-Object { $_.expected -eq "benign" }).Count
        expected_auditguard_detect_cases = ($labels | Where-Object { $_.should_auditguard_detect }).Count
        labels = $labels
    }

    [System.IO.File]::WriteAllText(
        $allToolsPath,
        ($allTools | ConvertTo-Json -Depth 30),
        $Utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        $expectedLabelsPath,
        ($expectedLabels | ConvertTo-Json -Depth 20),
        $Utf8NoBom
    )

    [ordered]@{
        dataset = $Dataset.dataset
        all_tools = $allToolsPath
        expected_labels = $expectedLabelsPath
        tools = $tools.Count
        labels = $labels.Count
        malicious = $expectedLabels.malicious_cases
        benign = $expectedLabels.benign_cases
        expected_auditguard_detect = $expectedLabels.expected_auditguard_detect_cases
    }
}

$results = foreach ($dataset in $Datasets) {
    Build-Aggregate -Dataset $dataset
}

$results | ConvertTo-Json -Depth 5
