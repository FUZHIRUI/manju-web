"""Visual audio assets module."""

from .models import (
    AssetConfig,
    ImageGenerationConfig,
    TTSConfig,
    ChapterAssets,
    AssetState,
)
from .prompt_builders import (
    build_character_prompt,
    build_location_prompt,
    build_fenjing_prompt,
)
from .utils import (
    ensure_dir,
    resolve_character_size_by_attribute,
    read_text,
    safe_get,
)

__all__ = [
    # Models
    "AssetConfig",
    "ImageGenerationConfig",
    "TTSConfig",
    "ChapterAssets",
    "AssetState",
    # Prompt builders
    "build_character_prompt",
    "build_location_prompt",
    "build_fenjing_prompt",
    # Utils
    "ensure_dir",
    "resolve_character_size_by_attribute",
    "read_text",
    "safe_get",
]
