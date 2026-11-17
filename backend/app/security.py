"""Jetons de session et contrôle des rôles."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header

from .config import settings
from .db import one, transaction
from .errors import DomainError, forbidden


def create_token(user_id: str, purpose: str = "session", hours: int | None = None, **extra) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "purpose": purpose, "iat": now,
               "exp": now + timedelta(hours=hours or settings.jwt_hours), **extra}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, purpose: str = "session") -> dict:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise DomainError(401, "session invalide ou expirée") from exc
    if data.get("purpose") != purpose:
        raise DomainError(401, "jeton non valable pour cette action")
    return data


USER_SQL = """
SELECT id, phone, name, role::text AS role, status::text AS status, is_woman, commune,
       ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng, version_id, valid_from
FROM users_current WHERE id = :id
"""


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise DomainError(401, "connexion requise")
    data = decode_token(authorization[7:])
    with transaction() as conn:
        user = one(conn, USER_SQL, id=data["sub"])
    if not user:
        raise DomainError(401, "utilisateur inconnu")
    if user["status"] in ("disabled", "closed"):
        raise forbidden("compte désactivé")
    return user


def require(*roles: str, active: bool = True):
    """Dépendance FastAPI : l'utilisateur doit avoir l'un des rôles et un compte validé."""

    def dep(user: dict = Depends(current_user)) -> dict:
        if roles and user["role"] not in roles:
            raise forbidden("action réservée au rôle : " + ", ".join(roles))
        if active and user["status"] != "active":
            raise forbidden("compte en attente de validation par l'administration")
        return user

    return dep
