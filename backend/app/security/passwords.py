import base64
import hashlib
import hmac
import os


_ALGORITHM = "sha256"
_ITERATIONS = 310_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password is required")

    salt = os.urandom(_SALT_BYTES)

    derived_key = hashlib.pbkdf2_hmac(
        _ALGORITHM,
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )

    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    hash_text = base64.urlsafe_b64encode(derived_key).decode("ascii")

    return (
        f"pbkdf2_{_ALGORITHM}"
        f"${_ITERATIONS}"
        f"${salt_text}"
        f"${hash_text}"
    )


def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    try:
        scheme, iterations_text, salt_text, hash_text = (
            stored_hash.split("$", 3)
        )

        if scheme != f"pbkdf2_{_ALGORITHM}":
            return False

        iterations = int(iterations_text)

        salt = base64.urlsafe_b64decode(
            salt_text.encode("ascii")
        )

        expected_hash = base64.urlsafe_b64decode(
            hash_text.encode("ascii")
        )

    except (ValueError, TypeError):
        return False

    actual_hash = hashlib.pbkdf2_hmac(
        _ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return hmac.compare_digest(
        actual_hash,
        expected_hash,
    )