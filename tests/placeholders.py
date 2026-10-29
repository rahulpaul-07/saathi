"""Test helper: fake translator output that keeps the masking placeholders, as a real model does."""

import re

PLACEHOLDER = re.compile(r"#L\d+")


def carry(output: str, text: str) -> str:
    """Return `output` followed by every placeholder found in `text`."""
    return " ".join([output, *PLACEHOLDER.findall(text)])
