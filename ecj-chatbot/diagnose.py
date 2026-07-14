"""
EuGH Chatbot - Setup Diagnosis / Diagnose-Werkzeug

Run this whenever the app "doesn't work" to find out exactly which part
is broken:

    python diagnose.py

It checks, in order:
  1. Python version
  2. Required packages
  3. Network access to EUR-Lex (SPARQL endpoint + document download)
  4. Anthropic API key & connectivity
  5. Data directory & existing downloads/index
  6. Embedding/vector store (ChromaDB)
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

PASS = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"

results: list[tuple[bool, str]] = []


def report(ok: bool, label: str, detail: str = "", hint: str = ""):
    marker = PASS if ok else FAIL
    print(f"{marker} {label}" + (f" – {detail}" if detail else ""))
    if not ok and hint:
        print(f"       Hinweis: {hint}")
    results.append((ok, label))


def warn(label: str, detail: str = ""):
    print(f"{WARN} {label}" + (f" – {detail}" if detail else ""))


def check_python():
    v = sys.version_info
    ok = (3, 11) <= (v.major, v.minor) <= (3, 13)
    report(
        ok,
        "Python-Version",
        f"{v.major}.{v.minor}.{v.micro}",
        "Bitte Python 3.11-3.13 verwenden (chromadb unterstützt 3.14 noch nicht). "
        "Windows: py -3.13 -m streamlit run app.py"
    )
    return ok


def check_packages():
    packages = {
        "SPARQLWrapper": "SPARQLWrapper",
        "requests": "requests",
        "bs4": "beautifulsoup4",
        "lxml": "lxml",
        "dotenv": "python-dotenv",
        "tqdm": "tqdm",
        "anthropic": "anthropic",
        "streamlit": "streamlit",
        "chromadb": "chromadb",
        "sentence_transformers": "sentence-transformers",
    }
    all_ok = True
    for module, pip_name in packages.items():
        try:
            __import__(module)
            report(True, f"Paket {pip_name}")
        except Exception as e:
            all_ok = False
            report(False, f"Paket {pip_name}", str(e)[:120],
                   f"pip install {pip_name}")
    return all_ok


def check_eurlex_sparql():
    try:
        from data_acquisition import get_case_law_metadata
        t0 = time.time()
        cases = get_case_law_metadata(limit=5, year_from=2023)
        elapsed = time.time() - t0
        if cases:
            report(True, "EUR-Lex SPARQL-Endpoint",
                   f"{len(cases)} Urteile in {elapsed:.1f}s, z.B. {cases[0].get('celex')}")
            return cases
        report(False, "EUR-Lex SPARQL-Endpoint", "Abfrage lieferte 0 Ergebnisse",
               "EUR-Lex evtl. überlastet - später erneut versuchen")
        return []
    except Exception as e:
        report(False, "EUR-Lex SPARQL-Endpoint", str(e)[:200],
               "Internetverbindung prüfen; Firewall/Proxy muss "
               "publications.europa.eu (HTTPS) erlauben")
        return []


def check_eurlex_document(cases: list):
    try:
        from data_acquisition import fetch_document_text_with_fallback
        celex = cases[0]["celex"] if cases else "62018CJ0311"  # Schrems II as fallback
        text, lang = fetch_document_text_with_fallback(celex)
        if text:
            report(True, "EUR-Lex Dokument-Download",
                   f"CELEX {celex}: {len(text)} Zeichen ({lang})")
            return True
        report(False, "EUR-Lex Dokument-Download",
               f"CELEX {celex} in keiner Sprache abrufbar",
               "eur-lex.europa.eu muss per HTTPS erreichbar sein "
               "(Firewall/Proxy prüfen)")
        return False
    except Exception as e:
        report(False, "EUR-Lex Dokument-Download", str(e)[:200],
               "eur-lex.europa.eu muss per HTTPS erreichbar sein")
        return False


def check_anthropic():
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        report(False, "ANTHROPIC_API_KEY",
               "nicht gesetzt",
               "Datei .env anlegen (Vorlage: .env.example) und "
               "ANTHROPIC_API_KEY=sk-ant-... eintragen")
        return False
    if not api_key.startswith("sk-ant-"):
        warn("ANTHROPIC_API_KEY", "gesetzt, beginnt aber nicht mit 'sk-ant-' - bitte prüfen")

    try:
        from anthropic import Anthropic
        from config import get_config
        client = Anthropic(api_key=api_key)
        model = get_config().llm_model
        response = client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": "Antworte nur mit: OK"}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        report(True, "Anthropic API", f"Modell {model} antwortet: {text.strip()[:20]}")
        return True
    except Exception as e:
        report(False, "Anthropic API", str(e)[:200],
               "API-Schlüssel prüfen (https://console.anthropic.com), "
               "Guthaben prüfen, api.anthropic.com muss erreichbar sein")
        return False


def check_data_dir():
    try:
        from config import get_config
        cfg = get_config()
        cfg.ensure_directories()
        status = cfg.get_status()
        report(True, "Datenverzeichnis", status["data_dir"])
        print(f"       Lokale Entscheidungen: {status['cases_count']}, "
              f"Index vorhanden: {'ja' if status['index_exists'] else 'nein'}")
        if status["cases_count"] == 0:
            warn("Noch keine Entscheidungen heruntergeladen",
                 "beim ersten Start der App wird der Download automatisch gestartet")
        return True
    except Exception as e:
        report(False, "Datenverzeichnis", str(e)[:200],
               "ECJ_DATA_DIR in .env prüfen (Schreibrechte?)")
        return False


def check_chromadb():
    try:
        import chromadb
        client = chromadb.EphemeralClient()
        col = client.get_or_create_collection("diagnose_test")
        col.upsert(ids=["t1"], documents=["Testdokument"],
                   embeddings=[[0.1, 0.2, 0.3]])
        n = col.count()
        client.delete_collection("diagnose_test")
        report(n == 1, "ChromaDB (Vektor-Datenbank)", "in-memory Test erfolgreich")
        return True
    except Exception as e:
        report(False, "ChromaDB (Vektor-Datenbank)", str(e)[:200],
               "pip install --upgrade chromadb; Python 3.11-3.13 verwenden")
        return False


def main():
    print("=" * 70)
    print("EuGH Chatbot - Diagnose")
    print("=" * 70)

    print("\n--- 1. Python & Pakete " + "-" * 45)
    check_python()
    packages_ok = check_packages()

    if not packages_ok:
        print("\nBitte zuerst fehlende Pakete installieren "
              "(pip install -r requirements.txt), dann erneut ausführen.")
        sys.exit(1)

    print("\n--- 2. EUR-Lex (Rechtsprechungs-Daten) " + "-" * 29)
    cases = check_eurlex_sparql()
    check_eurlex_document(cases)

    print("\n--- 3. Anthropic API (Claude) " + "-" * 38)
    check_anthropic()

    print("\n--- 4. Lokale Daten & Index " + "-" * 40)
    check_data_dir()
    check_chromadb()

    print("\n" + "=" * 70)
    failed = [label for ok, label in results if not ok]
    if failed:
        print(f"ERGEBNIS: {len(failed)} Problem(e) gefunden:")
        for label in failed:
            print(f"  - {label}")
        print("\nBitte die Hinweise oben umsetzen und die Diagnose erneut ausführen.")
        sys.exit(1)
    else:
        print("ERGEBNIS: Alle Prüfungen bestanden. Die App sollte funktionieren:")
        print("  streamlit run app.py")
        sys.exit(0)


if __name__ == "__main__":
    main()
