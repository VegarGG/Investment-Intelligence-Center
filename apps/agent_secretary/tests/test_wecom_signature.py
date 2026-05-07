"""Workflow 15 §5.5 — WeCom signature verification."""

from __future__ import annotations

from secretary.inbound.wecom_callback import signature, verify


def test_signature_matches_known_input() -> None:
    """Spec: SHA1 of sorted [token, timestamp, nonce, encrypt]."""
    sig = signature("ziwei-token", timestamp="1700000000", nonce="abc", encrypt="enc")
    assert verify(
        token="ziwei-token",
        timestamp="1700000000",
        nonce="abc",
        msg_signature=sig,
        encrypt="enc",
    )


def test_tampered_message_rejected() -> None:
    sig = signature("ziwei-token", timestamp="1700000000", nonce="abc", encrypt="enc")
    assert not verify(
        token="ziwei-token",
        timestamp="1700000000",
        nonce="abc",
        msg_signature=sig,
        encrypt="tampered",
    )


def test_signature_is_order_independent() -> None:
    sig1 = signature("t", timestamp="1", nonce="2", encrypt="3")
    sig2 = signature("t", timestamp="2", nonce="1", encrypt="3")
    # token+1+2+3 sorted == token+2+1+3 sorted, so same digest.
    assert sig1 == sig2
