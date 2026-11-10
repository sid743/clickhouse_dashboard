"""
Simple username/password login with two roles: "admin" and "viewer".

Users live in .streamlit/secrets.toml:

    [users.admin]
    role = "admin"
    password_hash = "pbkdf2_sha256$200000$<salt>$<hash>"

To create a hash for a new password, run:   python auth.py
"""

import getpass
import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(test, digest)
    except (ValueError, AttributeError):
        return False


def authenticate(users: dict, username: str, password: str):
    """Return the user's role if the credentials are valid, else None."""
    user = users.get(username.strip()) if username else None
    if not user or not check_password(password, user.get("password_hash", "")):
        return None
    role = user.get("role", "viewer")
    return role if role in ("admin", "viewer") else "viewer"


if __name__ == "__main__":
    pw = getpass.getpass("New password: ")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    print("\nPaste this into .streamlit/secrets.toml as password_hash:\n")
    print(hash_password(pw))
