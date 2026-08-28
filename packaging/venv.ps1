<#
Die Umgebung herstellen - einmal teuer, danach umsonst. Das PowerShell-
Gegenstueck zu packaging/venv.sh.

Wird von run.ps1 und packaging/build.ps1 EINGEBUNDEN (dot-sourcing:
`. "$Wurzel\packaging\venv.ps1"`), nicht ausgefuehrt. Der Aufrufer muss vorher
$Wurzel auf das Projektverzeichnis gesetzt haben.

Das Problem, das dieses Stueck loest, steht ausfuehrlich in venv.sh und gilt
hier unveraendert: Ein abgebrochener Aufbau hinterlaesst ein .venv, das
AUSSIEHT wie eine fertige Umgebung und keine ist. Deshalb ein Stempel, der den
Sollzustand beschreibt (Sperrdatei + Python), und der wird ERST GESCHRIEBEN,
WENN ALLES DURCH IST.

Warum ueberhaupt ein zweites Mal in PowerShell, statt die Logik einmal in
Python zu schreiben? Weil sie genau das herstellt, was Python hier noch nicht
hat - ein venv mit den Abhaengigkeiten. Sie muss also in der Sprache stehen,
die auf der Plattform ohne Vorbedingung laeuft.
#>

$Venv = Join-Path $Wurzel '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$Sperrdatei = Join-Path $Wurzel 'requirements.lock'
$Stempel = Join-Path $Venv '.jampilot-stempel'
$StempelSchema = 1        # hochzaehlen, wenn sich die Logik hier aendert

function Find-Python {
    # NICHT einfach `python`: Windows liefert unter diesem Namen die
    # App-Ausfuehrungsaliasse des Microsoft Store aus, die beim Aufruf bloss den
    # Store oeffnen. Der py-Launcher weiss dagegen, welche Interpreter wirklich
    # installiert sind - und `-3` nimmt davon die hoechste 3.x.
    $kandidaten = @()
    if ($env:PYTHON) { $kandidaten += , @($env:PYTHON, @()) }
    if (Get-Command py -ErrorAction SilentlyContinue) { $kandidaten += , @('py', @('-3')) }
    $kandidaten += , @('python', @())

    foreach ($k in $kandidaten) {
        $exe = $k[0]
        $vor = $k[1]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $pruef = @($vor) + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)')
        & $exe @pruef | Out-Null
        if ($LASTEXITCODE -eq 0) { return , @($exe, $vor) }
    }

    Write-Host ''
    Write-Host 'JamPilot braucht Python 3.10 oder neuer - gefunden wurde keines.'
    Write-Host ''
    Write-Host '  winget install Python.Python.3.13'
    Write-Host '  oder https://www.python.org/downloads/windows/'
    Write-Host ''
    Write-Host 'Beim Installieren "Add python.exe to PATH" ankreuzen, sonst findet dieses'
    Write-Host 'Skript den Interpreter nicht.'
    exit 1
}

function Get-Fingerabdruck([string]$py) {
    # Woran haengt die Umgebung? An der Sperrdatei und an dem Python, mit dem
    # sie gebaut wurde. Aendert sich eines von beiden, ist der Stempel
    # ungueltig - ein Update von 3.12 auf 3.13 laesst ein venv zurueck, dessen
    # Interpreter ins Leere zeigt, und genau das faellt hier auf.
    $summe = (Get-FileHash -Algorithm SHA256 -Path $Sperrdatei).Hash.ToLower()
    $version = & $py -c 'import platform, sys; print(sys.version.split()[0], platform.machine())'
    return "$summe $version $StempelSchema"
}

function Test-Pakete([string]$py) {
    # Sind die Pakete wirklich da? Ein Stempel bezeugt nur, dass pip einmal
    # durchgelaufen ist - nicht, dass seither niemand aufgeraeumt hat.
    #
    # Geprueft wird mit find_spec, nicht mit `import`: Das sucht die Module
    # bloss im Dateisystem, statt sie auszufuehren. librosa zu importieren
    # kostet ueber eine Sekunde (numba, scipy, sklearn haengen daran) - und
    # diese Sekunde fiele bei JEDEM Start an.
    #
    # EINFACHE Anfuehrungszeichen im Python-Text, nicht doppelte: Windows
    # PowerShell 5.1 baut die Kommandozeile fuer ein natives Programm selbst
    # zusammen und verliert dabei eingebettete `"`. Aus find_spec("numpy")
    # wuerde find_spec(numpy) - ein NameError, den niemand sieht, weil hier nur
    # der Exitcode zaehlt. Die Pruefung meldete dann bei JEDEM Start "Pakete
    # fehlen" und warf die fertige Umgebung weg.
    $code = 'import importlib.util as u, sys; ' +
            "sys.exit(1 if [m for m in ('numpy', 'librosa', 'sounddevice', " +
            "'soundfile', 'qrcode', 'PySide6') if u.find_spec(m) is None] else 0)"
    & $py -c $code | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function New-Venv {
    $gefunden = Find-Python
    $exe = $gefunden[0]
    $vor = $gefunden[1]
    $anzeige = (@((Get-Command $exe).Source) + $vor) -join ' '
    Write-Host "==> lege .venv an  ($anzeige)"
    $argumente = @($vor) + @('-m', 'venv', $Venv)
    & $exe @argumente
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Das venv liess sich nicht anlegen.'
        exit 1
    }
}

function Initialize-Venv {
    # Interpreter da UND pip da? `python -m venv` legt zuerst die exe an, holt
    # DANN pip und schreibt zuletzt die activate-Skripte. Bricht es in der
    # Mitte ab, bleibt ein .venv zurueck, dessen Interpreter tadellos startet
    # und in dem trotzdem kein pip liegt - die Meldung "No module named pip"
    # sagt dann nicht, dass das venv der Schuldige ist.
    $brauchbar = $false
    if (Test-Path $VenvPy) {
        # Einfache Anfuehrungszeichen - siehe die Begruendung in Test-Pakete.
        & $VenvPy -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('pip') else 1)" | Out-Null
        $brauchbar = ($LASTEXITCODE -eq 0)
    }

    if (-not $brauchbar) {
        if (Test-Path $Venv) {
            Write-Host '==> .venv ist unbrauchbar (abgebrochen oder verwaist) - wird neu angelegt'
            Remove-Item -Recurse -Force $Venv
        }
        New-Venv
    }
    elseif ((Get-Content $Stempel -Raw -ErrorAction SilentlyContinue) -eq (Get-Fingerabdruck $VenvPy)) {
        if (Test-Pakete $VenvPy) { return }      # DER NORMALFALL: nichts zu tun
        # Der Stempel sagt "fertig", die Pakete sagen etwas anderes. Dann ist
        # die Umgebung beschaedigt - und sie wird WEGGEWORFEN, nicht repariert.
        # pip heilt das naemlich nicht: Fehlt ein Paketverzeichnis, liegt sein
        # .dist-info aber noch da, haelt pip es fuer installiert und tut nichts.
        Write-Host '==> .venv ist beschaedigt (Pakete fehlen) - wird neu angelegt'
        Remove-Item -Recurse -Force $Venv
        New-Venv
    }

    Write-Host '==> installiere die Abhaengigkeiten aus requirements.lock'
    Write-Host '    (das dauert beim ALLERERSTEN Mal ein paar Minuten - danach nie wieder)'
    & $VenvPy -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $VenvPy -m pip install --quiet -r $Sperrdatei
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Erst jetzt. Bricht oben etwas ab, gibt es keinen gueltigen Stempel - und
    # der naechste Aufruf installiert zu Ende, statt mit einer halben Umgebung
    # loszulaufen und an einer nichtssagenden Meldung zu sterben.
    [System.IO.File]::WriteAllText($Stempel, (Get-Fingerabdruck $VenvPy))
}

function Test-System {
    # PortAudio steckt unter Windows IM sounddevice-Wheel (anders als unter
    # Linux, wo es vom System kommt). Scheitert der Import trotzdem, ist etwas
    # anderes kaputt - dann soll die echte Meldung zu sehen sein statt eines
    # Ratschlags, der ins Leere zeigt.
    & $VenvPy -c 'import sounddevice' | Out-Null
    if ($LASTEXITCODE -eq 0) { return }
    Write-Host ''
    Write-Host 'sounddevice laesst sich nicht importieren - hier die Meldung im Klartext:'
    & $VenvPy -c 'import sounddevice'
    exit 1
}
