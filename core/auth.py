"""Clawspan Authentication — password-protected startup.

Password is stored as SHA-256 + salt hash (never plaintext) in ~/.clawspan_auth.json.
On first run: user sets a passphrase (voice or text).
On every startup: user must authenticate before accessing Clawspan.

Security:
  - SHA-256 + random salt (16 bytes)
  - Max 3 failed attempts → 60 second lockout
  - Lockout timestamp stored in auth file
  - Works with voice (STT) — passphrases like "iron man mark fifty"

File: ~/.clawspan_auth.json
{
  "salt": "a1b2c3...",
  "hash": "sha256_hex...",
  "created_at": "2026-04-12",
  "failed_attempts": 0,
  "locked_until": null
}
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Literal

AUTH_PATH = os.path.expanduser("~/.clawspan_auth.json")

MAX_ATTEMPTS = 3
LOCKOUT_SECS = 60

CheckResult = Literal["ok", "wrong", "locked", "not_set", "damaged"]


class AuthFileError(Exception):
    """The auth file exists but can't be read, isn't JSON, or has no hash/salt."""


def _normalize(phrase: str) -> str:
    """Normalize a passphrase for comparison — lowercase, strip extra whitespace and punctuation."""
    # Handle spelled-out numbers from voice STT
    number_map = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20",
        "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
        "hundred": "100", "thousand": "1000",
    }
    phrase = phrase.lower().strip()
    # Remove all punctuation (voice STT often adds periods, exclamation marks)
    import string
    phrase = phrase.translate(str.maketrans("", "", string.punctuation))
    # Collapse multiple spaces
    phrase = " ".join(phrase.split())
    # Replace spelled-out numbers
    for word, digit in number_map.items():
        phrase = phrase.replace(word, digit)
    return phrase


def _hash_password(phrase: str, salt: str) -> str:
    """SHA-256 + salt hash."""
    return hashlib.sha256((salt + phrase).encode("utf-8")).hexdigest()


def _load_auth() -> dict | None:
    """Return the stored auth record, or None when no passphrase file exists.

    A file that exists but can't be used raises AuthFileError. It must not be
    read as "no passphrase set", or startup would skip the check and offer to
    set a new passphrase.
    """
    if not os.path.exists(AUTH_PATH):
        return None
    try:
        with open(AUTH_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise AuthFileError(f"{AUTH_PATH}: {e}") from e
    if not isinstance(data, dict) or not data.get("hash") or not data.get("salt"):
        raise AuthFileError(f"{AUTH_PATH}: missing hash or salt")
    return data


def _save_auth(data: dict) -> None:
    """Write the auth file atomically, so a crash mid-write keeps the old one."""
    tmp_path = f"{AUTH_PATH}.tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, AUTH_PATH)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def is_setup() -> bool:
    """Check if a password has been set.

    A damaged auth file still counts as set, so startup asks for the
    passphrase (and fails) instead of running first-time setup.
    """
    try:
        return _load_auth() is not None
    except AuthFileError:
        return True


def check(password: str) -> CheckResult:
    """Verify a password. Returns 'ok', 'wrong', 'locked', 'not_set' or 'damaged'."""
    try:
        auth = _load_auth()
    except AuthFileError as e:
        print(f"[Auth] Auth file is damaged: {e}", flush=True)
        return "damaged"
    if auth is None:
        return "not_set"

    # Check lockout
    locked_until = auth.get("locked_until")
    if locked_until and time.time() < locked_until:
        remaining = int(locked_until - time.time())
        return "locked"

    # Reset lockout if it expired
    if locked_until and time.time() >= locked_until:
        auth["locked_until"] = None
        auth["failed_attempts"] = 0
        _save_auth(auth)

    # Verify
    phrase = _normalize(password)
    stored_hash = auth["hash"]
    salt = auth["salt"]

    if _hash_password(phrase, salt) == stored_hash:
        auth["failed_attempts"] = 0
        _save_auth(auth)
        return "ok"

    # Wrong password
    auth["failed_attempts"] = auth.get("failed_attempts", 0) + 1
    if auth["failed_attempts"] >= MAX_ATTEMPTS:
        auth["locked_until"] = time.time() + LOCKOUT_SECS
        print(f"[Auth] Too many failed attempts. Locked for {LOCKOUT_SECS}s.", flush=True)
    _save_auth(auth)
    return "wrong"


def setup_password(password: str) -> bool:
    """Set a new password. Overwrites if already set."""
    salt = secrets.token_hex(16)
    auth = {
        "salt": salt,
        "hash": _hash_password(_normalize(password), salt),
        "created_at": time.strftime("%Y-%m-%d"),
        "failed_attempts": 0,
        "locked_until": None,
    }
    _save_auth(auth)
    print("[Auth] Password set successfully.", flush=True)
    return True


def change_password(old_password: str, new_password: str) -> bool:
    """Change password — requires old password."""
    result = check(old_password)
    if result != "ok":
        return False

    salt = secrets.token_hex(16)
    auth = _load_auth()
    auth["salt"] = salt
    auth["hash"] = _hash_password(_normalize(new_password), salt)
    auth["failed_attempts"] = 0
    auth["locked_until"] = None
    _save_auth(auth)
    print("[Auth] Password changed.", flush=True)
    return True


def lockout_remaining() -> int:
    """Return seconds remaining in lockout, or 0 if not locked."""
    try:
        auth = _load_auth()
    except AuthFileError:
        return 0
    if auth is None:
        return 0
    locked_until = auth.get("locked_until")
    if locked_until and time.time() < locked_until:
        return int(locked_until - time.time())
    return 0
