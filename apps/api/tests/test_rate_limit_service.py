from datetime import datetime, timedelta, timezone

from app.services.rate_limit_service import RATE_LIMIT_RETENTION_SECONDS, RateLimitService


def test_limit_key_is_stable_private_and_action_specific() -> None:
    first = RateLimitService.limit_key("upload", "user@example.com")
    same = RateLimitService.limit_key("upload", "user@example.com")
    other_action = RateLimitService.limit_key("analysis", "user@example.com")

    assert first == same
    assert first != other_action
    assert "user@example.com" not in first


def test_consume_blocks_after_configured_limit(tmp_path) -> None:
    service = RateLimitService(tmp_path / "limits.db")
    key = service.limit_key("upload", "user-1")
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)

    assert service.consume(key, limit=2, window_seconds=60, now=now) is None
    assert service.consume(key, limit=2, window_seconds=60, now=now) is None
    assert service.consume(key, limit=2, window_seconds=60, now=now) == 60


def test_consume_starts_a_fresh_window_after_expiry(tmp_path) -> None:
    service = RateLimitService(tmp_path / "limits.db")
    key = service.limit_key("analysis", "user-1")
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)

    assert service.consume(key, limit=1, window_seconds=60, now=now) is None
    assert service.consume(key, limit=1, window_seconds=60, now=now) == 60
    assert service.consume(
        key,
        limit=1,
        window_seconds=60,
        now=now + timedelta(seconds=61),
    ) is None


def test_cleanup_removes_stale_limit_rows(tmp_path) -> None:
    service = RateLimitService(tmp_path / "limits.db")
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    key = service.limit_key("upload", "user-1")
    service.consume(
        key,
        limit=2,
        window_seconds=60,
        now=now - timedelta(seconds=RATE_LIMIT_RETENTION_SECONDS + 1),
    )

    assert service.cleanup_expired(now=now) == 1
