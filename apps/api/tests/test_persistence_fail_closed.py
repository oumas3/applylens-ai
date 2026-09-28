import pytest

from app.routers import documents, opportunities, profiles, reviews, tasks


class FailingStore:
    def __getattr__(self, name: str):
        if name.startswith("load_"):
            def fail() -> None:
                raise ConnectionError("database unavailable")

            return fail
        raise AttributeError(name)


@pytest.mark.parametrize(
    ("router_module", "loader", "message"),
    [
        (documents, documents._load_documents, "document metadata"),
        (opportunities, opportunities._load_opportunities, "opportunities"),
        (profiles, profiles._load_profiles, "candidate profiles"),
        (reviews, reviews._load_reviews, "reviews"),
        (tasks, tasks._load_tasks, "tasks"),
    ],
)
def test_configured_postgres_load_failure_does_not_become_empty_fallback(
    monkeypatch: pytest.MonkeyPatch,
    router_module,
    loader,
    message: str,
) -> None:
    monkeypatch.setattr(router_module, "application_store", FailingStore())

    with pytest.raises(RuntimeError, match=message):
        loader()
