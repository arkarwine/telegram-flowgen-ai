from __future__ import annotations


APPROVAL_WORDS = {
    "yes",
    "yep",
    "yeah",
    "correct",
    "approved",
    "approve",
    "build it",
    "go ahead",
    "looks good",
    "that's right",
    "that is right",
}


def looks_like_approval(text: str) -> bool:
    normalized = text.strip().casefold()
    return normalized in APPROVAL_WORDS or any(phrase in normalized for phrase in APPROVAL_WORDS if " " in phrase)


def looks_like_correction(text: str) -> bool:
    normalized = text.strip().casefold()
    correction_markers = ["change", "instead", "actually", "make it", "also", "add", "remove", "not"]
    return any(marker in normalized for marker in correction_markers)

