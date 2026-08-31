#Requires -RunAsAdministrator
<#
    Configures the laptop's Ethernet adapter with the static IP that pairs with the
    Raspberry Pi (PI_IP = 192.168.1.20 in raspberry/main.py, LAPTOP_IP = 192.168.1.10).
    Run from an elevated PowerShell: .\configure-network.ps1
#>

param(
    [string]$IPAddress = "192.168.1.10",
    [int]$PrefixLength = 24,
    [string]$Gateway = "192.168.1.1",
    [string[]]$DnsServers = @("8.8.8.8", "1.1.1.1"),
    [string]$AdapterName
)

$ErrorActionPreference = "Stop"

if (-not $AdapterName) {
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" -and $_.MediaType -eq "802.3" } | Select-Object -First 1
    if (-not $adapter) {
        $adapter = Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq "802.3" } | Select-Object -First 1
    }
    if (-not $adapter) {
        Write-Error "Fant ingen Ethernet-adapter. Oppgi navnet med -AdapterName."
        exit 1
    }
    $AdapterName = $adapter.Name
}

Write-Host "[*] Konfigurerer adapter '$AdapterName' med statisk IP $IPAddress/$PrefixLength (gateway $Gateway)..."

# Clear any existing static/DHCP IPv4 config so re-running this script is idempotent
Get-NetIPAddress -InterfaceAlias $AdapterName -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
Get-NetRoute -InterfaceAlias $AdapterName -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.NextHop -ne "0.0.0.0" } |
    Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue

Set-NetIPInterface -InterfaceAlias $AdapterName -Dhcp Disabled

New-NetIPAddress -InterfaceAlias $AdapterName -IPAddress $IPAddress -PrefixLength $PrefixLength -DefaultGateway $Gateway | Out-Null
Set-DnsClientServerAddress -InterfaceAlias $AdapterName -ServerAddresses $DnsServers

Write-Host "[OK] '$AdapterName' er satt opp med statisk IP $IPAddress. Raspberry Pi forventes på 192.168.1.20."
