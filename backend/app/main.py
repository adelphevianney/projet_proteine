"""Point d'entrée de l'API Protéine circulaire."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError

from .api.routes import router
from .config import settings
from .errors import DomainError, db_error_handler, domain_error_handler

app = FastAPI(
    title="Protéine circulaire",
    version="0.1.0",
    description="Mise en relation producteurs de déchets, fermes à larves, éleveurs et collecteurs.",
)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(DBAPIError, db_error_handler)
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
