<#
.SYNOPSIS
    Creates (or reuses) a Business Central cloud sandbox in a specific client's Microsoft Entra tenant,
    authenticating with your own account instead of a native client account.

.DESCRIPTION
    Wraps the same CreateDevEnv logic as .AL-Go\cloudDevEnv.ps1, but:
    - Forces authentication (device login) against the Microsoft Entra tenant given in -clientTenantId,
      instead of "Common". Your own account must have been granted access to that tenant (Microsoft Entra B2B
      guest invite, or a CSP/GDAP delegated admin relationship) with a role allowing Business Central
      environment management (e.g. "Business Central Admin" / "Dynamics 365 Admin").
    - Caches the resulting refresh token locally, encrypted with DPAPI (tied to your Windows user + machine),
      in a file named after the tenant, so you only do the interactive login once per client.
    - After the environment is created, patches the generated ".vscode\launch.json" entry to add the
      "tenant" property (Microsoft Entra tenant ID or domain), which AL-Go/BcContainerHelper does not set
      automatically for cloud sandboxes. Without it, VS Code cannot reliably tell which tenant's environment
      "Cloud Sandbox (<name>)" refers to once you have access to more than one tenant.

.PARAMETER clientTenantId
    Mandatory. The client's Microsoft Entra tenant ID (GUID) or domain (e.g. "contoso.onmicrosoft.com").

.PARAMETER environmentName
    Name of the cloud sandbox environment to create or reuse. Prompted for if not specified.

.PARAMETER reuseExistingEnvironment
    $true to reuse an existing environment with the same name, $false to recreate it. Prompted for if not specified.

.PARAMETER fromVSCode
    Pauses at the end waiting for ENTER, for use as a VS Code task.

.PARAMETER clean
    Creates a clean environment without compiling/publishing apps.

.PARAMETER customSettings
    JSON string overriding repository settings for this run.

.EXAMPLE
    .\.AL-Go\cloudDevEnvForClientTenant.ps1 -clientTenantId "15806119-3504-4617-a150-ddb832593ec6" -environmentName "contoso-dev"
#>

Param(
    [Parameter(Mandatory = $true)]
    [string] $clientTenantId,
    [string] $environmentName = "",
    [bool] $reuseExistingEnvironment,
    [switch] $fromVSCode,
    [switch] $clean,
    [string] $customSettings = ""
)

$errorActionPreference = "Stop"; $ProgressPreference = "SilentlyContinue"; Set-StrictMode -Version 2.0

function DownloadHelperFile {
    param(
        [string] $url,
        [string] $folder,
        [switch] $notifyAuthenticatedAttempt
    )

    $prevProgressPreference = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    $name = [System.IO.Path]::GetFileName($url)
    Write-Host "Downloading $name from $url"
    $path = Join-Path $folder $name
    try {
        Invoke-WebRequest -UseBasicParsing -uri $url -OutFile $path
    }
    catch {
        if ($notifyAuthenticatedAttempt) {
            Write-Host -ForegroundColor Red "Failed to download $name, trying authenticated download"
        }
        Invoke-WebRequest -UseBasicParsing -uri $url -OutFile $path -Headers @{ "Authorization" = "token $(gh auth token)" }
    }
    $ProgressPreference = $prevProgressPreference
    return $path
}

function Set-LaunchJsonTenant {
    param(
        [string] $launchJsonFile,
        [string] $configurationName,
        [string] $tenantId
    )

    try {
        if (-not (Test-Path $launchJsonFile)) {
            Write-Host -ForegroundColor Yellow "launch.json not found at $launchJsonFile, skipping tenant patch"
            return
        }

        $launchJson = Get-Content $launchJsonFile -Raw | ConvertFrom-Json
        $configurations = @($launchJson.configurations)
        $config = $configurations | Where-Object { $_.name -eq $configurationName }
        if (-not $config) {
            $existingNames = ($configurations | ForEach-Object { $_.name }) -join ", "
            Write-Host -ForegroundColor Yellow "Configuration '$configurationName' not found in $launchJsonFile (found: $existingNames), skipping tenant patch"
            return
        }

        if ($config.PSObject.Properties.Name -contains "tenant") {
            $config.tenant = $tenantId
        }
        else {
            $config | Add-Member -NotePropertyName "tenant" -NotePropertyValue $tenantId
        }
        $launchJson.configurations = $configurations

        $launchJson | ConvertTo-Json -Depth 10 | Set-Content -Path $launchJsonFile -Encoding utf8
        Write-Host -ForegroundColor Green "Updated '$configurationName' in $launchJsonFile with tenant = $tenantId"
    }
    catch {
        Write-Host -ForegroundColor Red "Failed to patch $launchJsonFile with tenant: $($_.Exception.Message)"
    }
}

try {
Clear-Host
Write-Host

$tmpFolder = Join-Path ([System.IO.Path]::GetTempPath()) "$([Guid]::NewGuid().ToString())"
New-Item -Path $tmpFolder -ItemType Directory -Force | Out-Null
$GitHubHelperPath = DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/Github-Helper.psm1' -folder $tmpFolder -notifyAuthenticatedAttempt
$ReadSettingsModule = DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/.Modules/ReadSettings.psm1' -folder $tmpFolder
$debugLoggingModule = DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/.Modules/DebugLogHelper.psm1' -folder $tmpFolder
$ALGoHelperPath = DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/AL-Go-Helper.ps1' -folder $tmpFolder
DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/.Modules/settings.schema.json' -folder $tmpFolder | Out-Null
DownloadHelperFile -url 'https://raw.githubusercontent.com/microsoft/AL-Go-Actions/v9.2/Environment.Packages.proj' -folder $tmpFolder | Out-Null

Import-Module $GitHubHelperPath
Import-Module $ReadSettingsModule
Import-Module $debugLoggingModule
. $ALGoHelperPath -local

$baseFolder = GetBaseFolder -folder $PSScriptRoot
$project = GetProject -baseFolder $baseFolder -projectALGoFolder $PSScriptRoot

Write-Host @"

This script will create a cloud based development environment (Business Central SaaS Sandbox)
in the Microsoft Entra tenant $clientTenantId, using your own account.
Your account must already have been granted access to that tenant (B2B guest invite or CSP/GDAP
delegated admin) with a role allowing Business Central environment management.

"@

if (-not $environmentName) {
    $environmentName = Enter-Value `
        -title "Environment name" `
        -question "Please enter the name of the environment to create" `
        -default "$($env:USERNAME)-sandbox" `
        -trimCharacters @('"',"'",' ')
}

if ($PSBoundParameters.Keys -notcontains 'reuseExistingEnvironment') {
    $reuseExistingEnvironment = (Select-Value `
        -title "What if the environment already exists?" `
        -options @{ "Yes" = "Reuse existing environment"; "No" = "Recreate environment" } `
        -question "Select behavior" `
        -default "No") -eq "Yes"
}

DownloadAndImportBcContainerHelper -baseFolder $baseFolder

$secretFolder = Join-Path $env:LOCALAPPDATA "AL-Go-Secrets"
New-Item -ItemType Directory -Force -Path $secretFolder | Out-Null
$secretFile = Join-Path $secretFolder "$clientTenantId.xml"

if (Test-Path $secretFile) {
    $secureRefreshToken = Import-Clixml $secretFile
    $refreshToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($secureRefreshToken))
    $bcAuthContext = New-BcAuthContext -tenantID $clientTenantId -refreshToken $refreshToken
}
else {
    Write-Host "No cached credentials for tenant $clientTenantId, starting interactive device login..."
    $bcAuthContext = New-BcAuthContext -tenantID $clientTenantId -includeDeviceLogin
    (ConvertTo-SecureString $bcAuthContext.RefreshToken -AsPlainText -Force) | Export-Clixml $secretFile
}

CreateDevEnv `
    -kind cloud `
    -caller local `
    -bcAuthContext $bcAuthContext `
    -environmentName $environmentName `
    -reuseExistingEnvironment:$reuseExistingEnvironment `
    -baseFolder $baseFolder `
    -project $project `
    -clean:$clean `
    -customSettings $customSettings
}
catch {
    Write-Host -ForegroundColor Red "Error: $($_.Exception.Message)`nStacktrace: $($_.scriptStackTrace)"
}
finally {
    # Runs even if CreateDevEnv threw after already creating the launch.json entry (e.g. a later
    # compile/publish failure), so the tenant is patched in as long as the entry exists at all.
    # AL-Go updates the launch.json of each individual app folder (e.g. "AllGoSample"), which is
    # not necessarily the same as the AL-Go "project" folder (it can be "." at the repo root even
    # when apps live in subfolders) - so every launch.json in the repo is checked, and the patch is
    # a no-op wherever the matching configuration name isn't found.
    if ($environmentName -and $baseFolder) {
        Get-ChildItem -Path $baseFolder -Recurse -Force -Filter "launch.json" |
            Where-Object { $_.Directory.Name -eq ".vscode" } |
            ForEach-Object {
                Set-LaunchJsonTenant `
                    -launchJsonFile $_.FullName `
                    -configurationName "Cloud Sandbox ($environmentName)" `
                    -tenantId $clientTenantId
            }
    }
    if ($fromVSCode) {
        Read-Host "Press ENTER to close this window"
    }
}
