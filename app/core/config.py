from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application
    APP_NAME: str = "Bulk Certificate Generator"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./certificates.db"

    # Storage – where generated certificate PDFs are saved
    CERTIFICATES_DIR: str = str(Path(__file__).parent.parent.parent / "certificates")

    # Certificate template metadata
    CERTIFICATE_ISSUER: str = "Acme Learning Academy"
    CERTIFICATE_TITLE: str = "Certificate of Completion"


settings = Settings()
