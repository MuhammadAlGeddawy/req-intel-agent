"""Shared normalization helpers for the requirements analysis pipeline."""

from typing import Any

# ISO 26262 standard ASIL values exposed to callers/schemas.
ASIL_VALUES = ("QM", "ASIL_A", "ASIL_B", "ASIL_C", "ASIL_D")


def normalize_asil(value: Any, default: str = "QM") -> str:
    """
    Normalize an arbitrary suggested ASIL value to the ISO 26262 standard strings:
    "QM", "ASIL_A", "ASIL_B", "ASIL_C", "ASIL_D".

    Accepts a variety of loose formats such as:
        "QM", "qm", "ASIL B", "ASIL-B", "ASILB", "A", "B", "C", "D", "ASIL_C",
        "asil-d", None, "", ...
    Any unrecognized value falls back to ``default`` (QM).
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default

    normalized = text.upper().replace("-", "_").replace(" ", "_")

    if normalized in ASIL_VALUES:
        return normalized

    # Compact/abbreviated forms: "ASILB", "ASILA", "A", "B", ...
    if normalized in {"A", "ASILA"}:
        return "ASIL_A"
    if normalized in {"B", "ASILB"}:
        return "ASIL_B"
    if normalized in {"C", "ASILC"}:
        return "ASIL_C"
    if normalized in {"D", "ASILD"}:
        return "ASIL_D"

    return default

