# Deploy RFP Scanner Scheduler Logic App
# This script deploys the Azure Logic App that triggers scheduled scans
# Usage: .\deploy-logic-app.ps1 -ResourceGroupName "your-rg" -BackendApiUrl "https://your-backend/api/v1" -InternalApiKey "your-key"

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory=$true)]
    [string]$BackendApiUrl,

    [Parameter(Mandatory=$true)]
    [string]$InternalApiKey,

    [Parameter(Mandatory=$false)]
    [string]$LogicAppName = "rfp-scanner-scheduler",

    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RFP Scanner Scheduler - Logic App Deploy" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if logged in to Azure
Write-Host "Checking Azure login status..." -ForegroundColor Yellow
$context = Get-AzContext -ErrorAction SilentlyContinue
if (-not $context) {
    Write-Host "Not logged in to Azure. Please run 'Connect-AzAccount' first." -ForegroundColor Red
    exit 1
}
Write-Host "Logged in as: $($context.Account.Id)" -ForegroundColor Green
Write-Host ""

# Check if resource group exists
Write-Host "Checking resource group '$ResourceGroupName'..." -ForegroundColor Yellow
$rg = Get-AzResourceGroup -Name $ResourceGroupName -ErrorAction SilentlyContinue
if (-not $rg) {
    Write-Host "Creating resource group '$ResourceGroupName' in '$Location'..." -ForegroundColor Yellow
    $rg = New-AzResourceGroup -Name $ResourceGroupName -Location $Location
}
Write-Host "Resource group ready: $($rg.ResourceGroupName)" -ForegroundColor Green
Write-Host ""

# Get the template file path
$templatePath = Join-Path $PSScriptRoot "logic-app-scheduler.json"
if (-not (Test-Path $templatePath)) {
    Write-Host "Template file not found: $templatePath" -ForegroundColor Red
    exit 1
}

# Deploy the Logic App
Write-Host "Deploying Logic App '$LogicAppName'..." -ForegroundColor Yellow
Write-Host "  Backend API URL: $BackendApiUrl" -ForegroundColor Gray
Write-Host "  Schedule: Monday and Thursday at 6:00 AM UTC" -ForegroundColor Gray
Write-Host ""

$deployment = New-AzResourceGroupDeployment `
    -ResourceGroupName $ResourceGroupName `
    -TemplateFile $templatePath `
    -logicAppName $LogicAppName `
    -location $Location `
    -backendApiUrl $BackendApiUrl `
    -internalApiKey $InternalApiKey `
    -Verbose

if ($deployment.ProvisioningState -eq "Succeeded") {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Deployment Successful!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Logic App Name: $($deployment.Outputs.logicAppName.Value)" -ForegroundColor Cyan
    Write-Host "Resource ID: $($deployment.Outputs.logicAppResourceId.Value)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "The Logic App will run automatically on:" -ForegroundColor Yellow
    Write-Host "  - Every Monday at 6:00 AM UTC" -ForegroundColor White
    Write-Host "  - Every Thursday at 6:00 AM UTC" -ForegroundColor White
    Write-Host ""
    Write-Host "To test manually, go to Azure Portal > Logic Apps > $LogicAppName > Run Trigger" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "Deployment failed with state: $($deployment.ProvisioningState)" -ForegroundColor Red
    exit 1
}

