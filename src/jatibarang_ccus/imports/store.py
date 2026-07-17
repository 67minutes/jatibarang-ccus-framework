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
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        artifact_id = digest[:16].lower()
        target_dir = self.root / artifact_id
        target = target_dir / source.name
        if not target.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return StoredArtifact(artifact_id=artifact_id, sha256=digest, path=target)

    def resolve(self, artifact_id: str) -> Path:
        target_dir = self.root / artifact_id
        files = sorted(p for p in target_dir.iterdir() if p.is_file()) if target_dir.exists() else []
        if not files:
            raise FileNotFoundError(f"imported artifact is missing: {artifact_id}")
        return files[0]
