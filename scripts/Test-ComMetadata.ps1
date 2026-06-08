#Requires -Version 5.1
. (Join-Path $PSScriptRoot '..\Lib\1CPlatform.ps1')

function Get-1CComProperty { param($ComObject, [string]$Name)
    return $ComObject.GetType().InvokeMember($Name, [System.Reflection.BindingFlags]::GetProperty, $null, $ComObject, $null)
}

$connection = (New-Object -ComObject 'V83.COMConnector').Connect('File="C:\Users\aaposmetev\Documents\1C\DemoTrd";Usr="Администратор";Pwd="";')
$meta = Get-1CComProperty $connection 'Metadata'
$doc = (Get-1CComProperty $meta 'Documents' | Select-Object -First 1)

foreach ($name in @('Name', 'Synonym', 'Attributes', 'TabularSections')) {
    try {
        $value = Get-1CComProperty $doc $name
        if ($null -eq $value) { Write-Output "$name null"; continue }
        if ($value -is [string]) { Write-Output "$name => $value"; continue }
        $count = 0
        foreach ($item in $value) { $count++ }
        Write-Output "$name count=$count"
    }
    catch { Write-Output "$name FAIL $($_.Exception.Message)" }
}

$attr = (Get-1CComProperty $doc 'Attributes' | Select-Object -First 1)
try { Write-Output ('attr Name=' + (Get-1CComProperty $attr 'Name')) } catch { Write-Output 'attr Name FAIL' }
