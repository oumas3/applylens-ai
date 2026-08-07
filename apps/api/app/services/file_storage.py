"""Storage abstraction for uploaded document bytes."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class StoredFile:
    key: str
    size_bytes: int
    sha256: str


class FileStorage(Protocol):
    def save(self, key: str, content: bytes) -> StoredFile: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalFileStorage:
    """Atomic local storage used by development and single-node deployments."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate.parent != self.root or candidate == self.root:
            raise ValueError("Storage keys must name a file directly under the storage root")
        return candidate

    def save(self, key: str, content: bytes) -> StoredFile:
        destination = self._path(key)
        temporary = self.root / f".{destination.name}.{uuid4().hex}.tmp"
        digest = hashlib.sha256(content).hexdigest()

        try:
            with temporary.open("wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

        return StoredFile(key=key, size_bytes=len(content), sha256=digest)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
