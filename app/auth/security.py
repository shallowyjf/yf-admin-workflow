"""Password and opaque-session-token primitives."""

import base64
import hashlib
import hmac
import secrets


class PasswordHasher:
    algorithm = "scrypt"
    n = 2**14
    r = 8
    p = 1
    salt_bytes = 16
    key_bytes = 32

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        salt = secrets.token_bytes(self.salt_bytes)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
            dklen=self.key_bytes,
        )
        return "$".join(
            (
                self.algorithm,
                str(self.n),
                str(self.r),
                str(self.p),
                self._encode(salt),
                self._encode(derived),
            )
        )

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded_hash.split("$", 5)
            if algorithm != self.algorithm:
                return False
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=self._decode(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(self._decode(expected)),
            )
            return hmac.compare_digest(derived, self._decode(expected))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
