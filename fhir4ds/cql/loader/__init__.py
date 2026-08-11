"""FHIR data loading utilities.

Phase 2 (medterm4ds integration) adds the :class:`AutoCoder` for
augmenting text-only CodeableConcepts with auto-coded Codings.

Phase 4 (medterm4ds integration) adds the :class:`NotesPipeline` for
extracting Conditions from clinical-note text via ``medterm4ds.extract``.
"""

from .auto_coder import AutoCoder, AutoCoderConfig
from .autocoding_extension import (
    AUTOCODING_EXTENSION_URL,
    build_autocoding_extension,
    is_autocoded,
    parse_autocoding_extension,
)
from .category import RESOURCE_TYPE_TO_CATEGORY, normalize_text, resolve_category
from .derived_from_text_extension import (
    DERIVED_FROM_TEXT_EXTENSION_URL,
    build_derived_from_text_extension,
    is_derived_from_text,
    parse_derived_from_text_extension,
)
from .fhir_loader import FHIRDataLoader
from .notes_pipeline import NotesPipeline, NotesPipelineConfig
from .notes_text_extractor import DEFAULT_NOTE_PATHS, NoteText, extract_note_texts

__all__ = [
    # Phase 2 — auto-coding loader
    "FHIRDataLoader",
    "AutoCoder",
    "AutoCoderConfig",
    "AUTOCODING_EXTENSION_URL",
    "build_autocoding_extension",
    "parse_autocoding_extension",
    "is_autocoded",
    "RESOURCE_TYPE_TO_CATEGORY",
    "resolve_category",
    "normalize_text",
    # Phase 4 — clinical notes NER
    "NotesPipeline",
    "NotesPipelineConfig",
    "DEFAULT_NOTE_PATHS",
    "NoteText",
    "extract_note_texts",
    "DERIVED_FROM_TEXT_EXTENSION_URL",
    "build_derived_from_text_extension",
    "parse_derived_from_text_extension",
    "is_derived_from_text",
]
