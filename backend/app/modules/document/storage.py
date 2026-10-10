import hashlib
import os
from pathlib import Path
import secrets
from uuid import UUID


class ArtifactStorageError(OSError):
    pass


class ArtifactConflict(ArtifactStorageError):
    pass


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def write_immutable(
        self,
        document_id: UUID,
        version_id: UUID,
        filename: str,
        content: bytes,
        expected_hash: str,
    ) -> Path:
        if filename not in {"letter.md", "letter.pdf"}:
            raise ArtifactStorageError("Unsupported artifact name")
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ArtifactStorageError("Artifact integrity check failed")

        root = self._root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise ArtifactStorageError("Artifact root cannot be a symbolic link")
        os.chmod(root, 0o700)
        root = root.resolve(strict=True)

        document_directory = root / str(document_id)
        document_directory.mkdir(mode=0o700, exist_ok=True)
        if document_directory.is_symlink():
            raise ArtifactStorageError("Artifact directory cannot be a symbolic link")
        os.chmod(document_directory, 0o700)
        version_directory = document_directory / str(version_id)
        version_directory.mkdir(mode=0o700, exist_ok=True)
        if version_directory.is_symlink():
            raise ArtifactStorageError("Artifact directory cannot be a symbolic link")
        os.chmod(version_directory, 0o700)

        target = version_directory / filename
        if target.is_symlink():
            raise ArtifactStorageError("Artifact cannot be a symbolic link")
        if target.exists():
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != expected_hash:
                raise ArtifactConflict("Immutable artifact already has different bytes")
            return target

        temporary = version_directory / f".{filename}.{secrets.token_hex(12)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                existing = target.read_bytes()
                if hashlib.sha256(existing).hexdigest() != expected_hash:
                    raise ArtifactConflict(
                        "Immutable artifact already has different bytes"
                    )
        finally:
            temporary.unlink(missing_ok=True)
        directory_descriptor = os.open(version_directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return target

    def read_verified(
        self,
        document_id: UUID,
        version_id: UUID,
        filename: str,
        expected_hash: str,
    ) -> bytes:
        if filename not in {"letter.md", "letter.pdf"}:
            raise ArtifactStorageError("Unsupported artifact name")
        root = self._root
        document_directory = root / str(document_id)
        version_directory = document_directory / str(version_id)
        if root.is_symlink() or not root.is_dir():
            raise FileNotFoundError(filename)
        if document_directory.is_symlink() or not document_directory.is_dir():
            raise FileNotFoundError(filename)
        if version_directory.is_symlink() or not version_directory.is_dir():
            raise FileNotFoundError(filename)
        path = version_directory / filename
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(filename)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ArtifactStorageError("Stored artifact integrity check failed")
        return content
