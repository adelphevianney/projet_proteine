"""Comptes : connexion par code SMS, inscription, profil historisé (SCD2), administration."""
from __future__ import annotations

import hashlib
import secrets

from ..config import settings
from ..db import one, rows, run, transaction
from ..errors import DomainError, conflict, not_found
from ..repositories import scd2
from ..security import USER_SQL, create_token, decode_token
from .common import POINT, notify

SELF_SIGNUP_ROLES = {"producer", "farm", "breeder", "collector"}
NEEDS_VALIDATION = {"farm", "collector"}


def _hash(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}:{settings.jwt_secret}".encode()).hexdigest()


def request_otp(phone: str) -> dict:
    code = f"{secrets.randbelow(1_000_000):06d}"
    with transaction() as conn:
        recent = one(conn, """SELECT count(*) AS n FROM otp_codes
                              WHERE phone = :p AND created_at > now() - interval '10 minutes'""", p=phone)
        if recent["n"] >= 5:
            raise DomainError(429, "trop de demandes de code, réessayez dans quelques minutes")
        run(conn, """INSERT INTO otp_codes (phone, code_hash, expires_at)
                     VALUES (:p, :h, now() + interval '5 minutes')""", p=phone, h=_hash(phone, code))
    out = {"sent": True}
    if settings.dev_otp:
        out["dev_code"] = code  # prototype : pas de fournisseur SMS
    return out


def verify_otp(phone: str, code: str) -> dict:
    error = None
    with transaction() as conn:
        otp = one(conn, """SELECT id, code_hash, attempts, expires_at < now() AS expired, used_at
                           FROM otp_codes WHERE phone = :p ORDER BY created_at DESC LIMIT 1 FOR UPDATE""", p=phone)
        if not otp or otp["used_at"] or otp["expired"]:
            error = "code expiré, demandez-en un nouveau"
        elif otp["attempts"] >= 5:
            error = "trop d'essais, demandez un nouveau code"
        elif not secrets.compare_digest(otp["code_hash"], _hash(phone, code)):
            # L'essai raté est enregistré (la transaction est validée avant l'erreur).
            run(conn, "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = :c", c=otp["id"])
            error = "code incorrect"
        else:
            run(conn, "UPDATE otp_codes SET used_at = now() WHERE id = :c", c=otp["id"])
        user = one(conn, "SELECT id FROM users WHERE phone = :p", p=phone)
    if error:
        raise DomainError(401, error)
    if user:
        return {"token": create_token(user["id"]), "needs_signup": False}
    return {"needs_signup": True, "signup_token": create_token(phone, purpose="signup", hours=1)}


def signup(signup_token: str, name: str, role: str, lat: float | None, lng: float | None,
           commune: str | None, is_woman: bool) -> dict:
    phone = decode_token(signup_token, purpose="signup")["sub"]
    if phone in settings.admin_phones:
        role, status = "admin", "active"
    elif role not in SELF_SIGNUP_ROLES:
        raise DomainError(422, "rôle inconnu")
    else:
        status = "pending" if role in NEEDS_VALIDATION else "active"
    with transaction() as conn:
        if one(conn, "SELECT 1 AS x FROM users WHERE phone = :p", p=phone):
            raise conflict("ce numéro a déjà un compte")
        user_id = one(conn, "INSERT INTO users (phone) VALUES (:p) RETURNING id", p=phone)["id"]
        run(conn, "SELECT set_config('app.actor_id', :a, true)", a=str(user_id))
        loc = POINT if lat is not None and lng is not None else "NULL"
        run(conn, f"""INSERT INTO user_versions (user_id, name, role, status, is_woman, commune, location)
                      VALUES (:u, :n, :r, :s, :w, :c, {loc})""",
            u=user_id, n=name, r=role, s=status, w=is_woman, c=commune, lat=lat, lng=lng)
        if status == "pending":
            for admin in rows(conn, "SELECT id FROM users_current WHERE role = 'admin' AND status = 'active'"):
                notify(conn, admin["id"], "validation", f"Nouveau compte à valider : {name} ({role})")
    return {"token": create_token(user_id), "status": status, "role": role}


def update_profile(user: dict, changes: dict) -> dict:
    """Changement de nom, commune ou position : nouvelle version SCD2, l'ancienne est conservée."""
    geo = None
    if changes.get("lat") is not None and changes.get("lng") is not None:
        geo = {"location": (changes.pop("lat"), changes.pop("lng"))}
    changes = {k: v for k, v in changes.items() if k in ("name", "commune", "is_woman") and v is not None}
    if not changes and not geo:
        raise DomainError(422, "rien à modifier")
    with transaction(user["id"]) as conn:
        scd2.change(conn, "user_versions", user["id"], changes, geo)
        return one(conn, USER_SQL, id=user["id"])


def profile_history(user_id) -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT version_id, name, role::text AS role, status::text AS status, commune,
                                    ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng,
                                    valid_from, valid_to, is_current
                             FROM user_versions WHERE user_id = :u ORDER BY valid_from""", u=user_id)


def list_users(status: str | None = None, role: str | None = None) -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT id, phone, name, role::text AS role, status::text AS status, commune, valid_from
                             FROM users_current
                             WHERE (CAST(:s AS text) IS NULL OR status::text = :s)
                               AND (CAST(:r AS text) IS NULL OR role::text = :r)
                             ORDER BY valid_from DESC""", s=status, r=role)


def set_status(admin: dict, user_id, status: str) -> dict:
    with transaction(admin["id"]) as conn:
        cur = scd2.current(conn, "user_versions", user_id, lock=True)
        if cur["role"] == "admin":
            raise conflict("un administrateur ne se modifie pas ici")
        if cur["status"] == status:
            return one(conn, USER_SQL, id=user_id)
        scd2.change(conn, "user_versions", user_id, {"status": status})
        msg = {"active": "Votre compte a été validé.", "disabled": "Votre compte a été désactivé."}[status]
        notify(conn, user_id, "compte", msg)
        user = one(conn, USER_SQL, id=user_id)
    if not user:
        raise not_found()
    return user


def list_collectors() -> list[dict]:
    with transaction() as conn:
        return rows(conn, """SELECT id, name, commune FROM users_current
                             WHERE role = 'collector' AND status = 'active' ORDER BY name""")
