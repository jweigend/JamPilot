<#
Baut JamPilot als eigenstaendiges Programm fuer Windows - reproduzierbar, mit
ZIP zum Weitergeben. Das Gegenstueck zu packaging/build.sh.

    packaging\build.ps1              baut, wenn sich etwas geaendert hat (sonst nicht)
    packaging\build.ps1 --force      baut in jedem Fall neu
    packaging\build.ps1 --venv       baut in einem frischen venv aus requirements.lock
    packaging\build.ps1 --check      baut ZWEIMAL und prueft, ob es gleich ist

Der uebliche Weg ist `run.cmd --bundle` - das ist dasselbe Skript, nur richtet
es vorher die Umgebung ein, falls sie fehlt.

WAS HERAUSKOMMT, und warum es anders aussieht als unter Linux und macOS:

    dist\JamPilot\                          der Ordner, den der Nutzer bekommt
    dist\JamPilot-<version>-windows-<arch>.zip   genau dieser Ordner, gepackt

Ein ORDNER, keine einzelne Datei. Die Begruendung steht im Kopf von
packaging/jampilot.spec und ist keine technische: Eine unsignierte Exe dieser
Groesse (150 MB gepackt), die sich bei jedem Start nach %TEMP% auspackt, ist
technisch ein Packer und wird von SmartScreen und Virenscannern auch so
behandelt. Im ZIP ist ein Ordner derselbe eine Download - und er startet in
~0.45 s statt ~2.5 s.

REPRODUZIERBARKEIT. `--check` baut zweimal und vergleicht. Verglichen werden
die INHALTE des Ordners (jede Datei einzeln mit SHA-256), nicht das ZIP: Ein
ZIP traegt die Aenderungszeit jeder Datei im Kopf und kann deshalb gar nicht
zweimal gleich werden. Ob die Exe selbst es wird, entscheidet Windows und nicht
dieses Skript - das PE-Format traegt einen Zeitstempel im Header, und ob
PyInstaller ihn normalisiert, sagt einem nur die Messung. `--check` ist genau
diese Messung; was dabei herauskommt, steht im README.

Ohne PYTHONHASHSEED ist der Bau NICHT reproduzierbar - der Grund ist nichts
Zeitliches, sondern die Iterationsreihenfolge von Mengen und Dicts: Sie wandert
ins Inhaltsverzeichnis des Archivs. SOURCE_DATE_EPOCH setzen wir wie unter
Linux dazu, obwohl es dort nachgemessen nichts aendert.

ABSICHTLICH OHNE param()-Block - siehe die Begruendung im Kopf von run.ps1:
Sonst versucht PowerShell `--force` an einen Parameternamen zu binden.
#>

# KEIN 'Stop': Windows PowerShell 5.1 verpackt jede Zeile, die ein natives
# Programm nach stderr schreibt, in einen ErrorRecord - PyInstaller schreibt
# seine Fortschrittsmeldungen genau dorthin. Geprueft wird durchgehend
# $LASTEXITCODE, die einzige Angabe, die bei nativen Aufrufen wirklich stimmt.
$ErrorActionPreference = 'Continue'

$Wurzel = Split-Path -Parent $PSScriptRoot
. (Join-Path $Wurzel 'packaging\venv.ps1')   # Initialize-Venv, Find-Python, $VenvPy

$Modus = if ($args.Count -gt 0) { [string]$args[0] } else { '' }

$Dist = Join-Path $Wurzel 'dist'
$Werkstatt = Join-Path $Wurzel 'build'
$Buendel = Join-Path $Dist 'JamPilot'
$Exe = Join-Path $Buendel 'jampilot.exe'
$Stempeldatei = Join-Path $Dist '.quellstempel'

# --- Determinismus -----------------------------------------------------------
$env:PYTHONHASHSEED = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
$commit = & git -C $Wurzel log -1 --pretty=%ct 2>$null
if ($LASTEXITCODE -ne 0 -or -not $commit) { $commit = '1700000000' }
$env:SOURCE_DATE_EPOCH = $commit

& git -C $Wurzel diff --quiet HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'WARNUNG: Das Arbeitsverzeichnis ist schmutzig. SOURCE_DATE_EPOCH kommt'
    Write-Host '         vom letzten Commit - der Bau ist dann NICHT an den Quellstand'
    Write-Host '         gebunden, den er beschreibt.'
}

# --- Hilfsmittel -------------------------------------------------------------

function Get-TextHash([string]$text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $roh = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($text))
        return ([BitConverter]::ToString($roh) -replace '-', '').ToLower()
    }
    finally { $sha.Dispose() }
}

function Get-Version {
    # Aus jampilot/__init__.py, der einzigen Stelle, an der die Nummer steht.
    $text = Get-Content (Join-Path $Wurzel 'jampilot\__init__.py') -Raw
    if ($text -match '(?m)^__version__ = "([^"]+)"') { return $Matches[1] }
    Write-Host 'In jampilot/__init__.py steht kein __version__ - Abbruch.'
    exit 1
}

function Get-Architektur([string]$py) {
    # Die Architektur des INTERPRETERS, nicht die des Rechners: Ein 32-Bit-Python
    # auf einem 64-Bit-Windows baut ein 32-Bit-Bundle, und der Dateiname soll
    # nicht das Gegenteil behaupten. Die Namen sind dieselben wie in der CI.
    $m = (& $py -c 'import platform; print(platform.machine())').Trim().ToLower()
    switch ($m) {
        'amd64' { 'x86_64' }
        'x86'   { 'x86' }
        'arm64' { 'arm64' }
        default { $m }
    }
}

function Get-Quellstempel {
    # Woraus das Bundle besteht. Aendert sich hieran nichts, ist ein Neubau
    # vergeudete Zeit - PyInstaller braucht dafuer jedes Mal Minuten.
    $dateien = @(Get-ChildItem (Join-Path $Wurzel 'jampilot\*.py') |
                 Sort-Object Name | ForEach-Object { $_.FullName })
    $dateien += (Join-Path $Wurzel 'packaging\jampilot.spec')
    $dateien += (Join-Path $Wurzel 'packaging\entry.py')
    $dateien += (Join-Path $Wurzel 'packaging\build.ps1')
    $dateien += (Join-Path $Wurzel 'requirements.lock')
    $zeilen = $dateien | ForEach-Object {
        (Split-Path $_ -Leaf) + ' ' + (Get-FileHash -Algorithm SHA256 -Path $_).Hash.ToLower()
    }
    return Get-TextHash ($zeilen -join "`n")
}

function Get-Buendelstempel {
    # Eine Zahl fuer einen ganzen Ordner: jede Datei mit ihrem relativen Pfad
    # und ihrer Pruefsumme, in fester Reihenfolge. Das ist unter Windows das,
    # was unter Linux der SHA-256 der einen Binary ist.
    $vorspann = $Buendel.Length + 1
    $zeilen = Get-ChildItem -Recurse -File $Buendel |
        ForEach-Object { $_.FullName.Substring($vorspann) + ' ' +
                         (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLower() } |
        Sort-Object -CaseSensitive
    return Get-TextHash ($zeilen -join "`n")
}

function Invoke-Bau {
    foreach ($weg in @($Werkstatt, $Dist)) {
        if (Test-Path $weg) { Remove-Item -Recurse -Force $weg }
    }
    # --distpath/--workpath ausdruecklich: sonst entscheidet das aktuelle
    # Verzeichnis, wo dist landet, und dieses Skript ist von ueberall aufrufbar.
    & $PY -m PyInstaller (Join-Path $Wurzel 'packaging\jampilot.spec') `
        --noconfirm --log-level WARN `
        --distpath $Dist --workpath $Werkstatt
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host 'PyInstaller ist gescheitert - siehe die Meldungen oben.'
        exit 1
    }
}

# --- Was mit ins ZIP gehoert, ausser dem Programm ----------------------------

function Write-Beigaben {
    # Der Doppelklick-Starter. jampilot.exe LAESST sich doppelklicken - aber
    # wenn sie mit einer Meldung abbricht (kein zweiter Ausgang, Geraet mit
    # einem Kanal), schliesst Windows das Konsolenfenster im selben Moment, und
    # der Nutzer sieht ein Programm, das nichts tut. Genau die Meldung ist aber
    # die, die ihm sagt, was zu tun ist. Also: Fenster offenhalten, wenn etwas
    # schiefging - und nur dann.
    $starter = @'
@echo off
rem JamPilot starten - der Doppelklick-Weg.
rem
rem Der Unterschied zu jampilot.exe: Bricht JamPilot mit einer Meldung ab,
rem bleibt das Fenster stehen, statt sich im selben Moment zu schliessen.
rem Jedes Argument wird durchgereicht - "JamPilot.cmd devices" geht also auch.
setlocal
"%~dp0jampilot.exe" %*
set FEHLER=%ERRORLEVEL%
if not "%FEHLER%"=="0" (
    echo.
    echo JamPilot hat mit Fehlercode %FEHLER% beendet. Die Erklaerung steht oben.
    pause
)
exit /b %FEHLER%
'@
    [System.IO.File]::WriteAllText((Join-Path $Buendel 'JamPilot.cmd'),
                                   ($starter -replace "`r?`n", "`r`n"))

    # Die Kurzfassung neben dem Programm. Wer ein ZIP herunterlaedt, liest kein
    # GitHub - hier steht das, was er wissen muss, um es zu starten, und der
    # eine Fall, in dem es nicht von selbst geht.
    $liesmich = @"
JamPilot $Version - Windows ($Arch)
========================================================================

The chords of your system audio, seconds before you hear them.

    https://github.com/jweigend/JamPilot


GETTING STARTED

  1. Unpack this folder anywhere you like (keep it together - jampilot.exe
     needs the _internal folder next to it).
  2. Double-click JamPilot.cmd.
  3. Play something - YouTube, Spotify, anything.

There is nothing to install and nothing to configure. JamPilot borrows a
second output endpoint of your PC (an unused HDMI or S/PDIF port will do),
mutes it, and captures the system sound there; you keep listening to the
delayed music on your normal speakers. Both are restored when it exits.

Windows will ask twice on the first start, and both answers matter:

  * SmartScreen ("Windows protected your PC") - this program is not code
    signed. Click "More info", then "Run anyway".
  * The firewall dialog - the display page is served to your phone over
    Wi-Fi. Deny it and the QR code will not work. Allow private networks.


IF IT SAYS IT CANNOT TAKE OVER THE SYSTEM SOUND

Then this machine really has only one output. Install VB-CABLE
(https://vb-audio.com/Cable/, run VBCABLE_Setup_x64.exe as administrator,
then reboot) and start JamPilot again - it picks it up by itself.


USEFUL COMMANDS  (in a terminal, in this folder)

    jampilot.exe devices        what JamPilot found, and what it will use
    jampilot.exe --delay 8      more lead time (default is 5 seconds)
    jampilot.exe cleanup        put the audio back after a crash
    jampilot.exe selftest       check the installation without a sound card
    jampilot.exe --help         everything else

Your sound comes back on a normal exit, on Ctrl+C, and when you close the
console window. If the process is killed outright, the next start restores
it by itself - or 'jampilot.exe cleanup' does it now.


LICENCE AND SOURCE

See the repository above. Built from $Kurzcommit.
"@
    [System.IO.File]::WriteAllText((Join-Path $Buendel 'README.txt'),
                                   ($liesmich -replace "`r?`n", "`r`n"))
}

# --- Interpreter waehlen -----------------------------------------------------

if ($env:PY) {
    # Von aussen vorgegeben - so ruft die CI dieses Skript (PY=python), sie hat
    # die Pakete schon systemweit installiert und braucht kein venv.
    $PY = $env:PY
}
elseif ($Modus -eq '--venv') {
    # Frisches venv aus der Sperrdatei, bewusst OHNE Zwischenspeicher: der Bau
    # von ganz vorn, mit dem sich die Reproduzierbarkeit beweisen laesst.
    # requirements.txt taugt dafuer NICHT - es sagt "librosa>=0.10", und was
    # daraus wird, entscheidet der Kalender.
    Write-Host '==> frisches venv aus requirements.lock'
    $bauvenv = Join-Path $Wurzel '.build-venv'
    if (Test-Path $bauvenv) { Remove-Item -Recurse -Force $bauvenv }
    $gefunden = Find-Python
    $argumente = @($gefunden[1]) + @('-m', 'venv', $bauvenv)
    & $gefunden[0] @argumente
    if ($LASTEXITCODE -ne 0) { Write-Host 'Das venv liess sich nicht anlegen.'; exit 1 }
    $PY = Join-Path $bauvenv 'Scripts\python.exe'
    & $PY -m pip install --quiet --upgrade pip
    & $PY -m pip install --quiet -r (Join-Path $Wurzel 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { Write-Host 'pip ist gescheitert.'; exit 1 }
}
else {
    # Der normale Weg: dasselbe .venv wie beim Starten, und es wird nur dann
    # angelegt oder nachinstalliert, wenn wirklich etwas fehlt.
    Initialize-Venv
    $PY = $VenvPy
}

# PyInstaller steht in requirements.lock, aber nicht in requirements.txt - wer
# sein venv von Hand aufgesetzt hat, hat es womoeglich nicht. Das jetzt sagen,
# nicht in einer Meldung ueber ein fehlendes Modul.
& $PY -c "import PyInstaller" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'PyInstaller fehlt in dieser Umgebung:'
    Write-Host "    $PY -m pip install -r requirements.lock"
    exit 1
}

$Version = Get-Version
$Arch = Get-Architektur $PY
$Kurzcommit = & git -C $Wurzel log -1 --pretty=%h 2>$null
if ($LASTEXITCODE -ne 0 -or -not $Kurzcommit) { $Kurzcommit = 'an unknown commit' }
$ZipName = "JamPilot-$Version-windows-$Arch.zip"
$Zip = Join-Path $Dist $ZipName

# --- Bauen -------------------------------------------------------------------

Write-Host "==> Interpreter:        $PY"
Write-Host "==> Version:            $Version ($Arch)"
Write-Host "==> SOURCE_DATE_EPOCH:  $($env:SOURCE_DATE_EPOCH)  ($Kurzcommit)"

# Steht das Bundle schon da und hat sich an den Quellen nichts geaendert, ist
# nichts zu tun. Das ist der haeufigste Fall - und der einzige Grund, warum sich
# `run.cmd --bundle` zweimal hintereinander aufrufen laesst, ohne dass man
# Minuten verliert. `--check` beweist die Reproduzierbarkeit und muss dafuer
# zwingend neu bauen; `--force` ist der Holzhammer fuer alle anderen Faelle.
$quellen = Get-Quellstempel
$aktuell = $false
if ($Modus -ne '--check' -and $Modus -ne '--force' -and (Test-Path $Exe) -and
    (Test-Path $Zip) -and
    ((Get-Content $Stempeldatei -Raw -ErrorAction SilentlyContinue) -eq $quellen)) {
    Write-Host '==> dist\JamPilot ist aktuell - kein Neubau.'
    Write-Host '    (packaging\build.ps1 --force baut trotzdem neu)'
    $aktuell = $true
}
else {
    Write-Host '==> baue ...'
    Invoke-Bau

    # Der Test, der zaehlt - und er braucht keine Soundkarte. Der Selbsttest
    # zieht librosa, numba und beide CQTs durch und faellt ueber jedes Modul,
    # das PyInstaller nicht mitgenommen hat. Ein Bundle, das startet, ist noch
    # kein Bundle, das rechnet.
    Write-Host '==> Selbsttest aus dem Bundle ...'
    & $Exe selftest
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host 'Der Selbsttest ist im Bundle gescheitert - es fehlt etwas, das'
        Write-Host 'PyInstaller nicht eingesammelt hat. Kein ZIP, kein Stempel.'
        exit 1
    }
}

$hash1 = Get-Buendelstempel

if ($Modus -eq '--check') {
    Write-Host '==> zweiter Bau (Reproduzierbarkeit pruefen) ...'
    Invoke-Bau
    $hash2 = Get-Buendelstempel
    Write-Host ''
    Write-Host "    Lauf 1: $hash1"
    Write-Host "    Lauf 2: $hash2"
    if ($hash1 -eq $hash2) {
        Write-Host '    -> GLEICH. Reproduzierbar.'
    }
    else {
        Write-Host '    -> VERSCHIEDEN. Der Bau ist nicht reproduzierbar.'
        exit 1
    }
}

# --- Zusammenpacken ----------------------------------------------------------
#
# Erst hier, nach dem Bau und nach dem Selbsttest - und nach --check, dessen
# zweiter Bau dist\ abraeumt und ein frueher gebautes ZIP mitnehmen wuerde.
if (-not $aktuell) {
    Write-Host '==> Beigaben (Starter, README) ...'
    Write-Beigaben

    Write-Host "==> packe $ZipName ..."
    if (Test-Path $Zip) { Remove-Item -Force $Zip }
    # Nicht Compress-Archive: Das braucht fuer die ~2000 Dateien eines
    # PyInstaller-Ordners Minuten. Dieselbe Bibliothek, direkt aufgerufen,
    # braucht Sekunden. Das letzte $true nimmt den Ordnernamen mit ins Archiv -
    # ohne das entpackt der Nutzer 2000 Dateien in sein Downloads-Verzeichnis.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $Buendel, $Zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)

    # Der Stempel steht ERST HIER - nach Bau, Selbsttest und ZIP. Ein Lauf, der
    # auf halber Strecke abbrach, hinterlaesst keinen, und der naechste Aufruf
    # baut zu Ende, statt eine halbe dist\ fuer fertig zu halten.
    [System.IO.File]::WriteAllText($Stempeldatei, $quellen)
}

$zipHash = (Get-FileHash -Algorithm SHA256 -Path $Zip).Hash.ToLower()
$zipMB = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
$ordnerMB = [math]::Round(((Get-ChildItem -Recurse -File $Buendel |
                            Measure-Object -Property Length -Sum).Sum / 1MB), 1)

Write-Host ''
Write-Host "  fertig:  dist\$ZipName  ($zipMB MB, ausgepackt $ordnerMB MB)"
Write-Host "  sha256:  $zipHash"
Write-Host ''
Write-Host '  Das ZIP ist das, was hochgeladen wird. Die Pruefsumme gehoert in die'
Write-Host '  Release-Notes - sie ist das Einzige, woran ein Nutzer erkennt, dass er'
Write-Host '  bekommen hat, was hier gebaut wurde.'
exit 0
