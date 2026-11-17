"""Erreurs métier et traduction des erreurs PostgreSQL en réponses HTTP."""
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError


class DomainError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def conflict(msg: str) -> DomainError:
    return DomainError(409, msg)


def not_found(msg: str = "introuvable") -> DomainError:
    return DomainError(404, msg)


def forbidden(msg: str = "accès refusé") -> DomainError:
    return DomainError(403, msg)


# Codes SQLSTATE -> statut HTTP. P0001/P0002 viennent de nos déclencheurs.
_SQLSTATE = {
    "P0001": 409,  # garde-fou (suppression, historique, paiement figé)
    "P0002": 409,  # transition de statut interdite
    "23505": 409,  # unicité
    "23P01": 409,  # chevauchement de périodes SCD2
    "23514": 422,  # contrainte CHECK
    "23503": 422,  # clé étrangère
    "40001": 409,  # conflit de sérialisation après relances
}


async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


async def db_error_handler(_: Request, exc: DBAPIError):
    code = getattr(exc.orig, "sqlstate", None)
    status = _SQLSTATE.get(code, 500)
    diag = getattr(exc.orig, "diag", None)
    # Seuls nos garde-fous (statut connu) renvoient le texte de la base ; une erreur inattendue reste opaque.
    message = (getattr(diag, "message_primary", None) if status != 500 else None) or "erreur de base de données"
    if code == "23514":
        message = f"donnée refusée par la base ({getattr(diag, 'constraint_name', '')})"
    return JSONResponse(status_code=status, content={"detail": message, "sqlstate": code})
