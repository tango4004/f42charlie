import hashlib
import random
import secrets
import sys

sys.path.insert(0, "/home/f42charlie/app")
from wordlist import WORDS


def generate_passphrase() -> str:
    """4 random words from WORDS."""
    return " ".join(random.choice(WORDS) for _ in range(4))


def generate_session_id() -> str:
    """Legacy soft sid: word + 4 digits (bootstrap / unauth only)."""
    word = random.choice(WORDS)
    digits = str(random.randint(1000, 9999))
    return word + digits


def generate_signed_session_id() -> str:
    """Stable cryptographic session id (BBS-style)."""
    return secrets.token_hex(32)


def hash_passphrase(phrase: str) -> str:
    return hashlib.sha256(phrase.strip().lower().encode()).hexdigest()


def sha256_hex(data: str) -> str:
    return hashlib.sha256((data or "").encode("utf-8")).hexdigest()


def generate_ed25519_keypair():
    """Return (priv_hex, pub_hex) for client session binding.

    Uses Encoding/Format Raw for older cryptography (no private_bytes_raw).
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    pub_hex = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return priv_hex, pub_hex


def sign_payload(priv_hex: str, payload: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    return priv.sign(payload.encode("utf-8")).hex()


def verify_payload(pub_hex: str, payload: str, sig_hex: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(bytes.fromhex(sig_hex), payload.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def build_step_payload(session_id: str, command: str, argument: str, ts: int) -> str:
    """Canonical signed payload for Charlie step.

    argument is hashed so large python-write bodies stay out of the sig string
    but remain bound cryptographically.
    """
    body_h = sha256_hex(argument or "")
    return f"{session_id}:{command or ''}:{body_h}:{int(ts)}"


if __name__ == "__main__":
    phrase = generate_passphrase()
    words = phrase.split()
    assert len(words) == 4
    assert all(4 <= len(w) <= 8 for w in words)
    print(f"passphrase: {phrase}")

    sid = generate_session_id()
    assert sid[-4:].isdigit()
    print(f"session_id: {sid}")

    h1 = hash_passphrase(phrase)
    h2 = hash_passphrase(phrase)
    assert h1 == h2
    assert h1 != hash_passphrase("wrong phrase")
    print(f"hash: {h1[:16]}...")

    priv, pub = generate_ed25519_keypair()
    payload = build_step_payload("abc", "exec", "echo hi", 123)
    sig = sign_payload(priv, payload)
    assert verify_payload(pub, payload, sig)
    assert not verify_payload(pub, payload + "x", sig)
    print("ed25519 OK")
    print("auth OK")
