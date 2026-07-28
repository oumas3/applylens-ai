import pytest

from app.services.retrieval_service import chunk_text


def test_chunk_text_preserves_source_metadata_and_stable_ids() -> None:
    text = "Eligibility requirements.\n\nApplicants must hold a degree."

    first = chunk_text(text, source_name="call.pdf", page=2, max_chars=200)
    second = chunk_text(text, source_name="call.pdf", page=2, max_chars=200)

    assert len(first) == 1
    assert first[0].text == "Eligibility requirements.\n\nApplicants must hold a degree."
    assert first[0].source_name == "call.pdf"
    assert first[0].page == 2
    assert first[0].chunk_id == second[0].chunk_id


def test_chunk_text_splits_long_content_at_word_boundaries() -> None:
    chunks = chunk_text("one two three four five six", max_chars=10)

    assert [chunk.text for chunk in chunks] == [
        "one two",
        "three four",
        "five six",
    ]
    assert [chunk.index for chunk in chunks] == [0, 1, 2]


def test_chunk_text_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError, match="max_chars must be positive"):
        chunk_text("text", max_chars=0)
