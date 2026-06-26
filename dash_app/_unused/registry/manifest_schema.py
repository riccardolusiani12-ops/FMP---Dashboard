"""
Manifest JSON schema definition and validation helpers.

Manifest structure (outputs/manifest.json):
{
  "version": "1.0",
  "generated_at": "2026-02-27T12:00:00",
  "artifacts": [
    {
      "id": "unique-artifact-id",
      "season": "2024_2025",
      "competition": "Serie A",
      "analysis": "high_regains",
      "team": "Bologna",              // optional
      "match_id": "9f9a05...",         // optional
      "match_label": "GW1 Bologna–Udinese", // optional
      "title": "High Regains – Bologna Season Overview",
      "description": "...",
      "format": "plotly_json",         // plotly_json | html | png | csv | parquet | table_json
      "file": "2024_2025/high_regains/Bologna/season_overview.json",
      "tags": ["season", "defensive"],
      "created_at": "2026-02-27T12:00:00"
    }
  ]
}
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
import json
from pathlib import Path

SUPPORTED_FORMATS = (
    "plotly_json",
    "html",
    "png",
    "jpg",
    "csv",
    "parquet",
    "table_json",
    "markdown",
)

FormatType = Literal[
    "plotly_json", "html", "png", "jpg", "csv", "parquet", "table_json", "markdown"
]


@dataclass
class ArtifactEntry:
    """Single artifact record in the manifest."""

    id: str
    season: str
    competition: str
    analysis: str
    title: str
    format: FormatType
    file: str  # relative to outputs/

    team: Optional[str] = None
    match_id: Optional[str] = None
    match_label: Optional[str] = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""

    # ── Helpers ────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactEntry":
        # accept only known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    def matches_filter(
        self,
        season: Optional[str] = None,
        team: Optional[str] = None,
        analysis: Optional[str] = None,
        match_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        """Return True if this entry matches all provided filter criteria."""
        if season and self.season != season:
            return False
        if team and self.team and self.team.lower() != team.lower():
            return False
        if analysis and self.analysis != analysis:
            return False
        if match_id and self.match_id != match_id:
            return False
        if tags and not set(tags).issubset(set(self.tags)):
            return False
        return True


@dataclass
class Manifest:
    """Top-level manifest object."""

    version: str = "1.0"
    generated_at: str = ""
    artifacts: list[ArtifactEntry] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "generated_at": self.generated_at,
                "artifacts": [a.to_dict() for a in self.artifacts],
            },
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        data = json.loads(text)
        arts = [ArtifactEntry.from_dict(a) for a in data.get("artifacts", [])]
        return cls(
            version=data.get("version", "1.0"),
            generated_at=data.get("generated_at", ""),
            artifacts=arts,
        )

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.exists():
            return cls()
        return cls.from_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
