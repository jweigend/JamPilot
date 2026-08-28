<#
JamPilot starten - unter Windows, aus einem frischen Checkout heraus, ohne
Vorbereitung. Das PowerShell-Gegenstueck zu run.sh + packaging/venv.sh.

    .\run.cmd                   starten (richtet beim ersten Mal alles ein)
    .\run.cmd --delay 6         jede Option von `jampilot run`
    .\run.cmd devices           jeder andere Befehl (devices, selftest, analyze ...)
    .\run.cmd --bundle          das eigenstaendige Programm + ZIP bauen
    .\run.cmd --neu             die Umgebung wegwerfen und neu aufsetzen

run.cmd ist nur eine Huelle um dieses Skript - sie umgeht die
Ausfuehrungsrichtlinie von PowerShell, an der `.\run.ps1` sonst scheitert
("Die Datei kann nicht geladen werden, da die Ausfuehrung von Skripts auf
diesem System deaktiviert ist"), und sie reicht die Argumente unveraendert
durch. Wer eine PowerShell mit RemoteSigned hat, kann genauso gut
`.\run.ps1` direkt aufrufen.

Der erste Aufruf legt .venv an und installiert die Abhaengigkeiten - das dauert
ein paar Minuten. JEDER WEITERE Aufruf ueberspringt das: Ein Stempel in .venv
haelt fest, gegen welche Sperrdatei und welches Python installiert wurde. Passt
er, ist nichts zu tun. Passt er nicht (Sperrdatei geaendert, Python
aktualisiert, Installation abgebrochen), wird nachinstalliert - von selbst.

ABSICHTLICH OHNE param()-Block: Sobald ein Skript Parameter deklariert,
versucht PowerShell jedes fuehrende `-` zu binden, und `--delay 6` stirbt an
"Es wurde kein Parameter gefunden, der dem Parameternamen 'delay' entspricht".
Ohne Deklaration landet alles unveraendert in $args - genau das, was ein
Weiterreicher braucht.

`--bundle` reicht an packaging/build.ps1 weiter, genau wie run.sh an
packaging/build.sh. Unter Windows entsteht dabei ein ORDNER im ZIP und keine
einzelne Datei - warum, steht im Kopf von packaging/jampilot.spec.
#>

# KEIN $ErrorActionPreference = 'Stop': Windows PowerShell 5.1 verpackt jede
# Zeile, die ein natives Programm nach stderr schreibt, in einen ErrorRecord.
# Mit 'Stop' braeche das Skript an einer pip-Warnung ab. Geprueft wird deshalb
# durchgehend $LASTEXITCODE - das ist die einzige Angabe, die bei nativen
# Aufrufen wirklich stimmt.
$ErrorActionPreference = 'Continue'

$Wurzel = $PSScriptRoot

# venv anlegen, pruefen, nachinstallieren - dasselbe Stueck, das auch
# packaging/build.ps1 benutzt. Setzt $VenvPy.
. (Join-Path $Wurzel 'packaging\venv.ps1')

$Rest = @($args)

# --- Argumente, die dieses Skript selbst beantwortet ------------------------

if ($Rest.Count -gt 0 -and $Rest[0] -eq '--neu') {
    Write-Host '==> werfe .venv weg'
    if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
    $Rest = @($Rest | Select-Object -Skip 1)
}

if ($Rest.Count -gt 0 -and $Rest[0] -eq '--bundle') {
    # Wie run.sh: durchreichen, mit allem, was dahinter steht (--force, --check).
    $bauen = @($Rest | Select-Object -Skip 1)
    & (Join-Path $Wurzel 'packaging\build.ps1') @bauen
    exit $LASTEXITCODE
}

# --- Los --------------------------------------------------------------------

Initialize-Venv
Test-System

$jam = @('-m', 'jampilot') + $Rest
& $VenvPy @jam
exit $LASTEXITCODE
