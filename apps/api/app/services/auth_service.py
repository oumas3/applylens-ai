from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3


SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


class AuthService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
                """
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                bytes.fromhex(salt_hex),
                int(iterations),
            ).hex()
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(candidate, digest_hex)

    def create_user(self, email: str, password: str) -> dict[str, str | bool]:
        user_id = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, email, self._hash_password(password), now),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("An account with this email already exists.") from error
        return {"id": user_id, "email": email, "is_active": True}

    def authenticate(self, email: str, password: str) -> dict[str, str | bool] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, email, password_hash, is_active FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row is None or not row["is_active"] or not self._verify_password(password, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"], "is_active": bool(row["is_active"])}

    def create_session(self, user_id: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    user_id,
                    (now + timedelta(seconds=SESSION_MAX_AGE_SECONDS)).isoformat(),
                    now.isoformat(),
                ),
            )
        return session_id

    def get_user_by_session(self, session_id: str) -> dict[str, str | bool] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email, users.is_active, sessions.expires_at
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            self.delete_session(session_id)
            return None
        return {"id": row["id"], "email": row["email"], "is_active": True}

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
