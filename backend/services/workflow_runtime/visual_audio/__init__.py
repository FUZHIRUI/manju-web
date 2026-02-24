"""Visual audio assets module."""

from .models import (
    AssetConfig,
    ImageGenerationConfig,
    TTSConfig,
    ChapterAssets,
    AssetState,
)
from .image_generation import (
    generate_images_with_qps,
    generate_single_image,
    process_prompt_pairs,
)
from .audio_generation import (
    generate_tts_for_chapter,
    process_tts_batch,
)
from .asset_upload import (
    upload_assets_to_tos,
    download_assets_from_tos,
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
    # Image generation
    "generate_images_with_qps",
    "generate_single_image",
    "process_prompt_pairs",
    # Audio generation
    "generate_tts_for_chapter",
    "process_tts_batch",
    # Asset upload/download
    "upload_assets_to_tos",
    "download_assets_from_tos",
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
