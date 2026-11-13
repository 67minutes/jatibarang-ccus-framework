"""Hash-addressed local artifact store for imported study inputs (spec §6)."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifact:
    artifact_id: str
    sha256: str
    path: Path


class ImportStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, source: Path) -> StoredArtifact:
        source = Path(source)
        return self.put_bytes(source.name, source.read_bytes(), source=source)

    def put_bytes(
        self,
        name: str,
        payload: bytes,
        *,
        source: Path | None = None,
    ) -> StoredArtifact:
        """Store generated artifact bytes under the same content-addressed contract.

        Imported study inputs use :meth:`put`; generated, compact companions such
        as a memo's spatial-result archive have no source file and use this method.
        The basename restriction prevents callers from escaping the digest folder.
        """

        if not name or Path(name).name != name:
            raise ValueError("artifact name must be a non-empty basename")
        digest = hashlib.sha256(payload).hexdigest().upper()
        artifact_id = digest[:16].lower()
        target_dir = self.root / artifact_id
        target = target_dir / name
        if not target.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            if source is None:
                target.write_bytes(payload)
            else:
                shutil.copy2(source, target)
        return StoredArtifact(artifact_id=artifact_id, sha256=digest, path=target)

    def resolve(self, artifact_id: str) -> Path:
        target_dir = self.root / artifact_id
        files = sorted(p for p in target_dir.iterdir() if p.is_file()) if target_dir.exists() else []
        if not files:
            raise FileNotFoundError(f"imported artifact is missing: {artifact_id}")
        return files[0]
