[CmdletBinding()]
param(
    [switch]$RecreateVenv,
    [switch]$ForceModelDownload,
    [switch]$SkipTests,
    [switch]$FullTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ApplicationName = "MCP-AuditGuard"
$ModelRepository = "BAAI/bge-small-en-v1.5"

$InstallerDirectory = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InstallerDirectory
$VenvDirectory = Join-Path $ProjectRoot ".venv-build"
$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
$HfExecutable = Join-Path $VenvDirectory "Scripts\hf.exe"

$ModelDirectory = Join-Path `
    $ProjectRoot `
    "models\embedding\bge-small-en-v1.5"

$WindowsSpec = Join-Path `
    $InstallerDirectory `
    "auditguard_windows.spec"

$BuildDirectory = Join-Path $ProjectRoot "build"
$DistDirectory = Join-Path $ProjectRoot "dist"

$AuditGuardExecutable = Join-Path `
    $DistDirectory `
    "AuditGuard\AuditGuard.exe"

$InternalDirectory = Join-Path `
    $DistDirectory `
    "AuditGuard\_internal"


function Write-Step {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    Write-Host
    Write-Host "===================================================================="
    Write-Host $Message
    Write-Host "===================================================================="
}


function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments

    if ($LASTEXITCODE -ne 0) {
        $RenderedArguments = $Arguments -join " "

        throw (
            "명령 실행에 실패했습니다.`n" +
            "명령: $FilePath $RenderedArguments`n" +
            "종료 코드: $LASTEXITCODE"
        )
    }
}


function Test-PythonVersion {
    param(
        [Parameter(Mandatory)]
        [string]$Executable,

        [string[]]$PrefixArguments = @()
    )

    $Arguments = @(
        $PrefixArguments
        "-c"
        "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    )

    & $Executable @Arguments *> $null

    return $LASTEXITCODE -eq 0
}


function Resolve-BasePython {
    if ($env:AUDITGUARD_PYTHON) {
        $ConfiguredPython = Get-Command `
            $env:AUDITGUARD_PYTHON `
            -ErrorAction SilentlyContinue

        if ($null -eq $ConfiguredPython) {
            throw (
                "AUDITGUARD_PYTHON으로 지정한 Python을 찾을 수 없습니다: " +
                $env:AUDITGUARD_PYTHON
            )
        }

        if (-not (
            Test-PythonVersion `
                -Executable $ConfiguredPython.Source
        )) {
            throw "Python 3.11 이상이 필요합니다."
        }

        return [pscustomobject]@{
            Executable = $ConfiguredPython.Source
            PrefixArguments = [string[]]@()
        }
    }

    $PythonLauncher = Get-Command `
        "py" `
        -ErrorAction SilentlyContinue

    if ($null -ne $PythonLauncher) {
        foreach ($VersionArgument in @("-3.14", "-3")) {
            if (
                Test-PythonVersion `
                    -Executable $PythonLauncher.Source `
                    -PrefixArguments @($VersionArgument)
            ) {
                return [pscustomobject]@{
                    Executable = $PythonLauncher.Source
                    PrefixArguments = [string[]]@(
                        $VersionArgument
                    )
                }
            }
        }
    }

    $PythonCommand = Get-Command `
        "python" `
        -ErrorAction SilentlyContinue

    if (
        $null -ne $PythonCommand `
        -and (
            Test-PythonVersion `
                -Executable $PythonCommand.Source
        )
    ) {
        return [pscustomobject]@{
            Executable = $PythonCommand.Source
            PrefixArguments = [string[]]@()
        }
    }

    throw (
        "Python 3.11 이상을 찾지 못했습니다.`n" +
        "Python을 설치하거나 AUDITGUARD_PYTHON 환경변수에 " +
        "Python 실행파일 경로를 지정하세요."
    )
}


function Test-EmbeddingModel {
    $ConfigPath = Join-Path `
        $ModelDirectory `
        "config.json"

    $SafeTensorPath = Join-Path `
        $ModelDirectory `
        "model.safetensors"

    $PyTorchWeightPath = Join-Path `
        $ModelDirectory `
        "pytorch_model.bin"

    return (
        (Test-Path $ConfigPath -PathType Leaf) `
        -and (
            (Test-Path $SafeTensorPath -PathType Leaf) `
            -or (
                Test-Path `
                    $PyTorchWeightPath `
                    -PathType Leaf
            )
        )
    )
}


$OriginalLocation = Get-Location

try {
    Set-Location $ProjectRoot

    Write-Host "===================================================================="
    Write-Host $ApplicationName
    Write-Host "Windows Build"
    Write-Host "===================================================================="
    Write-Host "프로젝트: $ProjectRoot"

    $IsWindowsPlatform = (
        [System.Environment]::OSVersion.Platform `
        -eq [System.PlatformID]::Win32NT
    )

    if (-not $IsWindowsPlatform) {
        throw (
            "build_windows.ps1은 Windows에서만 실행할 수 있습니다."
        )
    }

    if (-not (
        Test-Path `
            $WindowsSpec `
            -PathType Leaf
    )) {
        throw (
            "Windows spec 파일을 찾을 수 없습니다: " +
            $WindowsSpec
        )
    }

    Write-Step "1/8 Python과 빌드 가상환경을 준비합니다."

    if (
        $RecreateVenv `
        -and (
            Test-Path $VenvDirectory
        )
    ) {
        Write-Host (
            "기존 빌드 가상환경을 삭제합니다: " +
            $VenvDirectory
        )

        Remove-Item `
            $VenvDirectory `
            -Recurse `
            -Force
    }

    if (-not (
        Test-Path `
            $VenvPython `
            -PathType Leaf
    )) {
        $BasePython = Resolve-BasePython

        $VersionArguments = @(
            $BasePython.PrefixArguments
            "-c"
            "import sys; print(sys.version.split()[0])"
        )

        $BasePythonVersion = & `
            $BasePython.Executable `
            @VersionArguments

        if ($LASTEXITCODE -ne 0) {
            throw "기본 Python 버전을 확인하지 못했습니다."
        }

        Write-Host (
            "사용할 Python: " +
            $BasePython.Executable +
            " " +
            ($BasePython.PrefixArguments -join " ")
        )
        Write-Host "Python 버전: $BasePythonVersion"
        Write-Host "빌드 가상환경을 생성합니다: $VenvDirectory"

        $CreateVenvArguments = @(
            $BasePython.PrefixArguments
            "-m"
            "venv"
            $VenvDirectory
        )

        Invoke-CheckedCommand `
            -FilePath $BasePython.Executable `
            -Arguments $CreateVenvArguments
    }
    else {
        Write-Host (
            "기존 빌드 가상환경을 사용합니다: " +
            $VenvDirectory
        )
    }

    $VenvPythonVersion = & `
        $VenvPython `
        -c `
        "import sys; print(sys.version.split()[0])"

    if ($LASTEXITCODE -ne 0) {
        throw "빌드 가상환경의 Python을 실행하지 못했습니다."
    }

    Write-Host "빌드 Python 버전: $VenvPythonVersion"

    Write-Step "2/8 pip와 프로젝트 빌드 의존성을 설치합니다."

    Invoke-CheckedCommand `
        -FilePath $VenvPython `
        -Arguments @(
            "-m"
            "pip"
            "install"
            "--upgrade"
            "pip"
            "setuptools"
            "wheel"
        )

    Invoke-CheckedCommand `
        -FilePath $VenvPython `
        -Arguments @(
            "-m"
            "pip"
            "install"
            ".[dev,semantic,build]"
        )

    Write-Step "3/8 Semantic 모델을 준비합니다."

    if (
        $ForceModelDownload `
        -or (-not (
            Test-EmbeddingModel
        ))
    ) {
        if (-not (
            Test-Path `
                $HfExecutable `
                -PathType Leaf
        )) {
            throw (
                "Hugging Face CLI를 찾을 수 없습니다: " +
                $HfExecutable
            )
        }

        New-Item `
            -ItemType Directory `
            -Path $ModelDirectory `
            -Force `
            | Out-Null

        $DownloadArguments = @(
            "download"
            $ModelRepository
            "--local-dir"
            $ModelDirectory
        )

        if ($env:AUDITGUARD_MODEL_REVISION) {
            $DownloadArguments += @(
                "--revision"
                $env:AUDITGUARD_MODEL_REVISION
            )

            Write-Host (
                "고정 revision: " +
                $env:AUDITGUARD_MODEL_REVISION
            )
        }
        else {
            Write-Host (
                "AUDITGUARD_MODEL_REVISION이 없으므로 " +
                "모델 저장소의 기본 revision을 사용합니다."
            )
        }

        Invoke-CheckedCommand `
            -FilePath $HfExecutable `
            -Arguments $DownloadArguments
    }
    else {
        Write-Host (
            "기존 Semantic 모델을 사용합니다: " +
            $ModelDirectory
        )
    }

    if (-not (
        Test-EmbeddingModel
    )) {
        throw (
            "Semantic 모델 다운로드 후 필수 파일을 찾지 못했습니다: " +
            $ModelDirectory
        )
    }

    Write-Step "4/8 Semantic Runtime Preflight를 실행합니다."

    $PreflightCode = @'
from core.runtime_preflight import run_runtime_preflight

result = run_runtime_preflight()

print(f"ready: {result.semantic_ready}")
print(f"provider: {result.provider_name}")
print(f"model: {result.model_path}")
print(f"dimension: {result.embedding_dimension}")
print(f"error: {result.error_code}")
print(f"message: {result.error_message}")

raise SystemExit(0 if result.semantic_ready else 1)
'@

    Invoke-CheckedCommand `
        -FilePath $VenvPython `
        -Arguments @(
            "-c"
            $PreflightCode
        )

    Write-Step "5/8 빌드 관련 테스트를 실행합니다."

    if ($SkipTests) {
        Write-Host "요청에 따라 테스트를 건너뜁니다."
    }
    elseif ($FullTests) {
        Invoke-CheckedCommand `
            -FilePath $VenvPython `
            -Arguments @(
                "-m"
                "pytest"
                "-q"
            )
    }
    else {
        Invoke-CheckedCommand `
            -FilePath $VenvPython `
            -Arguments @(
                "-m"
                "pytest"
                "-q"
                "tests/unit/test_runtime_preflight.py"
            )
    }

    Write-Step "6/8 이전 build와 dist를 정리합니다."

    Remove-Item `
        $BuildDirectory `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    Remove-Item `
        $DistDirectory `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    Write-Step "7/8 PyInstaller Windows onedir 빌드를 실행합니다."

    Invoke-CheckedCommand `
        -FilePath $VenvPython `
        -Arguments @(
            "-m"
            "PyInstaller"
            "--noconfirm"
            "--clean"
            $WindowsSpec
        )

    Write-Step "8/8 최종 Windows 빌드 결과를 확인합니다."

    $RequiredBuildPaths = @(
        $AuditGuardExecutable
        (Join-Path `
            $InternalDirectory `
            "web\templates\index.html")
        (Join-Path `
            $InternalDirectory `
            "web\static\app.js")
        (Join-Path `
            $InternalDirectory `
            "rules")
        (Join-Path `
            $InternalDirectory `
            "models\embedding\bge-small-en-v1.5\config.json")
    )

    foreach ($RequiredPath in $RequiredBuildPaths) {
        if (-not (
            Test-Path $RequiredPath
        )) {
            throw (
                "최종 빌드에서 필수 파일을 찾지 못했습니다: " +
                $RequiredPath
            )
        }

        Write-Host "[확인] $RequiredPath"
    }

    Write-Host
    Write-Host "===================================================================="
    Write-Host "Windows 빌드가 완료되었습니다."
    Write-Host "실행파일:"
    Write-Host $AuditGuardExecutable
    Write-Host "===================================================================="
}
catch {
    Write-Host
    Write-Host "===================================================================="
    Write-Host "[빌드 실패]"
    Write-Host "===================================================================="
    Write-Host $_.Exception.Message
    Write-Host

    exit 1
}
finally {
    Set-Location $OriginalLocation
}
