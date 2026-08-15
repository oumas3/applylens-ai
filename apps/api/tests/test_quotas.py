import pytest
from fastapi import HTTPException

from app.config import Settings, get_settings
from app.quotas import enforce_account_quota


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("resource", "setting_name"),
    [
        ("document", "FREE_BETA_DOCUMENT_LIMIT"),
        ("opportunity", "FREE_BETA_OPPORTUNITY_LIMIT"),
        ("review", "FREE_BETA_REVIEW_LIMIT"),
        ("task", "FREE_BETA_TASK_LIMIT"),
    ],
)
def test_account_quota_allows_limit_and_rejects_next_item(
    monkeypatch: pytest.MonkeyPatch,
    resource: str,
    setting_name: str,
) -> None:
    monkeypatch.setenv(setting_name, "2")
    get_settings.cache_clear()

    enforce_account_quota(resource, 2)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as error:
        enforce_account_quota(resource, 3)  # type: ignore[arg-type]

    assert error.value.status_code == 409
    assert error.value.detail == (
        f"Free beta {resource} limit reached (2). "
        f"Delete an existing {resource} before adding another."
    )


def test_quota_settings_reject_non_positive_values() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, free_beta_document_limit=0)
