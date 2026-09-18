from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm

from app.core import auth as auth_module

ISSUER = "https://clerk.example.test"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
AUDIENCE = "stonegate-api"
AUTHORIZED_PARTY = "https://stonegate.example.test"


@pytest.fixture(autouse=True)
def clear_clerk_jwks_client_cache() -> Iterator[None]:
    auth_module.get_clerk_jwks_client.cache_clear()
    yield
    auth_module.get_clerk_jwks_client.cache_clear()


@pytest.fixture
def clerk_settings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        clerk_issuer=ISSUER,
        clerk_jwks_endpoint=JWKS_URL,
        clerk_audience=AUDIENCE,
        clerk_authorized_parties=[AUTHORIZED_PARTY],
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
    return settings


def key_material(kid: str) -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, jwk


def session_token(
    private_key: rsa.RSAPrivateKey,
    kid: str,
    *,
    subject: str,
    authorized_party: str = AUTHORIZED_PARTY,
) -> str:
    return jwt.encode(
        {
            "sub": subject,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "azp": authorized_party,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def install_jwks_response(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, list[dict[str, Any]]],
) -> list[int]:
    fetch_count = [0]

    def fake_fetch_data(client: PyJWKClient) -> dict[str, list[dict[str, Any]]]:
        fetch_count[0] += 1
        payload = {"keys": list(response["keys"])}
        if client.jwk_set_cache is not None:
            # PyJWT stores this raw mapping internally despite its narrower annotation.
            client.jwk_set_cache.put(payload)  # type: ignore[arg-type]
        return payload

    monkeypatch.setattr(PyJWKClient, "fetch_data", fake_fetch_data)
    return fetch_count


def test_clerk_jwks_is_fetched_once_across_repeated_verifications(
    monkeypatch: pytest.MonkeyPatch,
    clerk_settings: SimpleNamespace,
) -> None:
    private_key, public_jwk = key_material("key-one")
    fetch_count = install_jwks_response(monkeypatch, {"keys": [public_jwk]})
    token = session_token(private_key, "key-one", subject="user_one")

    first = auth_module.verify_clerk_authorization_header(f"Bearer {token}")
    second = auth_module.verify_clerk_authorization_header(f"Bearer {token}")

    assert first.subject == "user_one"
    assert second.subject == "user_one"
    assert fetch_count == [1]
    assert auth_module.get_clerk_jwks_client(JWKS_URL) is auth_module.get_clerk_jwks_client(
        JWKS_URL
    )


def test_clerk_jwks_refreshes_when_a_new_key_id_appears(
    monkeypatch: pytest.MonkeyPatch,
    clerk_settings: SimpleNamespace,
) -> None:
    first_private_key, first_public_jwk = key_material("key-one")
    second_private_key, second_public_jwk = key_material("key-two")
    jwks_response = {"keys": [first_public_jwk]}
    fetch_count = install_jwks_response(monkeypatch, jwks_response)

    first_token = session_token(first_private_key, "key-one", subject="user_one")
    assert auth_module.verify_clerk_authorization_header(
        f"Bearer {first_token}"
    ).subject == "user_one"

    jwks_response["keys"] = [first_public_jwk, second_public_jwk]
    second_token = session_token(second_private_key, "key-two", subject="user_two")
    assert auth_module.verify_clerk_authorization_header(
        f"Bearer {second_token}"
    ).subject == "user_two"
    assert fetch_count == [2]


def test_cached_clerk_jwks_still_rejects_an_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
    clerk_settings: SimpleNamespace,
) -> None:
    _, public_jwk = key_material("key-one")
    wrong_private_key, _ = key_material("unused-key")
    fetch_count = install_jwks_response(monkeypatch, {"keys": [public_jwk]})
    token = session_token(wrong_private_key, "key-one", subject="forged_user")

    with pytest.raises(HTTPException) as exc_info:
        auth_module.verify_clerk_authorization_header(f"Bearer {token}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid Clerk session token."
    assert fetch_count == [1]


def test_cached_clerk_jwks_still_enforces_authorized_party(
    monkeypatch: pytest.MonkeyPatch,
    clerk_settings: SimpleNamespace,
) -> None:
    private_key, public_jwk = key_material("key-one")
    fetch_count = install_jwks_response(monkeypatch, {"keys": [public_jwk]})
    token = session_token(
        private_key,
        "key-one",
        subject="user_one",
        authorized_party="https://untrusted.example.test",
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_module.verify_clerk_authorization_header(f"Bearer {token}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid Clerk authorized party."
    assert fetch_count == [1]
