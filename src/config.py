"""
ABQ Daily Intelligence System - Configuration

Loads settings from environment variables and config files.
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Load environment variables from project .env
load_dotenv(PROJECT_ROOT / ".env")
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
LOGS_DIR = PROJECT_ROOT / "logs"


class RSSFeed(BaseModel):
    """RSS Feed configuration"""
    name: str
    url: str
    category: str  # research, environment, regulatory, events, general
    enabled: bool = True
    priority: int = 1  # 1=high, 2=medium, 3=low
    language: Optional[str] = None  # fr, en


class EmailConfig(BaseModel):
    """Email delivery configuration"""
    sender_email: str = Field(default_factory=lambda: os.getenv("SENDER_EMAIL", ""))
    sender_name: str = Field(default_factory=lambda: os.getenv("SENDER_NAME", "ABQ Veille Scientifique"))
    recipient_emails: List[str] = Field(default_factory=list)
    subject_prefix: str = "[ABQ Veille]"


class AnalysisConfig(BaseModel):
    """Content analysis configuration"""
    relevancy_keywords: List[str] = Field(default_factory=lambda: [
        # Core biology - French
        "biologie", "biologiste", "sciences de la vie", "recherche scientifique",
        "laboratoire", "microbiologie", "biochimie", "biotechnologie",
        "genetique", "genomique", "proteomique", "bioinformatique",
        # Core biology - English
        "biology", "biologist", "life sciences", "scientific research",
        "laboratory", "microbiology", "biochemistry", "biotechnology",
        "genetics", "genomics", "proteomics", "bioinformatics",
        # Environment - French
        "environnement", "ecologie", "biodiversite", "conservation",
        "changement climatique", "ecosysteme", "faune", "flore",
        "especes menacees", "habitat", "pollution", "developpement durable",
        # Environment - English
        "environment", "ecology", "biodiversity", "conservation",
        "climate change", "ecosystem", "wildlife", "flora",
        "endangered species", "habitat", "pollution", "sustainable development",
        # Quebec specific
        "quebec", "canadien", "canadian", "fleuve saint-laurent",
        "foret boreale", "nord du quebec", "ministere environnement",
        # Academia - French
        "universite", "uqam", "udem", "laval", "mcgill", "sherbrooke",
        "inrs", "frq", "nserc", "crsng", "subvention", "bourse",
        # Academia - English
        "university", "grant", "scholarship", "publication", "peer review"
    ])
    min_relevancy_score: float = 0.015  # Very low threshold to get 8-25 articles after AI filtering
    max_articles_per_category: int = 15  # Increased for better coverage


class AIConfig(BaseModel):
    """AI analysis configuration"""
    enabled: bool = Field(default_factory=lambda: bool(os.getenv("ANTHROPIC_API_KEY")))
    model: str = "claude-sonnet-4-20250514"
    max_articles_to_analyze: int = 50  # Increased for better coverage
    test_max_articles: int = 5
    temperature: float = 0.3


class Config(BaseModel):
    """Main configuration"""
    email: EmailConfig = Field(default_factory=EmailConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    feeds: List[RSSFeed] = Field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from files and environment"""
        config = cls()

        # Load feeds from JSON
        feeds_file = CONFIG_DIR / "feeds.json"
        if feeds_file.exists():
            with open(feeds_file) as f:
                feeds_data = json.load(f)
                config.feeds = [RSSFeed(**feed) for feed in feeds_data.get("feeds", [])]

        # Load recipient emails from environment
        recipients = os.getenv("RECIPIENT_EMAILS", "")
        if recipients:
            config.email.recipient_emails = [e.strip() for e in recipients.split(",")]

        return config


# Global config instance
config = Config.load()
