"""
Vinted Folder Watcher
Beobachtet den 'artikel'-Ordner und startet automatisch
die Listing-Generierung wenn neue Fotos hinzugefuegt werden.
"""

import time
import sys
import json
import subprocess
from pathlib import Path
from threading import Timer

try:
    from watchdog.observers.polling import PollingObserver
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Fehler: watchdog nicht installiert.")
    print("Bitte ausfuehren: pip install watchdog")
    sys.exit(1)

BASE_DIR = Path(__file__).parent
ARTIKEL_DIR = BASE_DIR / "artikel"
CONFIG_FILE = BASE_DIR / "config.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

pending_timer: dict[str, Timer] = {}


def lade_debounce() -> int:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("debounce_sekunden", 5)
    except Exception:
        return 5


def verarbeite_ordner(ordner_pfad: str) -> None:
    ordner = Path(ordner_pfad)
    listing_datei = ordner / "listing.txt"

    if listing_datei.exists():
        return

    fotos = [f for f in ordner.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
    if not fotos:
        return

    print(f"\n[STARTE] Ordner: {ordner.name}  ({len(fotos)} Foto(s) gefunden)")

    ergebnis = subprocess.run(
        [sys.executable, str(BASE_DIR / "generator.py"), str(ordner)],
        capture_output=False,
        text=True
    )

    if ergebnis.returncode == 0:
        print(f"[OK] listing.txt wurde erstellt: {listing_datei}")
    else:
        print(f"[FEHLER] Listing-Generierung fehlgeschlagen fuer: {ordner.name}")


class FotoHandler(FileSystemEventHandler):
    def __init__(self, debounce: int):
        self.debounce = debounce
        super().__init__()

    def on_created(self, event):
        self._pruefen(event)

    def on_moved(self, event):
        self._pruefen(event)

    def _pruefen(self, event):
        if event.is_directory:
            return

        pfad = Path(getattr(event, "dest_path", event.src_path))

        if pfad.suffix.lower() not in IMAGE_EXTENSIONS:
            return

        # Nur Unterordner von 'artikel/', nicht direkt in 'artikel/'
        if pfad.parent == ARTIKEL_DIR:
            print(f"  Hinweis: Fotos direkt in 'artikel/' ablegen funktioniert nicht.")
            print(f"  Bitte einen Unterordner erstellen, z.B. artikel\\mein_item\\")
            return

        if not pfad.parent.is_relative_to(ARTIKEL_DIR):
            return

        schluessel = str(pfad.parent)

        if schluessel in pending_timer:
            pending_timer[schluessel].cancel()

        print(f"  + Foto erkannt: {pfad.name} (warte {self.debounce}s auf weitere...)")

        timer = Timer(self.debounce, verarbeite_ordner, args=[schluessel])
        pending_timer[schluessel] = timer
        timer.start()


def scan_vorhandene_ordner():
    """Verarbeitet beim Start alle Unterordner die Fotos aber noch kein listing.txt haben."""
    if not ARTIKEL_DIR.exists():
        return
    for unterordner in ARTIKEL_DIR.iterdir():
        if not unterordner.is_dir():
            continue
        listing = unterordner / "listing.txt"
        if listing.exists():
            continue
        fotos = [f for f in unterordner.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
        if fotos:
            print(f"[GEFUNDEN] Ordner ohne listing.txt: {unterordner.name} ({len(fotos)} Foto(s))")
            verarbeite_ordner(str(unterordner))


def main():
    ARTIKEL_DIR.mkdir(exist_ok=True)
    debounce = lade_debounce()

    print("=" * 55)
    print("  VINTED AUTOMATISIERUNG  |  Ordner-Watcher aktiv")
    print("=" * 55)
    print(f"  Ueberwachter Ordner : {ARTIKEL_DIR}")
    print(f"  Warte-Zeit          : {debounce} Sekunden nach letztem Foto")
    print()
    print("  ABLAUF:")
    print("  1. Neuen Ordner anlegen:  artikel\\mein_artikel_name\\")
    print("  2. Fotos hineinkopieren   (max. 6 Fotos pro Artikel)")
    print("  3. listing.txt erscheint  automatisch im selben Ordner")
    print()
    print("  Zum Beenden: Strg+C")
    print("=" * 55)
    print()

    # Bereits vorhandene Ordner ohne listing.txt sofort verarbeiten
    scan_vorhandene_ordner()

    handler = FotoHandler(debounce)
    observer = PollingObserver(timeout=2)
    observer.schedule(handler, str(ARTIKEL_DIR), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for timer in pending_timer.values():
            timer.cancel()
        observer.stop()
        print("\nAutomatisierung beendet.")

    observer.join()


if __name__ == "__main__":
    main()
