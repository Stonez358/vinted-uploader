"""
Vinted Listing Generator
Analysiert Fotos mit Claude AI und erstellt fertige Vinted-Inserate.
"""

import sys
import json
import base64
import io
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Fehler: anthropic nicht installiert. Bitte 'pip install anthropic' ausfuehren.")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Fehler: Pillow nicht installiert. Bitte 'pip install Pillow' ausfuehren.")
    sys.exit(1)

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
STIL_FILE = BASE_DIR / "stil_vorlage.txt"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MAX_BILDBREITE = 1568


def lade_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"Fehler: {CONFIG_FILE} nicht gefunden.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    if config.get("api_key", "").startswith("DEIN_"):
        print("Fehler: Bitte deinen Claude API-Key in config.json eintragen.")
        sys.exit(1)
    return config


def lade_stilvorlage() -> str:
    if not STIL_FILE.exists():
        return ""
    with open(STIL_FILE, "r", encoding="utf-8") as f:
        inhalt = f.read()
    if "[Platzhalter" in inhalt and inhalt.count("[Platzhalter") >= 2:
        return ""
    return inhalt


def bereite_bild_vor(bild_pfad: Path, max_breite: int = MAX_BILDBREITE) -> tuple[str, str]:
    """Bild skalieren (falls noetig) und als Base64 zurueckgeben."""
    with Image.open(bild_pfad) as img:
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            hintergrund = Image.new("RGB", img.size, (255, 255, 255))
            hintergrund.paste(img, mask=img.split()[3])
            img = hintergrund

        if max(img.size) > max_breite:
            img.thumbnail((max_breite, max_breite), Image.LANCZOS)

        puffer = io.BytesIO()
        img.save(puffer, format="JPEG", quality=85, optimize=True)
        data = base64.standard_b64encode(puffer.getvalue()).decode("utf-8")

    return data, "image/jpeg"


def erstelle_listing(ordner: Path, config: dict, stil: str) -> str:
    """Claude AI analysiert Fotos und erstellt das Vinted-Inserat."""

    fotos = sorted([
        f for f in ordner.iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ])

    if not fotos:
        raise ValueError("Keine Fotos im Ordner gefunden.")

    max_fotos = config.get("max_fotos", 6)
    fotos = fotos[:max_fotos]

    stil_abschnitt = f"""
## Stil-Vorlage (imitiere genau diesen Stil):
{stil}
---
""" if stil.strip() else "Schreibe in einem freundlichen, ehrlichen und ansprechenden Stil auf Deutsch."

    system_prompt = f"""Du bist ein Experte fuer Vinted-Listings mit Fokus auf Vintage- und Secondhand-Kleidung.

{stil_abschnitt}

Analysiere die Fotos sehr sorgfaeltig. Achte besonders auf:
- Marke (Etikett lesen falls sichtbar)
- Groesse (Groessenetikett lesen, oder W/L-Angabe bei Jeans)
- Zustand (Tragespuren, Flecken, Loecher?)
- Kleidungsart und Kategorie
- Farbe und Material

Antworte AUSSCHLIESSLICH in folgendem Format (exakt diese Felder, keine Erklaerungen):

TITEL: [praegnanter Titel, max. 60 Zeichen]

BESCHREIBUNG:
[Beschreibung im vorgegebenen Stil - 3 bis 6 Saetze]

HASHTAGS: [mindestens 8 Hashtags, z.B. #vintage #retro ...]

PREIS: [nur die Zahl, z.B. 22]

MARKE: [Markenname exakt, z.B. Levi's, Nike, Zara, oder "Keine Angabe"]

GROESSE: [Groesse exakt wie auf Etikett, z.B. M, L, XL, W32/L30, 38, oder "Keine Angabe"]

ZUSTAND: [eines von: Neu mit Etikett | Neu ohne Etikett | Sehr gut | Gut | Befriedigend]

KATEGORIE: [Pfad z.B. "Herren > Kleidung > Hosen & Shorts > Jeans" oder "Damen > Kleidung > Jacken & Maentel > Winterjacken"]
"""

    inhalt = []

    for i, foto in enumerate(fotos, 1):
        print(f"   Verarbeite Foto {i}/{len(fotos)}: {foto.name}")
        try:
            data, mime = bereite_bild_vor(foto)
            inhalt.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": data
                }
            })
        except Exception as e:
            print(f"   Warnung: Foto {foto.name} konnte nicht verarbeitet werden: {e}")

    if not inhalt:
        raise ValueError("Kein Foto konnte verarbeitet werden.")

    inhalt.append({
        "type": "text",
        "text": "Analysiere alle Fotos und erstelle das Vinted-Inserat gemaess den Anweisungen."
    })

    client = anthropic.Anthropic(api_key=config["api_key"])

    antwort = client.messages.create(
        model=config.get("model", "claude-sonnet-4-6"),
        max_tokens=1200,
        system=system_prompt,
        messages=[{"role": "user", "content": inhalt}]
    )

    return antwort.content[0].text.strip()


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python generator.py <artikelordner> [--force]")
        sys.exit(1)

    ordner = Path(sys.argv[1])
    force = "--force" in sys.argv

    if not ordner.is_dir():
        print(f"Fehler: Ordner nicht gefunden: {ordner}")
        sys.exit(1)

    listing_datei = ordner / "listing.txt"

    if listing_datei.exists() and not force:
        print(f"Listing bereits vorhanden: {listing_datei}")
        print("Verwende --force um es neu zu generieren.")
        sys.exit(0)

    config = lade_config()
    stil = lade_stilvorlage()

    if not stil.strip():
        print("   Hinweis: Keine Stilvorlage gefunden - verwende Standard-Stil.")

    try:
        listing_text = erstelle_listing(ordner, config, stil)

        with open(listing_datei, "w", encoding="utf-8") as f:
            f.write(listing_text)
            f.write("\n")

        print(listing_text)
        sys.exit(0)

    except Exception as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
