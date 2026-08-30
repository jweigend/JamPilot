"""Erzeugt die BTC-Eingabebilder fuer HOW-IT-WORKS aus echten Musikbeispielen.

Gezeigt wird wirklich die Eingabematrix des Modells: 144 CQT-Baender x 108
Zeitschritte, ein float32 je Feld, erst aus features_from_audio() und dann mit
derselben globalen Mittelwert-/Std-Normalisierung wie vor der Inferenz.

Die ersten zwei Tafelfelder stammen aus festen 10-s-Ausschnitten realer
Referenzaufnahmen, die dieses Repository ohnehin fuer Messungen mitfuehrt:
`tests/reference/let_it_be.mp3` und `tests/reference/its_too_late.mp3`.
Gerade dafuer ist die Doku hilfreicher als bei den alten Kunst-Anschlaegen:
Man sieht links->rechts wirkliche Musik mit neuen Attacken, Akkordwechseln und
sich wandelnder Instrumentierung statt viermal dieselbe gezupfte Huelle.

Das dritte Feld bleibt digitale Stille bei -90 dBFS. Alle drei teilen sich
EINE Graustufen-Skala; sonst saehe Stille aus wie ausgesteuertes Rauschen.

    .venv/bin/python docs/bilder/make-btc-images.py
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jampilot import btc                                        # noqa: E402

HIER = Path(__file__).resolve().parent
REPO = HIER.parents[1]
REFERENZ = REPO / "tests" / "reference"
SR = btc.BTC_SR
DAUER = btc.BTC_WINDOW_SECONDS          # 10.0 s -> genau 108 Frames
SKALA = (-5.0, 2.0)                     # gemeinsame Graustufen-Grenzen
ZOOM = 4                                # Vergroesserung, nearest neighbour
BTC_FRAME = btc.BTC_FRAME_SECONDS


@dataclass(frozen=True)
class Beispiel:
    schluessel: str
    titel: str
    quelle: Path | None
    start: float = 0.0
    dauer: float = DAUER


BEISPIELE = [
    Beispiel("let-it-be", "Let It Be", REFERENZ / "let_it_be.mp3"),
    Beispiel("its-too-late", "It's Too Late", REFERENZ / "its_too_late.mp3"),
    Beispiel("silence", "Stille / silence", None),
]

ANNOTATIONEN = {
    "Let It Be": [
        (0.175157, "C"),
        (1.852358, "G"),
        (3.454535, "Am"),
        (4.720022, "Am/b7"),
        (5.126371, "Fmaj7"),
        (5.950680, "F6"),
        (6.774988, "C"),
        (8.423605, "G"),
    ],
    "It's Too Late": [
        (0.258, "Am7"),
        (2.392, "D6"),
        (5.013, "Am7"),
        (7.082, "D6"),
        (9.683, "Am7"),
    ],
}


def digitale_stille() -> np.ndarray:
    """Rauschteppich bei -90 dBFS - was der Digitalpfad liefert, wenn nichts laeuft."""
    rng = np.random.default_rng(7)
    return (rng.standard_normal(int(SR * DAUER)) * 10 ** (-90 / 20)).astype(np.float32)


def ausschnitt(beispiel: Beispiel) -> np.ndarray:
    """Lade einen festen 10-s-Ausschnitt in BTC-Abtastrate, mono."""
    if beispiel.quelle is None:
        return digitale_stille()
    y, _ = librosa.load(beispiel.quelle, sr=SR, mono=True,
                        offset=beispiel.start, duration=beispiel.dauer)
    ziel_laenge = int(round(SR * beispiel.dauer))
    if len(y) < ziel_laenge:
        y = np.pad(y, (0, ziel_laenge - len(y)))
    return y.astype(np.float32, copy=False)


def als_bild(merkmale: np.ndarray, ziel: Path) -> None:
    """(108, 144) -> Graustufen-PNG, tiefe Toene unten, Zeit nach rechts."""
    tief, hoch = SKALA
    norm = np.clip((merkmale - tief) / (hoch - tief), 0.0, 1.0)
    bild = (norm.T[::-1] * 255).astype(np.uint8)        # (144, 108), C1 unten
    Image.fromarray(bild, mode="L").resize(
        (bild.shape[1] * ZOOM, bild.shape[0] * ZOOM), Image.NEAREST
    ).save(ziel)


# --- Tafel mit Achsen -------------------------------------------------------
#
# Die Bildflaechen bleiben pixelgenau dieselben; die Tafel gibt ihnen nur
# Achsen und Titel. Beschriftet wird so knapp wie moeglich, damit dieselbe
# Grafik in beiden Doku-Sprachen verwendbar bleibt.

GRUND, TINTE, GEDECKT, STRICH = "#FBFAF7", "#243040", "#66707E", "#9AA4B1"
RAND_LINKS, RAND_OBEN, RAND_UNTEN, LUECKE = 66, 40, 48, 26
TAFEL_ZOOM = 3


def _schrift(groesse: int, fett: bool = False):
    pfad = ("/usr/share/fonts/truetype/dejavu/"
            + ("DejaVuSans-Bold.ttf" if fett else "DejaVuSans.ttf"))
    try:
        return ImageFont.truetype(pfad, groesse)
    except OSError:                       # Font nicht da -> PIL-Standard
        return ImageFont.load_default()


def als_tafel(panels: list[tuple[str, np.ndarray]], ziel: Path,
              rand_unten: int = RAND_UNTEN) -> None:
    """Die drei Bilder nebeneinander, mit Frequenz- und Zeitachse."""
    breite_p, hoehe_p = 108 * TAFEL_ZOOM, 144 * TAFEL_ZOOM
    breite = RAND_LINKS + len(panels) * breite_p + (len(panels) - 1) * LUECKE + 18
    hoehe = RAND_OBEN + hoehe_p + rand_unten
    tafel = Image.new("RGB", (breite, hoehe), GRUND)
    stift = ImageDraw.Draw(tafel)
    klein, titel = _schrift(13), _schrift(17, fett=True)

    tief, hoch = SKALA
    for i, (name, merkmale) in enumerate(panels):
        x0 = RAND_LINKS + i * (breite_p + LUECKE)
        norm = np.clip((merkmale - tief) / (hoch - tief), 0.0, 1.0)
        feld = (norm.T[::-1] * 255).astype(np.uint8)
        tafel.paste(Image.fromarray(feld, mode="L").convert("RGB").resize(
            (breite_p, hoehe_p), Image.NEAREST), (x0, RAND_OBEN))
        stift.rectangle([x0, RAND_OBEN, x0 + breite_p, RAND_OBEN + hoehe_p],
                        outline=STRICH)
        stift.text((x0 + breite_p // 2, RAND_OBEN - 22), name, font=titel,
                   fill=TINTE, anchor="mm")

        for sek in (0, 2.5, 5.0, 7.5, 10.0):
            x = x0 + int(sek / BTC_FRAME * TAFEL_ZOOM)
            x = min(x, x0 + breite_p)
            stift.line([x, RAND_OBEN + hoehe_p, x, RAND_OBEN + hoehe_p + 5], fill=STRICH)
            stift.text((x, RAND_OBEN + hoehe_p + 16), f"{sek:g}", font=klein,
                       fill=GEDECKT, anchor="mm")
        if i == len(panels) // 2:
            stift.text((x0 + breite_p // 2, RAND_OBEN + hoehe_p + 36),
                       "Sekunden / seconds", font=klein, fill=GEDECKT, anchor="mm")

    for oktave in range(6):
        bin_ = oktave * 24
        y = RAND_OBEN + hoehe_p - int(bin_ * TAFEL_ZOOM)
        stift.line([RAND_LINKS - 6, y, RAND_LINKS, y], fill=STRICH)
        stift.text((RAND_LINKS - 12, y), f"C{oktave + 1}", font=klein,
                   fill=GEDECKT, anchor="rm")
    stift.text((RAND_LINKS - 12, RAND_OBEN + 6), "B6", font=klein,
               fill=GEDECKT, anchor="rm")

    tafel.save(ziel)


def als_annotierte_tafel(panels: list[tuple[str, np.ndarray]], ziel: Path) -> None:
    """Tafel plus markierte Referenzwechsel fuer die ersten zwei Beispiele.

    Die Nummernkreise im Bild loest die Legende UNTER dem jeweiligen Feld auf
    (Zeitpunkt + Akkordname aus der .lab-Ground-Truth). Dafuer bekommt diese
    Tafel einen hoeheren Unterrand - die Legende der laengsten Spalte (8
    Wechsel) muss vollstaendig hineinpassen, PIL clippt sonst stumm. Text im
    Bild bleibt sprachneutral (Notennamen, Zahlen), die Grafik haengt in
    beiden Doku-Sprachen.
    """
    legend_start, legend_zeile = 56, 16
    zeilen_max = max(len(w) for w in ANNOTATIONEN.values())
    als_tafel(panels, ziel,
              rand_unten=legend_start + zeilen_max * legend_zeile + 12)
    tafel = Image.open(ziel).convert("RGB")
    stift = ImageDraw.Draw(tafel)
    klein = _schrift(12)
    farben = ["#D7263D", "#F49D37", "#140F2D", "#00A6A6",
              "#6A4C93", "#1982C4", "#8AC926", "#C1121F"]

    for panel_index, (titel, wechsel) in enumerate(ANNOTATIONEN.items()):
        x0 = RAND_LINKS + panel_index * (108 * TAFEL_ZOOM + LUECKE)
        y0 = RAND_OBEN
        for nummer, (sekunden, label) in enumerate(wechsel, start=1):
            x = x0 + int(sekunden / BTC_FRAME * TAFEL_ZOOM)
            x = min(x, x0 + 108 * TAFEL_ZOOM)
            farbe = farben[(nummer - 1) % len(farben)]
            stift.line([x, y0, x, y0 + 144 * TAFEL_ZOOM], fill=farbe, width=2)
            # Kreis knapp INNERHALB des Felds, nicht darueber - dort stuende
            # er im Paneltitel.
            stift.ellipse([x - 9, y0 + 4, x + 9, y0 + 22], fill=farbe,
                          outline="white", width=1)
            stift.text((x, y0 + 13), str(nummer), font=klein, fill="white", anchor="mm")

        legend_x = x0 + 10
        legend_y = RAND_OBEN + 144 * TAFEL_ZOOM + legend_start
        for nummer, (sekunden, label) in enumerate(wechsel, start=1):
            farbe = farben[(nummer - 1) % len(farben)]
            y = legend_y + (nummer - 1) * legend_zeile
            stift.ellipse([legend_x, y - 5, legend_x + 10, y + 5], fill=farbe,
                          outline="white", width=1)
            stift.text((legend_x + 16, y), f"{nummer}. {sekunden:0.2f}s  {label}",
                       font=klein, fill=TINTE, anchor="lm")

    tafel.save(ziel)


def main() -> None:
    modell = btc.BTCModel()
    panels = []
    for beispiel in BEISPIELE:
        y = ausschnitt(beispiel)
        roh = btc.features_from_audio(y, SR)
        merkmale = (roh - modell.mean) / modell.std
        ziel = HIER / f"btc-input-{beispiel.schluessel}.png"
        als_bild(merkmale, ziel)

        labels = modell.predict(roh)
        namen, anzahl = np.unique([btc.LABEL_NAMES[i] for i in labels], return_counts=True)
        haeufigstes = namen[anzahl.argmax()]
        anteil = anzahl.max() / len(labels)
        panels.append((beispiel.titel, merkmale))
        quelle = (f"{beispiel.quelle.relative_to(REPO)} @ {beispiel.start:.1f}-{beispiel.start + beispiel.dauer:.1f}s"
                  if beispiel.quelle else "digital silence")
        print(f"{beispiel.titel:14s} -> {ziel.name}  {merkmale.shape}  "
              f"Werte {merkmale.min():+.2f} bis {merkmale.max():+.2f}  "
              f"Top-Label: {haeufigstes} ({anteil:.0%})  Quelle: {quelle}")

    tafel = HIER / "btc-input-panels.png"
    als_tafel(panels, tafel)
    print(f"Tafel          -> {tafel.name}")

    annotiert = HIER / "btc-input-panels-annotated.png"
    als_annotierte_tafel(panels, annotiert)
    print(f"Annotiert      -> {annotiert.name}")


if __name__ == "__main__":
    main()
