"""
EuGH Chatbot Configuration Module

Handles configuration for data paths, allowing storage in cloud-synced folders.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv


def parse_themes_file(path: Path) -> dict[str, list[str]]:
    """Parse the user-editable themes file (themen.txt).

    Format: [section] headers, one entry per line, '#' starts a comment.
    Sections: schlagwoerter_de / schlagwoerter_en / schlagwoerter_fr
    (subject keywords) and rechtsakte (CELEX numbers of legal acts).
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections

# override=True: the project's .env file is authoritative. Without it,
# a stale ANTHROPIC_API_KEY stored in the Windows/macOS environment
# (e.g. from an old tutorial setup) silently wins over the .env file,
# and no amount of editing .env fixes a 401.
load_dotenv(override=True)


@dataclass
class Config:
    """
    Configuration for the EuGH Chatbot.

    Data paths can be configured via:
    1. Environment variables (ECJ_DATA_DIR)
    2. .env file
    3. Default: ./data relative to project root

    This allows storing case data in cloud-synced folders (OneDrive, Google Drive)
    for access from multiple devices.
    """

    # Base data directory - can be set to cloud folder
    data_dir: Path = field(default_factory=lambda: Path(
        os.getenv("ECJ_DATA_DIR", str(Path(__file__).parent.parent / "data"))
    ))

    # Subdirectories (relative to data_dir)
    cases_subdir: str = "cases"
    index_subdir: str = "index"

    # Download settings
    initial_year: int = 2018
    update_limit: int = 500  # Max cases to check per incremental update
    download_delay: float = 0.5
    sparql_page_size: int = 1000  # Results per SPARQL page for initial download
    # Cap for the initial download (newest cases first). This bounds the
    # first start to a predictable duration instead of trying to download
    # every ECJ document ever published. Raise via ECJ_MAX_INITIAL_CASES.
    max_initial_cases: int = 1500
    # CELEX document-type codes to download: CJ = ECJ judgment, CO = ECJ order,
    # CC = Advocate General opinion, TJ = General Court judgment
    celex_doc_types: list[str] = field(default_factory=lambda: ["CJ"])
    # EuroVoc SPARQL filtering rarely works for case-law in CELLAR and slows
    # every query down; disabled by default (Stichwort filter is used instead)
    use_eurovoc_filter: bool = False

    # Topic corpora: CELEX numbers of legal acts. For each act, ALL ECJ
    # decisions citing it are downloaded (topic-complete, no keyword
    # filtering, no year/count cap). Configure in themen.txt ([rechtsakte])
    # or via ECJ_TOPIC_CELEX (comma-separated), e.g. "32016R0679" = GDPR.
    topic_celex: list[str] = field(default_factory=list)

    # Path of the loaded themes file (None = built-in defaults active)
    themes_file_loaded: str | None = None

    # Subject area filter: EuroVoc descriptor labels (English)
    # Used for SPARQL EuroVoc filtering (works for legislation, often not for case-law)
    subject_areas: list[str] = field(default_factory=lambda: [
        # Employment / Social Policy / Workers' Rights
        "social policy",
        "employment",
        "employment contract",
        "employment policy",
        "labour law",
        "labour relations",
        "working conditions",
        "worker",
        "workers' rights",
        "posted worker",
        "migrant worker",
        "temporary worker",
        "self-employed worker",
        "social security",
        "free movement of workers",
        # Data Protection / Privacy / AI
        "data protection",
        "protection of privacy",
        "personal data",
        "artificial intelligence",
        # Discrimination / Equal Treatment / Fundamental Rights
        "discrimination",
        "discrimination based on nationality",
        "equal treatment",
        "sex discrimination",
        "racial discrimination",
        "fundamental rights",
    ])

    # Stichwort filter: German keywords matched against the "Stichwort" section
    # in the header of each EuGH decision. A case is included if any of these
    # terms appear in its Stichwort (case-insensitive substring match).
    # This is the primary filter for case-law, since EuroVoc is unreliable there.
    subject_keywords_de: list[str] = field(default_factory=lambda: [
        # Arbeitsrecht / Sozialpolitik / Arbeitnehmerrechte
        "Sozialpolitik",
        "Arbeitnehmer",
        "Arbeitsvertrag",
        "Arbeitszeit",
        "Arbeitsrecht",
        "Arbeitsbedingungen",
        "Beschäftigung",
        "Entlassung",
        "Kündigung",
        "Betriebsübergang",
        "Leiharbeit",
        "Teilzeitarbeit",
        "befristeter Arbeitsvertrag",
        "Entsendung von Arbeitnehmern",
        "entsandte Arbeitnehmer",
        "Wanderarbeitnehmer",
        "Freizügigkeit der Arbeitnehmer",
        "soziale Sicherheit",
        "Sozialversicherung",
        "Elternurlaub",
        "Jahresurlaub",
        "Massenentlassung",
        "Unterrichtung und Anhörung",
        # Datenschutz / Privatsphäre / KI
        "Datenschutz",
        "personenbezogene Daten",
        "Schutz der Privatsphäre",
        "Vorratsdatenspeicherung",
        "Datenübermittlung",
        "künstliche Intelligenz",
        # Diskriminierung / Gleichbehandlung / Grundrechte
        "Diskriminierung",
        "Gleichbehandlung",
        "Gleichstellung",
        "Alter",
        "Geschlecht",
        "Behinderung",
        "Religion",
        "sexuelle Ausrichtung",
        "Grundrechte",
        "Charta der Grundrechte",
    ])

    # English keywords matched against decisions only available in English
    # (recent decisions are often not yet translated to German)
    subject_keywords_en: list[str] = field(default_factory=lambda: [
        # Employment / social policy / workers' rights
        "social policy",
        "worker",
        "employment",
        "employment contract",
        "working time",
        "working conditions",
        "dismissal",
        "collective redundancies",
        "transfer of undertakings",
        "temporary agency work",
        "part-time work",
        "fixed-term work",
        "posting of workers",
        "posted workers",
        "migrant worker",
        "freedom of movement for workers",
        "social security",
        "parental leave",
        "annual leave",
        "information and consultation",
        # Data protection / privacy / AI
        "data protection",
        "personal data",
        "protection of privacy",
        "data retention",
        "data transfer",
        "artificial intelligence",
        # Discrimination / equal treatment / fundamental rights
        "discrimination",
        "equal treatment",
        "equality",
        "age",
        "sex",
        "disability",
        "religion",
        "sexual orientation",
        "fundamental rights",
        "Charter of Fundamental Rights",
    ])

    # French keywords for decisions only available in French
    subject_keywords_fr: list[str] = field(default_factory=lambda: [
        # Emploi / politique sociale / droits des travailleurs
        "politique sociale",
        "travailleur",
        "emploi",
        "contrat de travail",
        "temps de travail",
        "conditions de travail",
        "licenciement",
        "licenciements collectifs",
        "transfert d'entreprise",
        "travail intérimaire",
        "travail à temps partiel",
        "travail à durée déterminée",
        "détachement de travailleurs",
        "libre circulation des travailleurs",
        "sécurité sociale",
        "congé parental",
        "congé annuel",
        "information et consultation",
        # Protection des données / vie privée / IA
        "protection des données",
        "données à caractère personnel",
        "vie privée",
        "conservation des données",
        "transfert de données",
        "intelligence artificielle",
        # Discrimination / égalité de traitement / droits fondamentaux
        "discrimination",
        "égalité de traitement",
        "égalité",
        "âge",
        "sexe",
        "handicap",
        "religion",
        "orientation sexuelle",
        "droits fondamentaux",
        "charte des droits fondamentaux",
    ])

    @property
    def subject_keywords(self) -> dict[str, list[str]]:
        """Keyword lists per language for Stichwort filtering."""
        return {
            "DE": self.subject_keywords_de,
            "EN": self.subject_keywords_en,
            "FR": self.subject_keywords_fr,
        }

    @property
    def active_subject_areas(self) -> list[str] | None:
        """EuroVoc subject areas, or None when EuroVoc filtering is disabled."""
        return self.subject_areas if self.use_eurovoc_filter else None

    # Search settings
    n_results: int = 5
    relevance_threshold: float = 1.5
    enable_live_fallback: bool = True

    # Model settings
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_model: str = "claude-opus-4-8"

    @property
    def cases_dir(self) -> Path:
        """Path to case law JSON files."""
        return self.data_dir / self.cases_subdir

    @property
    def index_dir(self) -> Path:
        """Path to vector index."""
        return self.data_dir / self.index_subdir

    def ensure_directories(self):
        """Create data directories if they don't exist."""
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def is_cloud_storage(self) -> bool:
        """Check if data is stored in a known cloud folder."""
        path_str = str(self.data_dir).lower()
        cloud_indicators = [
            "onedrive",
            "google drive",
            "googledrive",
            "dropbox",
            "icloud"
        ]
        return any(indicator in path_str for indicator in cloud_indicators)

    def get_status(self) -> dict:
        """Get configuration status for display."""
        # Exclude the download checkpoint (bookkeeping, not a case document;
        # see data_acquisition.CHECKPOINT_FILE)
        cases_count = len([
            f for f in self.cases_dir.glob("*.json")
            if f.name != "download_checkpoint.json"
        ]) if self.cases_dir.exists() else 0
        index_exists = self.index_dir.exists() and any(self.index_dir.iterdir()) if self.index_dir.exists() else False

        return {
            "data_dir": str(self.data_dir),
            "cases_dir": str(self.cases_dir),
            "index_dir": str(self.index_dir),
            "cases_count": cases_count,
            "index_exists": index_exists,
            "is_cloud_storage": self.is_cloud_storage()
        }

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from themen.txt and environment variables."""
        config = cls()

        # User-editable themes file: overrides the built-in keyword lists
        # and defines the topic legal acts. Environment variables (below)
        # take precedence over the file.
        themes_path = Path(
            os.getenv("ECJ_THEMES_FILE")
            or Path(__file__).parent.parent / "themen.txt"
        )
        if themes_path.exists():
            try:
                sections = parse_themes_file(themes_path)
                if "schlagwoerter_de" in sections:
                    config.subject_keywords_de = sections["schlagwoerter_de"]
                if "schlagwoerter_en" in sections:
                    config.subject_keywords_en = sections["schlagwoerter_en"]
                if "schlagwoerter_fr" in sections:
                    config.subject_keywords_fr = sections["schlagwoerter_fr"]
                if "rechtsakte" in sections:
                    # First token per line (allows "32016R0679 DSGVO" style)
                    config.topic_celex = [
                        entry.split()[0] for entry in sections["rechtsakte"]
                    ]
                config.themes_file_loaded = str(themes_path)
            except Exception as e:
                print(f"Warnung: Themen-Datei {themes_path} konnte nicht "
                      f"gelesen werden ({e}) - eingebaute Listen aktiv.")

        # Override with environment variables if set
        if os.getenv("ECJ_INITIAL_YEAR"):
            config.initial_year = int(os.getenv("ECJ_INITIAL_YEAR"))

        if os.getenv("ECJ_MAX_INITIAL_CASES"):
            config.max_initial_cases = int(os.getenv("ECJ_MAX_INITIAL_CASES"))

        if os.getenv("ECJ_TOPIC_CELEX"):
            config.topic_celex = [
                c.strip() for c in os.getenv("ECJ_TOPIC_CELEX").split(",")
                if c.strip()
            ]

        if os.getenv("ECJ_EMBEDDING_MODEL"):
            config.embedding_model = os.getenv("ECJ_EMBEDDING_MODEL")

        if os.getenv("ECJ_LLM_MODEL"):
            config.llm_model = os.getenv("ECJ_LLM_MODEL")

        if os.getenv("ECJ_ENABLE_LIVE_FALLBACK"):
            config.enable_live_fallback = os.getenv("ECJ_ENABLE_LIVE_FALLBACK").lower() == "true"

        return config


# Global default config
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_data_dir(path: str | Path):
    """
    Set the data directory at runtime.

    Args:
        path: Path to data directory (can be cloud-synced folder)
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    _config.data_dir = Path(path)
    _config.ensure_directories()
