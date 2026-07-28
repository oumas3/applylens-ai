import pytest

from app.services.retrieval_service import InMemoryRetriever, chunk_text


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


def test_chunk_text_returns_no_chunks_for_empty_text() -> None:
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_keeps_short_paragraphs_together() -> None:
    chunks = chunk_text("First paragraph.\n\nSecond paragraph.", max_chars=100)

    assert len(chunks) == 1
    assert chunks[0].text == "First paragraph.\n\nSecond paragraph."


def test_chunk_text_splits_oversized_paragraphs() -> None:
    chunks = chunk_text("one two three four five six seven", max_chars=12)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 12 for chunk in chunks)


def test_chunk_text_preserves_metadata_on_every_chunk() -> None:
    chunks = chunk_text(
        "one two three four five six",
        source_name="call.pdf",
        page=4,
        max_chars=10,
    )

    assert all(chunk.source_name == "call.pdf" for chunk in chunks)
    assert all(chunk.page == 4 for chunk in chunks)


def test_chunk_text_applies_configurable_overlap_without_exceeding_maximum() -> None:
    chunks = chunk_text(
        "one two three four five six",
        max_chars=15,
        overlap_chars=4,
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 15 for chunk in chunks)
    assert chunks[1].text.startswith(chunks[0].text[-4:].strip())


def test_chunk_text_rejects_invalid_sizes_and_overlap() -> None:
    with pytest.raises(ValueError, match="max_chars must be positive"):
        chunk_text("text", max_chars=0)
    with pytest.raises(ValueError, match="overlap_chars cannot be negative"):
        chunk_text("text", overlap_chars=-1)
    with pytest.raises(ValueError, match="overlap_chars must be smaller"):
        chunk_text("text", max_chars=10, overlap_chars=10)


def test_retriever_returns_relevant_chunks_with_source_metadata() -> None:
    chunks = chunk_text(
        "English proficiency is required.",
        source_name="call.pdf",
        page=3,
    ) + chunk_text("Funding is available.", source_name="call.pdf", page=4)
    retriever = InMemoryRetriever()
    retriever.index(chunks)

    results = retriever.search("English proficiency requirement", top_k=2)

    assert len(results) == 1
    assert results[0].score > 0
    assert results[0].chunk.source_name == "call.pdf"
    assert results[0].chunk.page == 3


def test_retriever_ranks_more_relevant_chunks_first_and_limits_results() -> None:
    chunks = chunk_text("degree requirement and research experience")
    chunks += chunk_text("degree requirement")
    chunks += chunk_text("funding information")
    retriever = InMemoryRetriever()
    retriever.index(chunks)

    results = retriever.search("degree requirement research", top_k=2)

    assert len(results) == 2
    assert results[0].score > results[1].score


def test_retriever_handles_empty_index_and_no_match() -> None:
    retriever = InMemoryRetriever()

    assert retriever.search("degree") == []

    retriever.index(chunk_text("funding information"))
    assert retriever.search("English proficiency") == []


def test_retriever_rejects_non_positive_top_k() -> None:
    with pytest.raises(ValueError, match="top_k must be positive"):
        InMemoryRetriever().search("degree", top_k=0)
