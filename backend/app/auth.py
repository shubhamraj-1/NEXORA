"""Optional Supabase authentication for the NEXORA API.

When Supabase JWT verification is configured, protected routes require
``Authorization: Bearer <supabase-access-token>``. Tokens are verified locally
with the project JWT secret (HS256) or against the project JWKS endpoint using
only the asymmetric algorithm derived from the selected signing key.
With no verification settings the API stays open for local development.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from .config import settings

_JWKS_CLIENTS: dict[str, PyJWKClient] = {}

# Only asymmetric JOSE algorithms are accepted from a JWKS. Symmetric keys are
# rejected explicitly below so a JWKS can never enable HS256 token forgery.
_JWKS_ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256", "ES384", "ES512", "EdDSA"})


@dataclass(frozen=True)
class AuthUser:
    """The caller identity extracted from a verified Supabase access token."""

    subject: str
    email: str | None
    role: str | None


def _issuer() -> str:
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _jwks_client(url: str) -> PyJWKClient:
    if url not in _JWKS_CLIENTS:
        _JWKS_CLIENTS[url] = PyJWKClient(url)
    return _JWKS_CLIENTS[url]


def _jwks_algorithms(signing_key: PyJWK) -> frozenset[str]:
    """Return the algorithm supported by a JWKS signing key.

    The algorithm is derived from the key type and curve, not from the token
    header. Symmetric keys and JWKs without a signature use are rejected.
    """
    if signing_key.key_type == "oct":
        raise ValueError("Symmetric JWKs are not accepted for access tokens")
    if signing_key.public_key_use not in (None, "sig"):
        raise ValueError("JWK is not marked for signature verification")

    # PyJWT 2.x stores the JWK metadata here; public properties expose kty/use.
    jwk = getattr(signing_key, "_jwk_data", {}) or {}
    kty = signing_key.key_type
    if kty == "RSA":
        derived = "RS256"
    elif kty == "EC":
        derived = {
            "P-256": "ES256",
            "P-384": "ES384",
            "P-521": "ES512",
        }.get(jwk.get("crv"))
        if derived is None:
            raise ValueError("Unsupported EC curve in JWKS")
    elif kty == "OKP":
        derived = "EdDSA" if jwk.get("crv") == "Ed25519" else None
        if derived is None:
            raise ValueError("Unsupported OKP curve in JWKS")
    else:
        raise ValueError(f"Unsupported JWK key type: {kty}")

    declared = getattr(signing_key, "algorithm_name", None)
    if declared and declared != derived:
        raise ValueError("JWK algorithm does not match its key type")
    if derived not in _JWKS_ALLOWED_ALGORITHMS:
        raise ValueError(f"JWK algorithm {derived} is not allowed")
    return frozenset({derived})


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify a Supabase access token and return its claims."""
    issuer = _issuer()
    common = {
        "audience": "authenticated",
        "issuer": issuer,
        "options": {"require": ["exp", "sub"]},
    }

    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            **common,
        )

    jwks_url = settings.supabase_jwks_url
    if not jwks_url and settings.supabase_url:
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if not jwks_url:
        raise RuntimeError("Supabase JWT verification is not configured")

    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    allowed = _jwks_algorithms(signing_key)
    header_alg = jwt.get_unverified_header(token).get("alg")
    if header_alg not in allowed:
        raise ValueError(
            f"Token algorithm {header_alg!r} is not allowed for the signing key"
        )
    return jwt.decode(token, signing_key.key, algorithms=[header_alg], **common)


async def current_user(request: Request) -> AuthUser | None:
    """FastAPI dependency enforcing a Supabase token when auth is configured."""
    if not settings.auth_required:
        return None

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthUser(
        subject=str(subject),
        email=claims.get("email"),
        role=claims.get("role"),
    )
