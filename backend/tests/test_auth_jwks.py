"""Security tests for JWKS-based Supabase access-token verification."""

from __future__ import annotations

import base64
import time
from dataclasses import replace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWK

from app import auth as auth_module
from app.config import settings

ISSUER = "https://example.supabase.co/auth/v1"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"


def _b64_int(value: int, size: int = 32) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode()


def _claims() -> dict[str, object]:
    return {
        "sub": "test-user-123",
        "email": "tester@example.com",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
    }


class _FakeJWKSClient:
    def __init__(self, key: PyJWK) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        return self.key


def _use_jwks(monkeypatch: pytest.MonkeyPatch, key: PyJWK) -> None:
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(
            settings,
            supabase_url="https://example.supabase.co",
            supabase_jwks_url=JWKS_URL,
            supabase_jwt_secret="",
        ),
    )
    monkeypatch.setattr(auth_module, "_jwks_client", lambda url: _FakeJWKSClient(key))


def _ec_jwk(private_key: ec.EllipticCurvePrivateKey, kid: str, alg: str = "ES256") -> PyJWK:
    numbers = private_key.public_key().public_numbers()
    return PyJWK.from_dict(
        {
            "kty": "EC",
            "crv": "P-256",
            "use": "sig",
            "kid": kid,
            "alg": alg,
            "x": _b64_int(numbers.x),
            "y": _b64_int(numbers.y),
        }
    )


def test_jwks_accepts_es256_token_signed_by_matching_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    _use_jwks(monkeypatch, _ec_jwk(private_key, "ec-key"))
    token = jwt.encode(
        _claims(), private_key, algorithm="ES256", headers={"kid": "ec-key"}
    )

    claims = auth_module.verify_access_token(token)

    assert claims["sub"] == "test-user-123"
    assert claims["email"] == "tester@example.com"


def test_jwks_rejects_hs256_token_header(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    _use_jwks(monkeypatch, _ec_jwk(private_key, "ec-key"))
    token = jwt.encode(
        _claims(), "forged-secret", algorithm="HS256", headers={"kid": "ec-key"}
    )

    with pytest.raises(ValueError, match="not allowed for the signing key"):
        auth_module.verify_access_token(token)


def test_jwks_rejects_symmetric_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = b"local-test-secret-not-from-production"
    key = PyJWK.from_dict(
        {
            "kty": "oct",
            "use": "sig",
            "alg": "HS256",
            "kid": "oct-key",
            "k": base64.urlsafe_b64encode(secret).rstrip(b"=").decode(),
        }
    )
    _use_jwks(monkeypatch, key)
    token = jwt.encode(_claims(), secret, algorithm="HS256", headers={"kid": "oct-key"})

    with pytest.raises(ValueError, match="Symmetric JWKs are not accepted"):
        auth_module.verify_access_token(token)


def test_jwks_rejects_alg_mismatch_in_key_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    _use_jwks(monkeypatch, _ec_jwk(private_key, "ec-key", alg="ES384"))
    token = jwt.encode(
        _claims(), private_key, algorithm="ES256", headers={"kid": "ec-key"}
    )

    with pytest.raises(ValueError, match="does not match its key type"):
        auth_module.verify_access_token(token)


def test_legacy_secret_mode_still_uses_hs256(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "local-test-only-secret"
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(
            settings,
            supabase_url="https://example.supabase.co",
            supabase_jwks_url=JWKS_URL,
            supabase_jwt_secret=secret,
        ),
    )
    token = jwt.encode(_claims(), secret, algorithm="HS256")

    assert auth_module.verify_access_token(token)["sub"] == "test-user-123"
