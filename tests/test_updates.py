"""Die Update-Abfrage: Wann erscheint die Schaltflaeche - und wann NICHT?

Ins Netz geht hier nichts. Geprueft wird, was mit einer Antwort passiert,
und dass jeder Fehler auf dem Weg still "nichts Neues" bedeutet: Ein
Proberaum ohne WLAN ist der Normalfall.
"""

import io
import json
import socket
import urllib.error

import pytest

from jampilot import updates


def antwortet(tag):
    return lambda: tag


class TestVersionLesen:
    @pytest.mark.parametrize("text, erwartet", [
        ("v1.5.2", (1, 5, 2)),
        ("1.5.2", (1, 5, 2)),
        (" v1.10.0\n", (1, 10, 0)),
    ])
    def test_liest_release_tags(self, text, erwartet):
        assert updates.version_tupel(text) == erwartet

    @pytest.mark.parametrize("text", [
        "v1.6.0-rc1", "nightly", "v1.5", "1.5.2.1", "", None, 152,
        "v1.5.2<script>", "1.5.2 https://example.org"])
    def test_alles_andere_ist_keine_version(self, text):
        assert updates.version_tupel(text) is None


class TestVergleich:
    def test_neueres_release_wird_gemeldet(self):
        assert updates.neuere_version("1.5.1", antwortet("v1.5.2")) == "1.5.2"

    def test_dieselbe_version_ist_nichts_neues(self):
        assert updates.neuere_version("1.5.1", antwortet("v1.5.1")) is None

    def test_ein_aelteres_release_ist_nichts_neues(self):
        # Ein Entwickler-Checkout ist dem letzten Release voraus.
        assert updates.neuere_version("1.6.0", antwortet("v1.5.1")) is None

    def test_zahlen_nicht_zeichen_vergleichen(self):
        # Als Zeichenkette waere "1.10.0" kleiner als "1.9.0".
        assert updates.neuere_version("1.9.0", antwortet("v1.10.0")) == "1.10.0"
        assert updates.neuere_version("1.10.0", antwortet("v1.9.0")) is None

    def test_die_rueckgabe_ist_neu_zusammengesetzt(self):
        # Nicht der Text aus dem Netz, sondern die gelesenen Zahlen: Was im
        # Fenster steht, hat nie jemand anderes formuliert.
        assert updates.neuere_version("1.5.1", antwortet(" v01.06.00 ")) == "1.6.0"

    @pytest.mark.parametrize("tag", ["v2.0.0-beta", "latest", "", None, 7, {}])
    def test_ein_tag_das_keine_version_ist_faellt_weg(self, tag):
        assert updates.neuere_version("1.5.1", antwortet(tag)) is None


class TestScheiternIstStill:
    @pytest.mark.parametrize("fehler", [
        urllib.error.URLError("no route to host"),
        urllib.error.HTTPError(updates.RELEASES_API, 403, "rate limit", {}, None),
        socket.timeout("timed out"),
        json.JSONDecodeError("kaputt", "", 0),
        OSError("network unreachable"),
        ValueError("irgendetwas"),
    ])
    def test_jeder_fehler_heisst_nichts_neues(self, fehler):
        def wirft():
            raise fehler
        assert updates.neuere_version("1.5.1", wirft) is None


class TestAnfrage:
    """Was an GitHub geht und was aus der Antwort wird - gegen eine Attrappe."""

    @pytest.fixture
    def netz(self, monkeypatch):
        gesehen = {}

        def einrichten(koerper: bytes):
            def urlopen(anfrage, timeout=None, context=None):
                gesehen.update(url=anfrage.full_url, kopf=dict(anfrage.headers),
                               timeout=timeout, context=context)
                return io.BytesIO(koerper)
            monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
            return gesehen
        return einrichten

    def test_fragt_das_juengste_release_ab(self, netz):
        gesehen = netz(json.dumps({"tag_name": "v9.9.9", "body": "x"}).encode())
        assert updates.neuere_version("1.5.1") == "9.9.9"
        assert gesehen["url"] == updates.RELEASES_API
        assert gesehen["timeout"] == updates.TIMEOUT
        # GitHub verlangt einen User-Agent; mehr als Name und Version steht
        # nicht darin.
        assert gesehen["kopf"]["User-agent"] == f"JamPilot/{updates.__version__}"

    def test_zertifikate_werden_geprueft(self, netz):
        import ssl

        gesehen = netz(b'{"tag_name": "v9.9.9"}')
        updates.neuere_version("1.5.1")
        assert gesehen["context"].verify_mode == ssl.CERT_REQUIRED
        assert gesehen["context"].check_hostname

    @pytest.mark.parametrize("koerper", [
        b"", b"<html>captive portal</html>", b"[]", b'"v9.9.9"',
        b'{"message": "API rate limit exceeded"}',
        b'{"tag_name": "v9.9.9"' + b" " * (updates.MAX_BYTES + 10) + b"}",
    ])
    def test_unerwartete_antworten_fallen_weg(self, netz, koerper):
        netz(koerper)
        assert updates.neuere_version("1.5.1") is None

    def test_die_seite_hinter_der_schaltflaeche_steht_fest(self):
        # Kein Wert aus der Antwort bestimmt, was der Browser oeffnet.
        assert updates.RELEASES_SEITE == (
            "https://github.com/jweigend/JamPilot/releases/latest")
