# Lo lanza "Aurum WhatsApp.cmd": si a los 12 s la app no responde, avisa a Render
# con el sistema y la versión de Chrome. Sin datos de clientes.
param([string]$Version = '')
Start-Sleep -Seconds 12
try { Invoke-WebRequest -Uri 'http://127.0.0.1:3131/api/estado' -UseBasicParsing -TimeoutSec 5 | Out-Null; exit 0 } catch {}
$mat = ''
try { $mat = (Get-Content (Join-Path $env:APPDATA 'AurumWhatsApp\config.json') -Raw | ConvertFrom-Json).mat } catch {}
$chrome = 'sin Chrome'
foreach ($c in @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")) {
  if (Test-Path $c) { $chrome = 'Chrome ' + (Get-Item $c).VersionInfo.ProductVersion; break }
}
$cuerpo = @{ mat = "$mat"; evento = 'no-arranca'; version = $Version; so = 'Windows ' + [Environment]::OSVersion.Version; arch = $env:PROCESSOR_ARCHITECTURE; chrome = $chrome; detalle = 'La app no responde en el puerto 3131' } | ConvertTo-Json -Compress
try { Invoke-RestMethod -Method Post -Uri 'https://tecnicos-aurum.onrender.com/wa-diagnostico' -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($cuerpo)) -TimeoutSec 90 | Out-Null } catch {}
