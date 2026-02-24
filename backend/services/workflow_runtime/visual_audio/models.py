"""Data models for visual audio assets module."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class AssetState(Enum):
    """Asset processing state."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AssetConfig:
    """Base configuration for asset processing."""
    project_name: str = ""
    output_dir: Path = field(default_factory=Path)
    assets_dir: Path = field(default_factory=Path)
    bucket: str = ""
    tos_prefix: str = ""

    def __post_init__(self):
        """Ensure paths are Path objects."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.assets_dir, str):
            self.assets_dir = Path(self.assets_dir)


@dataclass
class ImageGenerationConfig:
    """Configuration for image generation."""
    concurrency: int = 5
    timeout: int = 300
    retry_count: int = 3
    size_override: Optional[str] = None
    on_progress: Optional[Callable[[int, int], None]] = None
    on_complete: Optional[Callable[[Path], None]] = None


@dataclass
class TTSConfig:
    """Configuration for TTS generation."""
    concurrency: int = 3
    speaker: str = "zh-CN-XiaoxiaoNeural"
    speed: float = 1.0
    pitch: float = 1.0
    on_progress: Optional[Callable[[int, int], None]] = None


@dataclass
class ChapterAssets:
    """Assets for a single chapter."""
    chapter_name: str = ""
    storyboard_path: Optional[Path] = None
    fenjing_images_dir: Optional[Path] = None
    candidates_dir: Optional[Path] = None
    prompts_path: Optional[Path] = None
    tts_dir: Optional[Path] = None
    state: AssetState = AssetState.PENDING

    # Runtime data
    storyboard_items: List[Dict[str, Any]] = field(default_factory=list)
    generated_images: List[Path] = field(default_factory=list)
    generated_tts: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ProcessingResult:
    """Result of asset processing."""
    success: bool = False
    message: str = ""
    output_paths: List[Path] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: Optional[str] = None
