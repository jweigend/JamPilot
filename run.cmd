@echo off
rem JamPilot starten - der Einstieg unter Windows.
rem
rem   run.cmd                 starten (richtet beim ersten Mal alles ein)
rem   run.cmd --delay 6       jede Option von `jampilot run`
rem   run.cmd devices         jeder andere Befehl (devices, selftest, analyze ...)
rem   run.cmd --neu           die Umgebung wegwerfen und neu aufsetzen
rem
rem Die Arbeit macht run.ps1; diese Huelle gibt es aus zwei Gruenden. Erstens
rem die Ausfuehrungsrichtlinie: Auf einem frisch aufgesetzten Windows steht sie
rem auf Restricted, und `.\run.ps1` scheitert dort an einer Meldung, die nach
rem einem kaputten Skript aussieht statt nach einer Einstellung. -ExecutionPolicy
rem Bypass gilt nur fuer diesen einen Aufruf und aendert nichts am System.
rem Zweitens reicht -File die Argumente unveraendert durch - `--delay 6` kommt
rem als `--delay 6` an und nicht als Bindeversuch an einen Parameter.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%
