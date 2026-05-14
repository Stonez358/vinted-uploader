"""
Vinted Poster - Vollautomatisch
Fuellt alle Felder aus: Fotos, Titel, Beschreibung, Preis,
Marke, Groesse, Zustand, Kategorie.
User klickt nur noch "Veroeffentlichen".
"""

import sys
import re
import time
import subprocess
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Page
except ImportError:
    print("Fehler: playwright nicht installiert.")
    print("Bitte: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

BASE_DIR = Path(__file__).parent


def benachrichtigung(titel: str, nachricht: str):
    """Windows-Toast-Benachrichtigung anzeigen."""
    try:
        ps = (
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'$n = New-Object System.Windows.Forms.NotifyIcon; '
            f'$n.Icon = [System.Drawing.SystemIcons]::Information; '
            f'$n.Visible = $true; '
            f'$n.ShowBalloonTip(6000, "{titel}", "{nachricht}", '
            f'[System.Windows.Forms.ToolTipIcon]::Info); '
            f'Start-Sleep -Seconds 7; $n.Dispose()'
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=0x08000000
        )
    except Exception:
        pass
PROFIL_DIR = BASE_DIR / "chrome_profil"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VINTED_NEU_URL = "https://www.vinted.de/items/new"

# Mapping: KI-Ausgabe → Vinted-Zustand-Text im UI
ZUSTAND_MAPPING = {
    "neu mit etikett":   "Neu mit Etikett",
    "neu ohne etikett":  "Neu ohne Etikett",
    "sehr gut":          "Sehr gut",
    "gut":               "Gut",
    "befriedigend":      "Befriedigend",
}


# ─────────────────────────────────────────────
#  Listing parsen
# ─────────────────────────────────────────────

def parse_listing(pfad: Path) -> dict:
    text = pfad.read_text(encoding="utf-8")
    r = {}

    def hole(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    r["titel"]       = hole(r"TITEL:\s*(.+)")
    r["preis"]       = hole(r"PREIS:\s*(\d+(?:[.,]\d+)?)")
    r["marke"]       = hole(r"MARKE:\s*(.+)")
    r["groesse"]     = hole(r"GR[ÖO]SSE:\s*(.+)")
    r["zustand"]     = hole(r"ZUSTAND:\s*(.+)")
    r["kategorie"]   = hole(r"KATEGORIE:\s*(.+)")
    r["hashtags"]    = hole(r"HASHTAGS:\s*(.+)")

    beschr = re.search(r"BESCHREIBUNG:\s*\n(.*?)(?=\nHASHTAGS:|\nPREIS:|\nMARKE:)", text, re.DOTALL)
    r["beschreibung"] = beschr.group(1).strip() if beschr else ""

    # Preis normalisieren
    r["preis"] = r["preis"].replace(",", ".")

    # Keine-Angabe-Felder leeren
    for key in ("marke", "groesse"):
        if "keine angabe" in r[key].lower():
            r[key] = ""

    return r


# ─────────────────────────────────────────────
#  Browser-Hilfsfunktionen
# ─────────────────────────────────────────────

def warte_und_klick(page: Page, selector: str, timeout: int = 5000) -> bool:
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.click()
        return True
    except Exception:
        return False


def klick_nach_text(page: Page, text: str, timeout: int = 5000) -> bool:
    """Klickt auf ein Element das den angegebenen Text enthaelt."""
    try:
        el = page.get_by_text(re.compile(f"^{re.escape(text)}$", re.I)).first
        el.wait_for(state="visible", timeout=timeout)
        el.scroll_into_view_if_needed()
        el.click()
        return True
    except Exception:
        return False


def cookie_schliessen(page: Page):
    for t in ["Alle akzeptieren", "Akzeptieren", "Accept all", "OK"]:
        try:
            page.get_by_role("button", name=re.compile(t, re.I)).click(timeout=1500)
            time.sleep(0.5)
            return
        except PlaywrightTimeout:
            pass


def feld_fuellen(page: Page, label_re: str, wert: str, tag: str = "input") -> bool:
    pattern = re.compile(label_re, re.I)
    for strategie in [
        lambda: page.get_by_label(pattern).first,
        lambda: page.get_by_placeholder(pattern).first,
        lambda: page.locator(f'{tag}[placeholder*="{label_re}"]').first,
    ]:
        try:
            feld = strategie()
            feld.wait_for(state="visible", timeout=3000)
            feld.click()
            feld.fill(wert)
            return True
        except Exception:
            continue
    return False


def dropdown_auswaehlen(page: Page, feld_label_re: str, option_text: str) -> bool:
    """Oeffnet ein Dropdown und waehlt eine Option per Text aus."""
    pattern = re.compile(feld_label_re, re.I)
    try:
        # Feld anklicken um Dropdown zu oeffnen
        feld = page.get_by_label(pattern).first
        feld.click(timeout=3000)
        time.sleep(0.5)
        # Option suchen und klicken
        option = page.get_by_role("option", name=re.compile(re.escape(option_text), re.I)).first
        option.click(timeout=3000)
        return True
    except Exception:
        pass

    # Fallback: Button mit Labeltext suchen
    try:
        page.get_by_label(pattern).first.click(timeout=3000)
        time.sleep(0.5)
        klick_nach_text(page, option_text)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Kategorie-Navigation
# ─────────────────────────────────────────────

def kategorie_auswaehlen(page: Page, kategorie_pfad: str) -> bool:
    """
    Navigiert den Vinted-Kategorie-Baum.
    Erwartet Format: "Herren > Kleidung > Hosen & Shorts > Jeans"
    """
    if not kategorie_pfad:
        return False

    stufen = [s.strip() for s in kategorie_pfad.split(">")]
    print(f"  Kategorie: {' > '.join(stufen)}")

    # Kategorie-Feld oeffnen
    geoffnet = False
    for selector in [
        'button:has-text("Kategorie")',
        '[data-testid*="category"]',
        'button[aria-label*="Kategorie"]',
        'input[placeholder*="Kategorie"]',
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                el.click()
                geoffnet = True
                time.sleep(1)
                break
        except Exception:
            continue

    if not geoffnet:
        print("  Warnung: Kategorie-Feld nicht gefunden.")
        return False

    # Jede Stufe des Kategorie-Pfads anklicken
    for stufe in stufen:
        gefunden = False
        for selector in [
            f'button:has-text("{stufe}")',
            f'li:has-text("{stufe}")',
            f'[role="option"]:has-text("{stufe}")',
            f'span:has-text("{stufe}")',
        ]:
            try:
                el = page.locator(selector).first
                el.wait_for(state="visible", timeout=4000)
                el.scroll_into_view_if_needed()
                el.click()
                gefunden = True
                time.sleep(0.8)
                break
            except Exception:
                continue

        if not gefunden:
            print(f"  Warnung: Kategorie-Stufe '{stufe}' nicht gefunden.")
            return False

    return True


# ─────────────────────────────────────────────
#  Hauptfunktion
# ─────────────────────────────────────────────

def poste_artikel(ordner: Path):
    listing_datei = ordner / "listing.txt"
    if not listing_datei.exists():
        print(f"Fehler: listing.txt nicht gefunden in {ordner}")
        sys.exit(1)

    d = parse_listing(listing_datei)
    fotos = sorted([f for f in ordner.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS])

    if not fotos:
        print("Fehler: Keine Fotos gefunden.")
        sys.exit(1)

    print("\n" + "=" * 55)
    print(f"  Artikel  : {d.get('titel', '?')}")
    print(f"  Fotos    : {len(fotos)}")
    print(f"  Preis    : {d.get('preis', '?')} EUR")
    print(f"  Marke    : {d.get('marke', '?')}")
    print(f"  Groesse  : {d.get('groesse', '?')}")
    print(f"  Zustand  : {d.get('zustand', '?')}")
    print(f"  Kategorie: {d.get('kategorie', '?')}")
    print("=" * 55)

    PROFIL_DIR.mkdir(exist_ok=True)
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFIL_DIR),
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--window-size=900,700",
            "--window-position=50,50",
        ],
        no_viewport=True,
        locale="de-DE",
    )
    page = context.new_page()

    try:
        print("\nOeffne Vinted...")
        page.goto(VINTED_NEU_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        cookie_schliessen(page)

        # Login pruefen — warten bis eingeloggt, kein ENTER noetig
        if "login" in page.url.lower() or "signup" in page.url.lower() or "member" in page.url.lower():
            print("\n  Bitte im Browser einloggen.")
            print("  Das Fenster wartet automatisch bis du eingeloggt bist...\n")
            try:
                # Warten bis URL nicht mehr login/signup ist (max. 3 Minuten)
                page.wait_for_url(
                    lambda url: "login" not in url.lower() and "signup" not in url.lower(),
                    timeout=180000
                )
            except PlaywrightTimeout:
                print("  Timeout beim Login. Bitte nochmal starten.")
                return
            time.sleep(1)
            page.goto(VINTED_NEU_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

        # ── 1. FOTOS ──────────────────────────────────────────
        print("\n  [1/7] Fotos hochladen...")
        foto_pfade = [str(f.resolve()) for f in fotos]
        try:
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(foto_pfade, timeout=10000)
            time.sleep(3)
            print(f"       OK ({len(fotos)} Fotos)")
        except Exception as e:
            print(f"       Warnung: {e}")

        # ── 2. TITEL ──────────────────────────────────────────
        if d["titel"]:
            print(f"\n  [2/7] Titel: {d['titel']}")
            ok = feld_fuellen(page, "titel|title", d["titel"])
            if not ok:
                print("       Warnung: Feld nicht gefunden")

        # ── 3. KATEGORIE ──────────────────────────────────────
        print(f"\n  [3/7] Kategorie auswaehlen...")
        kategorie_auswaehlen(page, d["kategorie"])

        # ── 4. MARKE ──────────────────────────────────────────
        if d["marke"]:
            print(f"\n  [4/7] Marke: {d['marke']}")
            ok = feld_fuellen(page, "marke|brand|hersteller", d["marke"])
            if not ok:
                # Vinted hat ein Marken-Suchfeld
                try:
                    marke_feld = page.locator('input[placeholder*="Marke"], input[placeholder*="Brand"]').first
                    marke_feld.fill(d["marke"], timeout=3000)
                    time.sleep(1)
                    # Erstes Ergebnis der Autocomplete-Liste auswaehlen
                    option = page.locator('[role="option"]').first
                    option.click(timeout=3000)
                    print("       OK")
                except Exception as e:
                    print(f"       Warnung: {e}")

        # ── 5. GRÖSSE ─────────────────────────────────────────
        if d["groesse"]:
            print(f"\n  [5/7] Groesse: {d['groesse']}")
            ok = dropdown_auswaehlen(page, "gr(ö|o)sse|size|groesse", d["groesse"])
            if not ok:
                # Direktsuche im Dropdown
                try:
                    page.locator('button:has-text("Größe"), button:has-text("Groesse"), button:has-text("Size")').first.click(timeout=3000)
                    time.sleep(0.5)
                    klick_nach_text(page, d["groesse"])
                    print("       OK")
                except Exception as e:
                    print(f"       Warnung: {e}")

        # ── 6. ZUSTAND ────────────────────────────────────────
        if d["zustand"]:
            zustand_ui = ZUSTAND_MAPPING.get(d["zustand"].lower(), d["zustand"])
            print(f"\n  [6/7] Zustand: {zustand_ui}")
            ok = dropdown_auswaehlen(page, "zustand|condition", zustand_ui)
            if not ok:
                try:
                    page.locator('button:has-text("Zustand"), button:has-text("Condition")').first.click(timeout=3000)
                    time.sleep(0.5)
                    klick_nach_text(page, zustand_ui)
                    print("       OK")
                except Exception as e:
                    print(f"       Warnung: {e}")

        # ── 7. BESCHREIBUNG + HASHTAGS + PREIS ───────────────
        beschreibung_komplett = d["beschreibung"]
        if d["hashtags"]:
            beschreibung_komplett += "\n\n" + d["hashtags"]

        if beschreibung_komplett:
            print(f"\n  [7/7] Beschreibung eintragen...")
            ok = False
            try:
                textarea = page.locator("textarea").first
                textarea.fill(beschreibung_komplett, timeout=5000)
                ok = True
            except Exception:
                pass
            if not ok:
                ok = feld_fuellen(page, "beschreibung|description", beschreibung_komplett, "textarea")
            print("       OK" if ok else "       Warnung: nicht gefunden")

        if d["preis"]:
            print(f"\n       Preis: {d['preis']} EUR")
            ok = feld_fuellen(page, "preis|price", d["preis"])
            if not ok:
                try:
                    preis_feld = page.locator('input[type="number"], input[placeholder*="Preis"], input[placeholder*="Price"]').first
                    preis_feld.fill(d["preis"], timeout=3000)
                    ok = True
                except Exception:
                    pass
            print("       OK" if ok else "       Warnung: nicht gefunden")

        # ── ENTWURF SPEICHERN ─────────────────────────────────
        time.sleep(1)
        print()
        print("  Speichere als Entwurf...")

        entwurf_gespeichert = False
        entwurf_selektoren = [
            'button:has-text("Als Entwurf speichern")',
            'button:has-text("Entwurf speichern")',
            'button:has-text("Save as draft")',
            'button:has-text("Save draft")',
            '[data-testid*="draft"]',
        ]
        for sel in entwurf_selektoren:
            try:
                btn = page.locator(sel).first
                btn.wait_for(state="visible", timeout=4000)
                btn.scroll_into_view_if_needed()
                btn.click()
                entwurf_gespeichert = True
                break
            except Exception:
                continue

        if entwurf_gespeichert:
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeout:
                pass
            titel_kurz = d.get("titel", "Artikel")[:40]
            benachrichtigung(
                "Vinted Entwurf gespeichert",
                f"{titel_kurz} wurde als Entwurf gespeichert."
            )
            print()
            print("=" * 55)
            print("  ENTWURF GESPEICHERT!")
            print(f"  Artikel: {d.get('titel', '?')}")
            print("  Vinted > Verkaufen > Meine Entwuerfe")
            print("=" * 55)
        else:
            print()
            print("=" * 55)
            print("  'Als Entwurf speichern' nicht gefunden.")
            print("  Bitte manuell auf den Button klicken.")
            print("  Das Fenster bleibt offen.")
            print("=" * 55)
            # Offen lassen damit User manuell speichern kann
            try:
                page.wait_for_url(re.compile(r"vinted\.de/items/\d+"), timeout=300000)
            except PlaywrightTimeout:
                pass

    finally:
        try:
            context.close()
            playwright.stop()
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print("Verwendung: python poster.py <artikelordner>")
        print("Beispiel:   python poster.py artikel\\meine_jacke")
        sys.exit(1)

    ordner = Path(sys.argv[1])
    if not ordner.is_dir():
        print(f"Fehler: Ordner nicht gefunden: {ordner}")
        sys.exit(1)

    poste_artikel(ordner)


if __name__ == "__main__":
    main()
