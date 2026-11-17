"""herecraft.stubgen.javadoc — Turn a javadoc fragment into the text a stub docstring shows.

Parchment publishes a doc as a list of strings, with the markup it was written in: {@code ...}, {@link Type#member
label}, <p>, <li>, <table> cells, and the occasional block tag on its own line. A docstring is plain text, so the
markup is turned into what a reader of Python would write: `code`, a name, a blank line between paragraphs, and
`- ` for a list item.

Only tags javadoc itself emits are touched. A fragment that spells a type parameter as <T> keeps it, because a
stripped tag there would delete a character of the sentence.
"""

from __future__ import annotations

from collections.abc import Iterable
import html
import re

# `{@code x}` and `{@literal x}` carry verbatim text; the braces are scaffolding.
_VERBATIM = re.compile(r"\{@(?:code|literal)\s+([^}]*)\}")
# `{@link Type#member label}`, and its `{@linkplain ...}` spelling.
_LINK = re.compile(r"\{@link(?:plain)?\s+([^}]*)\}")
# Any other inline tag keeps its body: `{@return {@code x}}` reads as `` `x` ``.
_INLINE_TAG = re.compile(r"\{@\w+\s*([^}]*)\}")

_PARAGRAPH = re.compile(r"<(?:p|br)\b[^>]*>|</p>", re.IGNORECASE)
_ITEM = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_CELL = re.compile(r"</?t[dh]\b[^>]*>", re.IGNORECASE)
_ROW = re.compile(r"<tr\b[^>]*>|</tr>", re.IGNORECASE)
_BOLD = re.compile(r"</?(?:strong|b)\b[^>]*>", re.IGNORECASE)
_ITALIC = re.compile(r"</?(?:em|i|cite)\b[^>]*>", re.IGNORECASE)
_MONO = re.compile(r"</?(?:code|samp)\b[^>]*>", re.IGNORECASE)
_BLOCK = re.compile(
    r"</?(?:pre|h[1-6]|ul|ol|table|blockquote)\b[^>]*>",
    re.IGNORECASE,
)
_TAG = re.compile(
    r"</?(?:p|br|li|ul|ol|pre|code|samp|strong|b|i|em|cite|h[1-6]|a|table|tbody|tr|td|th|div|span|blockquote"
    + r"|q|dd|dt|dl|hr|sup|sub|var)\b[^>]*>",
    re.IGNORECASE,
)
# `@param <T> ...`, `@see ...`, `@return ...`: javadoc's block tags, which have no place in a docstring body.
_BLOCK_TAG = re.compile(r"@\w+")
# Two adjacent cell separators, which a hidden or empty cell leaves behind.
_CELL_RUN = re.compile(r"\|(?:\s*\|)+")


def to_text(parts: Iterable[str]) -> str:
    """One docstring body from the doc's parts, with the markup turned into what a Python reader writes."""
    text = "\n".join(parts)
    text = _VERBATIM.sub(lambda match: f"`{match.group(1).strip()}`", text)
    text = _LINK.sub(_link, text)
    text = _INLINE_TAG.sub(lambda match: match.group(1).strip(), text)

    text = _PARAGRAPH.sub("\n\n", text)
    text = _ITEM.sub("\n- ", text)
    text = _CELL.sub(" | ", text)
    text = _ROW.sub("\n", text)
    text = _BLOCK.sub("\n\n", text)
    text = _BOLD.sub("**", text)
    text = _ITALIC.sub("*", text)
    text = _MONO.sub("`", text)
    text = _TAG.sub("", text)

    return _tidy(html.unescape(text))


def _link(match: re.Match[str]) -> str:
    """`Type#member label` reads as the label; with no label, as the name javadoc itself shows."""
    target, _, label = match.group(1).strip().partition(" ")
    if label.strip():
        return label.strip()
    owner, _, member = target.partition("#")
    owner = owner.rsplit(".", 1)[-1]
    return f"{owner}.{member}" if owner and member else owner or member


def _tidy(text: str) -> str:
    """Collapse the whitespace the replacements leave behind, and stop a table cell ending a line."""
    lines: list[str] = []
    for line in text.splitlines():
        line = _CELL_RUN.sub("|", " ".join(line.split())).strip().strip("|").strip()
        if _BLOCK_TAG.match(line):
            continue
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        lines.append(line)
    while lines and not lines[-1]:
        _ = lines.pop()
    return "\n".join(lines)
