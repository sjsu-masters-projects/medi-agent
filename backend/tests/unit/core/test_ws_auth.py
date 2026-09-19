"""Where a WebSocket credential is allowed to travel.

Browsers cannot set an `Authorization` header when opening a WebSocket, so the token used
to ride in the query string — and the access log wrote it out in full on every connection.
These tests pin the replacement: the token arrives as a subprotocol, and only the scheme
name is ever echoed back.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import WebSocketException

from app.routers.chat import (
    WS_AUTH_SUBPROTOCOL,
    _extract_ws_token,
    negotiated_subprotocol,
)


def _websocket(**headers: str) -> SimpleNamespace:
    """A stand-in carrying only what the auth helpers read."""
    return SimpleNamespace(headers=headers)


def test_the_token_is_read_from_the_subprotocol_header() -> None:
    websocket = _websocket(**{"sec-websocket-protocol": "bearer, jwt-value"})

    assert _extract_ws_token(websocket) == "jwt-value"  # type: ignore[arg-type]


def test_surrounding_whitespace_is_ignored() -> None:
    """Browsers join offered subprotocols with ', ', so the value arrives padded."""
    websocket = _websocket(**{"sec-websocket-protocol": "bearer ,  jwt-value "})

    assert _extract_ws_token(websocket) == "jwt-value"  # type: ignore[arg-type]


def test_a_jwt_survives_intact() -> None:
    """Dots and base64url padding must not be mangled by the comma split."""
    jwt = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJwMSJ9.c2ln-_=="
    websocket = _websocket(**{"sec-websocket-protocol": f"bearer, {jwt}"})

    assert _extract_ws_token(websocket) == jwt  # type: ignore[arg-type]


def test_the_authorization_header_still_works_for_non_browser_clients() -> None:
    websocket = _websocket(authorization="Bearer jwt-value")

    assert _extract_ws_token(websocket) == "jwt-value"  # type: ignore[arg-type]


def test_a_missing_credential_is_refused() -> None:
    with pytest.raises(WebSocketException):
        _extract_ws_token(_websocket())  # type: ignore[arg-type]


def test_a_scheme_with_no_token_is_refused() -> None:
    """`bearer` alone carries no credential and must not read as authenticated."""
    with pytest.raises(WebSocketException):
        _extract_ws_token(_websocket(**{"sec-websocket-protocol": "bearer"}))  # type: ignore[arg-type]


def test_an_unknown_scheme_is_refused() -> None:
    with pytest.raises(WebSocketException):
        _extract_ws_token(  # type: ignore[arg-type]
            _websocket(**{"sec-websocket-protocol": "graphql-ws, jwt-value"})
        )


def test_only_the_scheme_name_is_echoed_back() -> None:
    """Echoing the token would move the credential into a response header.

    That would put it straight back into the logs this change exists to keep it out of.
    """
    websocket = _websocket(**{"sec-websocket-protocol": "bearer, jwt-value"})

    assert negotiated_subprotocol(websocket) == WS_AUTH_SUBPROTOCOL  # type: ignore[arg-type]
    assert negotiated_subprotocol(websocket) != "jwt-value"  # type: ignore[arg-type]


def test_nothing_is_echoed_when_no_subprotocol_was_offered() -> None:
    """Selecting a subprotocol the client never offered breaks the handshake."""
    assert negotiated_subprotocol(_websocket(authorization="Bearer x")) is None  # type: ignore[arg-type]
