from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import math
from pathlib import Path
import secrets
import sqlite3


SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
DATABASE_CONNECT_TIMEOUT_SECONDS = 3
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$310000$00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_ATTEMPT_RETENTION_SECONDS = LOGIN_ATTEMPT_WINDOW_SECONDS + LOGIN_BLOCK_SECONDS
PASSWORD_RESET_TOKEN_TTL_SECONDS = 60 * 60
PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS = 60


class AuthService:
    def __init__(self, database_path: Path, database_url: str | None = None) -> None:
        self.database_path = database_path
        self.database_url = database_url
        if self.database_url is None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _postgres(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("psycopg is required for PostgreSQL authentication.") from error
        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    external_ai_consent INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    attempt_key TEXT PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL,
                    window_started TEXT NOT NULL,
                    blocked_until TEXT
                );
                CREATE INDEX IF NOT EXISTS login_attempts_window_started_idx
                    ON login_attempts (window_started);
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS password_reset_tokens_user_id_idx
                    ON password_reset_tokens (user_id);
                CREATE INDEX IF NOT EXISTS password_reset_tokens_expires_at_idx
                    ON password_reset_tokens (expires_at);
                """
            )
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "external_ai_consent" not in user_columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN external_ai_consent INTEGER NOT NULL DEFAULT 0"
                )

    @staticmethod
    def _as_utc_datetime(value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _retry_after_seconds(blocked_until: datetime, now: datetime) -> int:
        return max(1, math.ceil((blocked_until - now).total_seconds()))

    @staticmethod
    def login_attempt_key(email: str, client_address: str | None) -> str:
        identity = f"{email.lower()}\0{client_address or 'unknown'}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _login_attempt_row(self, connection, attempt_key: str, *, postgres: bool):
        placeholder = "%s" if postgres else "?"
        return connection.execute(
            f"""
            SELECT failed_attempts, window_started, blocked_until
            FROM login_attempts
            WHERE attempt_key = {placeholder}
            """,
            (attempt_key,),
        ).fetchone()

    @staticmethod
    def _cleanup_login_attempts(
        connection,
        *,
        postgres: bool,
        now: datetime,
    ) -> None:
        placeholder = "%s" if postgres else "?"
        cutoff = now - timedelta(seconds=LOGIN_ATTEMPT_RETENTION_SECONDS)
        connection.execute(
            f"""
            DELETE FROM login_attempts
            WHERE window_started < {placeholder}
              AND (blocked_until IS NULL OR blocked_until < {placeholder})
            """,
            (cutoff.isoformat(), now.isoformat()),
        )

    def login_retry_after(
        self,
        attempt_key: str,
        *,
        now: datetime | None = None,
    ) -> int | None:
        current_time = now or datetime.now(timezone.utc)
        if self.database_url:
            with self._postgres() as connection:
                row = self._login_attempt_row(connection, attempt_key, postgres=True)
        else:
            with self._connect() as connection:
                row = self._login_attempt_row(connection, attempt_key, postgres=False)
        if row is None:
            return None
        blocked_until = self._as_utc_datetime(row["blocked_until"])
        if blocked_until is None or blocked_until <= current_time:
            return None
        return self._retry_after_seconds(blocked_until, current_time)

    def record_failed_login(
        self,
        attempt_key: str,
        *,
        now: datetime | None = None,
    ) -> int | None:
        current_time = now or datetime.now(timezone.utc)
        if self.database_url:
            with self._postgres() as connection:
                self._cleanup_login_attempts(
                    connection,
                    postgres=True,
                    now=current_time,
                )
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (attempt_key,),
                )
                row = self._login_attempt_row(connection, attempt_key, postgres=True)
                values = self._next_login_attempt(row, current_time)
                connection.execute(
                    """
                    INSERT INTO login_attempts (
                        attempt_key, failed_attempts, window_started, blocked_until
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (attempt_key) DO UPDATE SET
                        failed_attempts = EXCLUDED.failed_attempts,
                        window_started = EXCLUDED.window_started,
                        blocked_until = EXCLUDED.blocked_until
                    """,
                    (attempt_key, *values),
                )
        else:
            with self._connect() as connection:
                self._cleanup_login_attempts(
                    connection,
                    postgres=False,
                    now=current_time,
                )
                row = self._login_attempt_row(connection, attempt_key, postgres=False)
                values = self._next_login_attempt(row, current_time)
                connection.execute(
                    """
                    INSERT INTO login_attempts (
                        attempt_key, failed_attempts, window_started, blocked_until
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(attempt_key) DO UPDATE SET
                        failed_attempts = excluded.failed_attempts,
                        window_started = excluded.window_started,
                        blocked_until = excluded.blocked_until
                    """,
                    (attempt_key, *values),
                )
        blocked_until = self._as_utc_datetime(values[2])
        if blocked_until is None:
            return None
        return self._retry_after_seconds(blocked_until, current_time)

    @classmethod
    def _next_login_attempt(
        cls,
        row,
        now: datetime,
    ) -> tuple[int, str, str | None]:
        window_started = (
            cls._as_utc_datetime(row["window_started"])
            if row is not None
            else None
        )
        blocked_until = (
            cls._as_utc_datetime(row["blocked_until"])
            if row is not None
            else None
        )
        if blocked_until is not None and blocked_until > now:
            return int(row["failed_attempts"]), window_started.isoformat(), blocked_until.isoformat()
        window_expired = (
            window_started is None
            or window_started + timedelta(seconds=LOGIN_ATTEMPT_WINDOW_SECONDS) <= now
        )
        failed_attempts = 1 if window_expired else int(row["failed_attempts"]) + 1
        active_window_start = now if window_expired else window_started
        next_blocked_until = (
            now + timedelta(seconds=LOGIN_BLOCK_SECONDS)
            if failed_attempts >= LOGIN_ATTEMPT_LIMIT
            else None
        )
        return (
            failed_attempts,
            active_window_start.isoformat(),
            next_blocked_until.isoformat() if next_blocked_until else None,
        )

    def clear_login_failures(self, attempt_key: str) -> None:
        if self.database_url:
            with self._postgres() as connection:
                connection.execute(
                    "DELETE FROM login_attempts WHERE attempt_key = %s",
                    (attempt_key,),
                )
        else:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM login_attempts WHERE attempt_key = ?",
                    (attempt_key,),
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
            if self.database_url:
                with self._postgres() as connection:
                    connection.execute(
                        "INSERT INTO users (id, email, password_hash, created_at) VALUES (%s, %s, %s, %s)",
                        (user_id, email, self._hash_password(password), now),
                    )
            else:
                with self._connect() as connection:
                    connection.execute(
                        "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                        (user_id, email, self._hash_password(password), now),
                    )
        except Exception as error:
            if not isinstance(error, sqlite3.IntegrityError) and "duplicate key" not in str(error).lower():
                raise
            raise ValueError("An account with this email already exists.") from error
        return {
            "id": user_id,
            "email": email,
            "is_active": True,
            "external_ai_consent": False,
        }

    def authenticate(self, email: str, password: str) -> dict[str, str | bool] | None:
        if self.database_url:
            with self._postgres() as connection:
                row = connection.execute(
                    """
                    SELECT id, email, password_hash, is_active, external_ai_consent
                    FROM users WHERE email = %s
                    """,
                    (email,),
                ).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT id, email, password_hash, is_active, external_ai_consent
                    FROM users WHERE email = ?
                    """,
                    (email,),
                ).fetchone()
        encoded_password = row["password_hash"] if row is not None else DUMMY_PASSWORD_HASH
        password_is_valid = self._verify_password(password, encoded_password)
        if row is None or not row["is_active"] or not password_is_valid:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "is_active": bool(row["is_active"]),
            "external_ai_consent": bool(row["external_ai_consent"]),
        }

    def create_session(self, user_id: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        values = (
            session_id,
            user_id,
            (now + timedelta(seconds=SESSION_MAX_AGE_SECONDS)).isoformat(),
            now.isoformat(),
        )
        if self.database_url:
            with self._postgres() as connection:
                connection.execute(
                    "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (%s, %s, %s, %s)",
                    values,
                )
        else:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                    values,
                )
        return session_id

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        if self.database_url:
            with self._postgres() as connection:
                row = connection.execute(
                    "SELECT password_hash FROM users WHERE id = %s AND is_active = TRUE",
                    (user_id,),
                ).fetchone()
                if row is None or not self._verify_password(
                    current_password,
                    row["password_hash"],
                ):
                    return False
                connection.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (self._hash_password(new_password), user_id),
                )
                connection.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        else:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
                    (user_id,),
                ).fetchone()
                if row is None or not self._verify_password(
                    current_password,
                    row["password_hash"],
                ):
                    return False
                connection.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (self._hash_password(new_password), user_id),
                )
                connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return True

    @staticmethod
    def _hash_reset_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_password_reset_token(
        self,
        email: str,
        *,
        now: datetime | None = None,
    ) -> str | None:
        current_time = now or datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_reset_token(token)
        expires_at = current_time + timedelta(seconds=PASSWORD_RESET_TOKEN_TTL_SECONDS)
        cooldown_started = current_time - timedelta(
            seconds=PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS
        )

        if self.database_url:
            with self._postgres() as connection:
                user = connection.execute(
                    "SELECT id FROM users WHERE email = %s AND is_active = TRUE FOR UPDATE",
                    (email,),
                ).fetchone()
                if user is None:
                    return None
                recent = connection.execute(
                    """
                    SELECT 1 FROM password_reset_tokens
                    WHERE user_id = %s AND created_at > %s
                    """,
                    (user["id"], cooldown_started.isoformat()),
                ).fetchone()
                if recent is not None:
                    return None
                connection.execute(
                    "DELETE FROM password_reset_tokens WHERE expires_at <= %s OR user_id = %s",
                    (current_time.isoformat(), user["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO password_reset_tokens (
                        token_hash, user_id, expires_at, created_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        token_hash,
                        user["id"],
                        expires_at.isoformat(),
                        current_time.isoformat(),
                    ),
                )
        else:
            with self._connect() as connection:
                user = connection.execute(
                    "SELECT id FROM users WHERE email = ? AND is_active = 1",
                    (email,),
                ).fetchone()
                if user is None:
                    return None
                connection.execute("BEGIN IMMEDIATE")
                user = connection.execute(
                    "SELECT id FROM users WHERE email = ? AND is_active = 1",
                    (email,),
                ).fetchone()
                if user is None:
                    return None
                recent = connection.execute(
                    """
                    SELECT 1 FROM password_reset_tokens
                    WHERE user_id = ? AND created_at > ?
                    """,
                    (user["id"], cooldown_started.isoformat()),
                ).fetchone()
                if recent is not None:
                    return None
                connection.execute(
                    "DELETE FROM password_reset_tokens WHERE expires_at <= ? OR user_id = ?",
                    (current_time.isoformat(), user["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO password_reset_tokens (
                        token_hash, user_id, expires_at, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        token_hash,
                        user["id"],
                        expires_at.isoformat(),
                        current_time.isoformat(),
                    ),
                )
        return token

    def reset_password(
        self,
        token: str,
        new_password: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(timezone.utc)
        token_hash = self._hash_reset_token(token)

        if self.database_url:
            with self._postgres() as connection:
                row = connection.execute(
                    """
                    SELECT password_reset_tokens.user_id,
                           password_reset_tokens.expires_at
                    FROM password_reset_tokens
                    JOIN users ON users.id = password_reset_tokens.user_id
                    WHERE password_reset_tokens.token_hash = %s
                      AND users.is_active = TRUE
                    FOR UPDATE
                    """,
                    (token_hash,),
                ).fetchone()
                if row is None:
                    return False
                expires_at = self._as_utc_datetime(row["expires_at"])
                if expires_at is None or expires_at <= current_time:
                    connection.execute(
                        "DELETE FROM password_reset_tokens WHERE token_hash = %s",
                        (token_hash,),
                    )
                    return False
                connection.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (self._hash_password(new_password), row["user_id"]),
                )
                connection.execute(
                    "DELETE FROM sessions WHERE user_id = %s",
                    (row["user_id"],),
                )
                connection.execute(
                    "DELETE FROM password_reset_tokens WHERE user_id = %s",
                    (row["user_id"],),
                )
        else:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT password_reset_tokens.user_id,
                           password_reset_tokens.expires_at
                    FROM password_reset_tokens
                    JOIN users ON users.id = password_reset_tokens.user_id
                    WHERE password_reset_tokens.token_hash = ?
                      AND users.is_active = 1
                    """,
                    (token_hash,),
                ).fetchone()
                if row is None:
                    return False
                expires_at = self._as_utc_datetime(row["expires_at"])
                if expires_at is None or expires_at <= current_time:
                    connection.execute(
                        "DELETE FROM password_reset_tokens WHERE token_hash = ?",
                        (token_hash,),
                    )
                    return False
                deleted = connection.execute(
                    "DELETE FROM password_reset_tokens WHERE token_hash = ?",
                    (token_hash,),
                )
                if deleted.rowcount != 1:
                    return False
                connection.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (self._hash_password(new_password), row["user_id"]),
                )
                connection.execute(
                    "DELETE FROM sessions WHERE user_id = ?",
                    (row["user_id"],),
                )
                connection.execute(
                    "DELETE FROM password_reset_tokens WHERE user_id = ?",
                    (row["user_id"],),
                )
        return True

    def get_account(self, user_id: str) -> dict[str, object] | None:
        """Return the portable, non-secret fields stored for one account."""
        query = """
            SELECT id, email, is_active, external_ai_consent, created_at
            FROM users
            WHERE id = ?
        """
        if self.database_url:
            with self._postgres() as connection:
                row = connection.execute(
                    query.replace("?", "%s"),
                    (user_id,),
                ).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(query, (user_id,)).fetchone()
        if row is None:
            return None
        created_at = row["created_at"]
        return {
            "id": row["id"],
            "email": row["email"],
            "is_active": bool(row["is_active"]),
            "external_ai_consent": bool(row["external_ai_consent"]),
            "created_at": (
                created_at.isoformat()
                if isinstance(created_at, datetime)
                else str(created_at)
            ),
        }

    def set_external_ai_consent(self, user_id: str, consent: bool) -> bool:
        value = consent if self.database_url else int(consent)
        if self.database_url:
            with self._postgres() as connection:
                cursor = connection.execute(
                    "UPDATE users SET external_ai_consent = %s WHERE id = %s AND is_active = TRUE",
                    (value, user_id),
                )
        else:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET external_ai_consent = ? WHERE id = ? AND is_active = 1",
                    (value, user_id),
                )
        return cursor.rowcount == 1

    def verify_user_password(self, user_id: str, password: str) -> bool:
        if self.database_url:
            with self._postgres() as connection:
                row = connection.execute(
                    "SELECT password_hash FROM users WHERE id = %s AND is_active = TRUE",
                    (user_id,),
                ).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
                    (user_id,),
                ).fetchone()
        encoded = row["password_hash"] if row is not None else DUMMY_PASSWORD_HASH
        return row is not None and self._verify_password(password, encoded)

    def delete_user(self, user_id: str) -> bool:
        """Delete an account and PostgreSQL vector rows owned through opportunities."""
        if self.database_url:
            with self._postgres() as connection:
                connection.execute(
                    """
                    DELETE FROM opportunity_chunks
                    WHERE opportunity_id IN (
                        SELECT id FROM opportunities WHERE user_id = %s
                    )
                    """,
                    (user_id,),
                )
                cursor = connection.execute(
                    "DELETE FROM users WHERE id = %s",
                    (user_id,),
                )
        else:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM users WHERE id = ?",
                    (user_id,),
                )
        return cursor.rowcount == 1

    def get_user_by_session(self, session_id: str) -> dict[str, str | bool] | None:
        query = """
                SELECT users.id, users.email, users.is_active,
                       users.external_ai_consent, sessions.expires_at
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?
                """
        if self.database_url:
            query = query.replace("?", "%s")
            with self._postgres() as connection:
                row = connection.execute(query, (session_id,)).fetchone()
        else:
            with self._connect() as connection:
                row = connection.execute(
                """
                SELECT users.id, users.email, users.is_active,
                       users.external_ai_consent, sessions.expires_at
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            self.delete_session(session_id)
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "is_active": True,
            "external_ai_consent": bool(row["external_ai_consent"]),
        }

    def delete_session(self, session_id: str) -> None:
        if self.database_url:
            with self._postgres() as connection:
                connection.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        else:
            with self._connect() as connection:
                connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
