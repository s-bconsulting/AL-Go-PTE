<#
    Custom deployment script for AL-Go, invoked automatically by Deploy.ps1 for any environment
    whose EnvironmentType is "SaaS" (all cloud environments, sandbox and production alike).

    For sandbox environments, behaves like AL-Go's default logic (publish immediately via the dev endpoint).

    For production environments, publishes via the Business Central Admin Center API's PTE install
    endpoint, which supports scheduling the actual installation ("Immediate", "UpdateWindow",
    "NextMinorUpdate", "NextMajorUpdate") - unlike BcContainerHelper's Publish-PerTenantExtensionApps,
    which only talks to the older Automation API and doesn't support "UpdateWindow".

    The schedule to use is read from the "deploymentSchedule" property of the environment's
    DeployTo<environmentName> setting in .AL-Go/settings.json, e.g.:
      "DeployToProdEnv": { "deploymentSchedule": "UpdateWindow" }
    Defaults to "Immediate" if not set.
#>
Param(
    [hashtable] $parameters
)

function Invoke-PteInstallWithSchedule {
    Param(
        [hashtable] $bcAuthContext,
        [string] $environmentName,
        [string] $appFile,
        [string] $deploymentSchedule
    )

    $bcAuthContext = Renew-BcAuthContext -bcAuthContext $bcAuthContext
    $apiVersion = "v2.29"
    $uri = "https://api.businesscentral.dynamics.com/admin/$apiVersion/applications/BusinessCentral/environments/$environmentName/apps/pteInstall"

    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    $fileBytes = [System.IO.File]::ReadAllBytes($appFile)
    $fileName = [System.IO.Path]::GetFileName($appFile)

    $bodyBytes = New-Object System.Collections.Generic.List[byte]

    function Add-TextPart([string] $name, [string] $value) {
        $part = "--$boundary$LF" + "Content-Disposition: form-data; name=`"$name`"$LF$LF" + "$value$LF"
        $bodyBytes.AddRange([System.Text.Encoding]::UTF8.GetBytes($part))
    }

    Add-TextPart -name "deploymentSchedule" -value $deploymentSchedule
    Add-TextPart -name "acceptIsvEula" -value "true"
    Add-TextPart -name "installOrUpdateNeededDependencies" -value "true"

    $filePartHeader = "--$boundary$LF" + "Content-Disposition: form-data; name=`"extensionFile`"; filename=`"$fileName`"$LF" + "Content-Type: application/octet-stream$LF$LF"
    $bodyBytes.AddRange([System.Text.Encoding]::UTF8.GetBytes($filePartHeader))
    $bodyBytes.AddRange($fileBytes)
    $bodyBytes.AddRange([System.Text.Encoding]::UTF8.GetBytes($LF))
    $bodyBytes.AddRange([System.Text.Encoding]::UTF8.GetBytes("--$boundary--$LF"))

    $headers = @{ "Authorization" = "Bearer $($bcAuthContext.AccessToken)" }
    Write-Host "Installing $fileName on $environmentName with deploymentSchedule = '$deploymentSchedule'"
    Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyBytes.ToArray()
}

$authContextParams = $parameters.AuthContext | ConvertFrom-Json | ConvertTo-HashTable
$bcAuthContext = New-BcAuthContext @authContextParams

$environmentUrl = "$($bcContainerHelperConfig.baseUrl.TrimEnd('/'))/$($bcAuthContext.tenantId)/$($parameters.EnvironmentName)"
$response = Invoke-RestMethod -UseBasicParsing -Method Get -Uri "$environmentUrl/deployment/url"
$sandboxEnvironment = ($response.environmentType -eq 1)

if ($sandboxEnvironment) {
    if ($parameters.Dependencies) {
        Write-Host "Installing/updating dependencies first"
        Publish-PerTenantExtensionApps -bcAuthContext $bcAuthContext -environment $parameters.EnvironmentName -appFiles $parameters.Dependencies
    }
    Write-Host "Sandbox environment ($($parameters.EnvironmentName)): publishing immediately via the dev endpoint"
    Publish-BcContainerApp -bcAuthContext $bcAuthContext -environment $parameters.EnvironmentName -appFile $parameters.Apps -useDevEndpoint -checkAlreadyInstalled -excludeRuntimePackages -replacePackageId
}
elseif ($parameters.type -eq 'CD' -and -not $parameters.continuousDeployment) {
    # Same safety net as AL-Go's own default logic (Deploy.ps1): do not auto-deploy to a
    # production environment from the CI/CD pipeline unless continuousDeployment is explicitly
    # enabled for it. Manual "Publish To Environment" runs (type 'Publish') are not affected.
    Write-Host "::Warning::Ignoring environment $($parameters.EnvironmentName), which is a production environment, and continuousDeployment is not enabled for it"
}
else {
    if ($parameters.Dependencies) {
        Write-Host "Installing/updating dependencies first"
        Publish-PerTenantExtensionApps -bcAuthContext $bcAuthContext -environment $parameters.EnvironmentName -appFiles $parameters.Dependencies
    }
    $schedule = if ($parameters.ContainsKey('deploymentSchedule')) { $parameters.deploymentSchedule } else { 'Immediate' }
    Write-Host "PRODUCTION environment ($($parameters.EnvironmentName)): scheduling install with deploymentSchedule = '$schedule'"
    foreach ($appFile in $parameters.Apps) {
        Invoke-PteInstallWithSchedule -bcAuthContext $bcAuthContext -environmentName $parameters.EnvironmentName -appFile $appFile -deploymentSchedule $schedule
    }
}
