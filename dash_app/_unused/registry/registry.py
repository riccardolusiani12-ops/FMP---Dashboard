"""
Artifact registry – loads the manifest, queries artifacts, resolves file paths.
Singleton pattern so the manifest is loaded once and reused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.config import MANIFEST_PATH, OUTPUTS_DIR
from src.registry.manifest_schema import ArtifactEntry, Manifest
from src.utils.logging import log


class ArtifactRegistry:
    """Central registry backed by manifest.json."""

    _instance: Optional["ArtifactRegistry"] = None

    def __init__(self) -> None:
        self._manifest: Manifest = Manifest()
        self._loaded = False

    # ── Singleton ──────────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "ArtifactRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Load / Reload ─────────────────────────────────────────────────────
    def load(self, path: Optional[Path] = None) -> None:
        p = path or MANIFEST_PATH
        log.info("Loading manifest from %s", p)
        try:
            self._manifest = Manifest.load(p)
            self._loaded = True
            log.info("Manifest loaded: %d artifacts", len(self._manifest.artifacts))
        except Exception as exc:
            log.error("Failed to load manifest: %s", exc)
            self._manifest = Manifest()
            self._loaded = True  # mark as loaded (empty) to avoid retrying

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Queries ────────────────────────────────────────────────────────────
    def query(
        self,
        season: Optional[str] = None,
        team: Optional[str] = None,
        analysis: Optional[str] = None,
        match_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        fmt: Optional[str] = None,
    ) -> list[ArtifactEntry]:
        """Return artifacts matching all provided filters."""
        self.ensure_loaded()
        results = [
            a
            for a in self._manifest.artifacts
            if a.matches_filter(season, team, analysis, match_id, tags)
        ]
        if fmt:
            results = [a for a in results if a.format == fmt]
        return results

    def get_by_id(self, artifact_id: str) -> Optional[ArtifactEntry]:
        self.ensure_loaded()
        for a in self._manifest.artifacts:
            if a.id == artifact_id:
                return a
        return None

    def resolve_path(self, entry: ArtifactEntry) -> Path:
        """Return the absolute path for an artifact's file."""
        return OUTPUTS_DIR / entry.file

    def file_exists(self, entry: ArtifactEntry) -> bool:
        return self.resolve_path(entry).exists()

    # ── Metadata helpers ──────────────────────────────────────────────────
    def available_seasons(self) -> list[str]:
        self.ensure_loaded()
        return sorted({a.season for a in self._manifest.artifacts})

    def available_teams(self, season: Optional[str] = None) -> list[str]:
        self.ensure_loaded()
        arts = self._manifest.artifacts
        if season:
            arts = [a for a in arts if a.season == season]
        return sorted({a.team for a in arts if a.team})

    def available_matches(
        self, season: Optional[str] = None, team: Optional[str] = None
    ) -> list[dict]:
        """Return list of {match_id, match_label} dicts."""
        self.ensure_loaded()
        seen: dict[str, str] = {}
        for a in self._manifest.artifacts:
            if season and a.season != season:
                continue
            if team and a.team and a.team.lower() != team.lower():
                continue
            if a.match_id and a.match_id not in seen:
                seen[a.match_id] = a.match_label or a.match_id
        return [{"match_id": k, "label": v} for k, v in sorted(seen.items())]

    def available_analyses(self) -> list[str]:
        self.ensure_loaded()
        return sorted({a.analysis for a in self._manifest.artifacts})

    @property
    def manifest(self) -> Manifest:
        self.ensure_loaded()
        return self._manifest

    # ── Diagnostics (for Settings tab) ────────────────────────────────────
    def diagnostics(self) -> dict:
        """Return a diagnostics summary."""
        self.ensure_loaded()
        total = len(self._manifest.artifacts)
        missing = [a for a in self._manifest.artifacts if not self.file_exists(a)]
        formats = {}
        for a in self._manifest.artifacts:
            formats[a.format] = formats.get(a.format, 0) + 1
        return {
            "manifest_path": str(MANIFEST_PATH),
            "manifest_exists": MANIFEST_PATH.exists(),
            "total_artifacts": total,
            "missing_files": len(missing),
            "missing_details": [
                {"id": a.id, "file": a.file} for a in missing[:20]
            ],
            "formats_breakdown": formats,
            "version": self._manifest.version,
            "generated_at": self._manifest.generated_at,
        }
