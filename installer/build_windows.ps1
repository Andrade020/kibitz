# Gera o instalador do Windows: PyInstaller (app) + Stockfish verificado + Inno Setup.
# Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
# Assinatura de código (opcional): defina WINDOWS_CERT_PFX_BASE64 e WINDOWS_CERT_PASSWORD (veja docs/SIGNING.md).
param([string]$Version = "")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $root

# --- ambiente virtual limpo (só o necessário: build menor e reproduzível)
$venv = Join-Path (Join-Path $root "build") "venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
$py = "$venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -e ".[desktop]" pyinstaller

# --- versão: 0.1.0b1 (PEP 440) -> 0.1.0-beta.1 (exibição) e 0.1.0.1 (numérica)
$pkgVersion = (& $py -c "from kibitz import __version__ as v; print(v)").Trim()
if (-not $Version) { $Version = $pkgVersion -replace '^(\d+\.\d+\.\d+)b(\d+)$', '$1-beta.$2' }
$m = [regex]::Match($Version, '^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?')
$fileVersion = "{0}.{1}.{2}.{3}" -f $m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value, $(if ($m.Groups[4].Success) { $m.Groups[4].Value } else { "0" })
Write-Host "== Kibitz $Version (arquivo $fileVersion)"

# --- 2) Stockfish oficial, com SHA-256 fixado (o mesmo do manifesto do winget-pkgs)
$sfDir = Join-Path $root "build\stockfish_pkg"
if (-not (Test-Path "$sfDir\stockfish.exe")) {
  $url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip"
  $sha = "3C8BF1F9EA66A09350A40DF4F632288285AC206D99F33AB5842C408FC30B48A7"
  $zip = Join-Path $root "build\stockfish.zip"
  New-Item -ItemType Directory -Force (Split-Path $zip) | Out-Null
  Write-Host "Baixando Stockfish..."
  Invoke-WebRequest $url -OutFile $zip
  $got = (Get-FileHash $zip -Algorithm SHA256).Hash
  if ($got -ne $sha) { throw "SHA-256 do Stockfish não confere: $got" }
  $tmp = Join-Path $root "build\sf_extract"
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  Expand-Archive $zip $tmp
  New-Item -ItemType Directory -Force "$sfDir\licenses" | Out-Null
  Copy-Item "$tmp\stockfish\stockfish-windows-x86-64-universal.exe" "$sfDir\stockfish.exe"
  Copy-Item "$tmp\stockfish\Copying.txt" "$sfDir\licenses\Stockfish-Copying.txt"
  Copy-Item "$tmp\stockfish\AUTHORS" "$sfDir\licenses\Stockfish-AUTHORS.txt"
  "Stockfish 19 - https://github.com/official-stockfish/Stockfish (GPLv3). Código-fonte no repositório oficial." | Set-Content "$sfDir\licenses\Stockfish-SOURCE.txt" -Encoding utf8
}

# --- 3) app (PyInstaller, onedir)
Remove-Item "build\dist", "build\work" -Recurse -Force -ErrorAction SilentlyContinue
& $py -m PyInstaller installer\Kibitz.spec --noconfirm --distpath build\dist --workpath build\work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

# --- assinatura (opcional)
function Sign-File($path) {
  if (-not $env:WINDOWS_CERT_PFX_BASE64) { return }
  $pfx = Join-Path $root "build\cert.pfx"
  [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERT_PFX_BASE64))
  $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName | Select-Object -Last 1
  & $signtool.FullName sign /f $pfx /p $env:WINDOWS_CERT_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /d "Kibitz" $path
  Remove-Item $pfx -Force
}
Sign-File "build\dist\Kibitz\Kibitz.exe"

# --- 4) instalador (Inno Setup)
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup não encontrado (winget install JRSoftware.InnoSetup)" }
& $iscc "/DAppVersion=$Version" "/DFileVersion=$fileVersion" installer\Kibitz.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou" }
$setup = Get-ChildItem "build\installer\Kibitz-$Version-Setup.exe"
Sign-File $setup.FullName
$hash = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLower()
"$hash *$($setup.Name)" | Set-Content "$($setup.FullName).sha256" -Encoding ascii
Write-Host "== Pronto: $($setup.FullName) ($([math]::Round($setup.Length/1MB,1)) MB)`n   sha256 $hash"
