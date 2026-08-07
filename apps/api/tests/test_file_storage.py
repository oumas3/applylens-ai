from pathlib import Path

import pytest

from app.services.file_storage import LocalFileStorage


def test_local_file_storage_round_trip_is_atomic(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "uploads")

    stored = storage.save("document.txt", b"hello ApplyLens")

    assert stored.key == "document.txt"
    assert stored.size_bytes == 15
    assert len(stored.sha256) == 64
    assert storage.read("document.txt") == b"hello ApplyLens"
    assert not list((tmp_path / "uploads").glob("*.tmp"))


def test_local_file_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "uploads")

    with pytest.raises(ValueError):
        storage.save("../outside.txt", b"unsafe")


def test_local_file_storage_delete_is_idempotent(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "uploads")
    storage.save("document.txt", b"hello")

    storage.delete("document.txt")
    storage.delete("document.txt")

    with pytest.raises(FileNotFoundError):
        storage.read("document.txt")
