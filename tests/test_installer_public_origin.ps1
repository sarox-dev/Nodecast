$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $root "install.ps1"), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$helper = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Resolve-PublicOrigin"
}, $true)
if (-not $helper) { throw "Missing public origin helper" }
. ([scriptblock]::Create($helper.Extent.Text))
$cases = @(
    @("", "localhost", 5000, "http://localhost:5000"),
    @("http://192.168.8.116:5000", "192.168.8.116", 5000, "http://192.168.8.116:5000"),
    @("https://nodecast.lan:8443", "nodecast.lan", 5000, "https://nodecast.lan:8443"),
    @("https://nodecast.lan/", "nodecast.lan", 5000, "https://nodecast.lan"),
    @("https://Nodecast.LAN:8443", "nodecast.lan", 5000, "https://nodecast.lan:8443"),
    @("https://old.lan:8443", "new.lan", 5000, "http://new.lan:5000"),
    @("https://nodecast.lan:8443", "localhost", 5000, "http://localhost:5000"),
    @("https://user:password@nodecast.lan", "nodecast.lan", 5000, "http://nodecast.lan:5000"),
    @("https://nodecast.lan/path", "nodecast.lan", 5000, "http://nodecast.lan:5000"),
    @("https://nodecast.lan/?key=secret", "nodecast.lan", 5000, "http://nodecast.lan:5000")
)
foreach ($case in $cases) {
    $actual = Resolve-PublicOrigin $case[0] $case[1] $case[2]
    if ($actual -ne $case[3]) { throw "Public origin regression for $($case[0])" }
}
Write-Output "10 PowerShell public origin checks passed"
