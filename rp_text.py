from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ParsedStoryPost:
    public_text: str | None
    thoughts: tuple[str, ...]


def _clean(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


_THOUGHT_RE = re.compile(
    r"(?<!\\)(?<!\*)\*(?!\*)(.+?)(?<!\\)(?<!\*)\*(?!\*)",
    re.DOTALL,
)


def parse_story_post(text):
    """
    Split story-style Discord RP into public prose and private thought.

    Convention:
      - action/narration: ordinary prose
      - spoken dialogue: quotation marks inside the prose
      - private thought: single-asterisk Discord italics

    Only complete italic spans are private. Unmatched Markdown remains public.
    """
    text = _clean(text)

    if text is None:
        return ParsedStoryPost(
            public_text=None,
            thoughts=(),
        )

    thoughts = []

    def remove_thought(match):
        thought = _clean(
            match.group(1)
        )

        if thought:
            thoughts.append(
                thought
            )

        return ""

    public = _THOUGHT_RE.sub(
        remove_thought,
        text,
    )

    lines = []

    for line in public.splitlines():
        cleaned = " ".join(
            line.split()
        ).strip()

        if cleaned:
            lines.append(cleaned)

    public = (
        "\n".join(lines).strip()
        or None
    )

    return ParsedStoryPost(
        public_text=public,
        thoughts=tuple(
            thoughts
        ),
    )


def strip_outer_italics(text):
    text = _clean(text)

    if (
        text
        and len(text) >= 2
        and text.startswith("*")
        and text.endswith("*")
        and not text.startswith("**")
        and not text.endswith("**")
    ):
        return _clean(
            text[1:-1]
        )

    return text


def _escape_thought_for_discord(text):
    return str(text).replace(
        "*",
        r"\*",
    )


def render_story_turn(
    public_text=None,
    thought=None,
):
    """
    Render what the human sees in Discord.

    Mechanical action metadata is deliberately not accepted by this function.
    """
    public_text = _clean(
        public_text
    )
    thought = strip_outer_italics(
        thought
    )

    parts = []

    if public_text:
        parts.append(
            public_text
        )

    if thought:
        for line in thought.splitlines():
            line = line.strip()

            if line:
                parts.append(
                    "*"
                    + _escape_thought_for_discord(
                        line
                    )
                    + "*"
                )

    return "\n".join(
        parts
    ).strip()
