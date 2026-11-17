"""Configuration lue dans les variables d'environnement."""
import os
from dataclasses import dataclass, field


DEV_JWT_SECRET = "dev-uniquement-changer-cette-cle-en-production"


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://proteine:proteine@localhost:5432/proteine"
    )
    jwt_secret: str = os.getenv("JWT_SECRET", DEV_JWT_SECRET)
    jwt_hours: int = int(os.getenv("JWT_HOURS", "12"))
    # Prototype : le code SMS est renvoyé dans la réponse au lieu d'être envoyé par SMS.
    dev_otp: bool = os.getenv("DEV_OTP", "1") == "1"
    admin_phones: frozenset = field(
        default_factory=lambda: frozenset(
            p.strip() for p in os.getenv("ADMIN_PHONES", "+2250700000000").split(",") if p.strip()
        )
    )
    cors_origins: tuple = tuple(os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","))


settings = Settings()

# Hors mode prototype, la clé de démonstration permettrait à quiconque de fabriquer un jeton administrateur.
if not settings.dev_otp and settings.jwt_secret == DEV_JWT_SECRET:
    raise RuntimeError("JWT_SECRET doit être défini (32 caractères ou plus) quand DEV_OTP=0")
