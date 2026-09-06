from __future__ import annotations

import math
from dataclasses import dataclass

from campaign import get_campaign_setting
from database import get_connection
from rp_text import parse_story_post


DEFAULT_RECENT_SCENE_TOKEN_BUDGET = 7000
DEFAULT_PRIVATE_THOUGHT_TOKEN_BUDGET = 1200
DEFAULT_SCENE_SUMMARY_CHAR_BUDGET = 2400


@dataclass(frozen=True)
class ContinuityCommitResult:
    public_turn_ids: tuple[int, ...]
    private_thought_id: int | None
    opened_thread_ids: tuple[int, ...]
    resolved_thread_ids: tuple[int, ...]


def _clean(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _setting_int(
    key,
    default,
    minimum=1,
):
    raw = get_campaign_setting(
        key
    )

    if raw is None:
        return int(
            default
        )

    try:
        value = int(
            raw
        )
    except (
        TypeError,
        ValueError,
    ):
        return int(
            default
        )

    return max(
        int(minimum),
        value,
    )


def recent_scene_token_budget():
    return _setting_int(
        "recent_scene_token_budget",
        DEFAULT_RECENT_SCENE_TOKEN_BUDGET,
        minimum=500,
    )


def private_thought_token_budget():
    return _setting_int(
        "private_thought_token_budget",
        DEFAULT_PRIVATE_THOUGHT_TOKEN_BUDGET,
        minimum=200,
    )


def scene_summary_char_budget():
    return _setting_int(
        "scene_summary_char_budget",
        DEFAULT_SCENE_SUMMARY_CHAR_BUDGET,
        minimum=500,
    )


def estimate_tokens(text):
    """
    Approximate token count for a provider/model-neutral rolling budget.

    Horde can serve models with different tokenizers. This estimate is used
    only to decide when older perceived scene history should be compacted.
    """
    text = _clean(
        text
    )

    if text is None:
        return 0

    return max(
        1,
        int(
            math.ceil(
                len(text)
                / 4.0
            )
        ),
    )


def _ensure_tables():
    conn = get_connection()

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_scene_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,
            scene_id INTEGER,
            location_id INTEGER,

            visibility TEXT NOT NULL,
            speaker_type TEXT,
            speaker_id TEXT,
            speaker_name TEXT,

            content TEXT NOT NULL,

            source_type TEXT NOT NULL,
            source_id TEXT,

            compacted INTEGER NOT NULL DEFAULT 0,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id)
                ON DELETE SET NULL,

            FOREIGN KEY (location_id)
                REFERENCES locations(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_character_scene_turns_owner
        ON character_scene_turns(
            character_id,
            visibility,
            compacted,
            id
        );

        CREATE TABLE IF NOT EXISTS character_scene_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,
            scene_id INTEGER,

            summary TEXT NOT NULL,
            through_turn_id INTEGER NOT NULL,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_character_scene_summaries_owner
        ON character_scene_summaries(
            character_id,
            updated_at
        );

        CREATE TABLE IF NOT EXISTS character_open_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,
            content TEXT NOT NULL,

            source_type TEXT NOT NULL,
            source_id TEXT,

            status TEXT NOT NULL DEFAULT 'open',

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_character_open_threads_owner
        ON character_open_threads(
            character_id,
            status,
            id
        );
        """
    )

    conn.commit()
    conn.close()


def _fallback_summary(rows):
    pieces = []

    for row in rows:
        speaker = (
            _clean(
                row["speaker_name"]
            )
            or _clean(
                row["speaker_type"]
            )
            or "Someone"
        )

        pieces.append(
            f"{speaker}: "
            f"{row['content']}"
        )

    text = " | ".join(
        pieces
    )

    budget = (
        scene_summary_char_budget()
    )

    if len(text) > budget:
        text = (
            text[: budget - 1]
            .rstrip()
            + "…"
        )

    return text


def _merge_summary(
    old_summary,
    new_summary,
):
    old_summary = _clean(
        old_summary
    )
    new_summary = _clean(
        new_summary
    )

    if not old_summary:
        merged = (
            new_summary
            or ""
        )
    elif not new_summary:
        merged = old_summary
    else:
        merged = (
            old_summary
            + " | "
            + new_summary
        )

    budget = (
        scene_summary_char_budget()
    )

    if len(merged) > budget:
        merged = (
            merged[-budget:]
            .lstrip(" |")
        )

    return merged


def _upsert_summary(
    character_id,
    scene_id,
    rows,
    *,
    summarizer=None,
):
    if not rows:
        return None

    source_text = "\n".join(
        (
            f"{row['speaker_name'] or row['speaker_type'] or 'Someone'}: "
            f"{row['content']}"
        )
        for row in rows
    )

    new_summary = None

    if summarizer is not None:
        try:
            new_summary = _clean(
                summarizer(
                    source_text
                )
            )
        except Exception:
            new_summary = None

    if not new_summary:
        new_summary = (
            _fallback_summary(
                rows
            )
        )

    conn = get_connection()

    existing = conn.execute(
        """
        SELECT id, summary
        FROM character_scene_summaries
        WHERE character_id = ?
          AND (
                scene_id = ?
                OR (
                    scene_id IS NULL
                    AND ? IS NULL
                )
              )
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            int(character_id),
            scene_id,
            scene_id,
        ),
    ).fetchone()

    merged = _merge_summary(
        (
            None
            if existing is None
            else existing["summary"]
        ),
        new_summary,
    )

    through_turn_id = max(
        int(
            row["id"]
        )
        for row in rows
    )

    if existing is None:
        conn.execute(
            """
            INSERT INTO character_scene_summaries (
                character_id,
                scene_id,
                summary,
                through_turn_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                int(character_id),
                scene_id,
                merged,
                through_turn_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE character_scene_summaries
            SET
                summary = ?,
                through_turn_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                merged,
                through_turn_id,
                int(
                    existing["id"]
                ),
            ),
        )

    conn.commit()
    conn.close()

    return through_turn_id


def compact_public_history(
    character_id,
    *,
    token_budget=None,
    summarizer=None,
):
    """
    Compact the oldest exact public perceptions once the live budget is full.

    Exact rows remain stored and auditable; compacted rows stop entering the
    verbatim live context and are represented by the rolling summary instead.
    """
    _ensure_tables()

    if token_budget is None:
        token_budget = (
            recent_scene_token_budget()
        )

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM character_scene_turns
        WHERE character_id = ?
          AND visibility = 'public'
          AND compacted = 0
        ORDER BY id DESC
        """,
        (
            int(character_id),
        ),
    ).fetchall()

    conn.close()

    running = 0
    keep_ids = set()

    for row in rows:
        cost = estimate_tokens(
            row["content"]
        )

        if (
            not keep_ids
            or running + cost
            <= int(token_budget)
        ):
            keep_ids.add(
                int(row["id"])
            )
            running += cost
            continue

        break

    overflow = [
        row
        for row in reversed(
            rows
        )
        if int(row["id"])
        not in keep_ids
    ]

    if not overflow:
        return 0

    by_scene = {}

    for row in overflow:
        by_scene.setdefault(
            row["scene_id"],
            [],
        ).append(row)

    for (
        scene_id,
        scene_rows,
    ) in by_scene.items():
        _upsert_summary(
            character_id,
            scene_id,
            scene_rows,
            summarizer=summarizer,
        )

    ids = [
        int(row["id"])
        for row in overflow
    ]

    placeholders = ",".join(
        "?"
        for _ in ids
    )

    conn = get_connection()
    conn.execute(
        f"""
        UPDATE character_scene_turns
        SET compacted = 1
        WHERE id IN ({placeholders})
        """,
        ids,
    )
    conn.commit()
    conn.close()

    return len(
        ids
    )


def record_perceived_public_turn(
    character_id,
    content,
    *,
    scene_id=None,
    location_id=None,
    speaker_type=None,
    speaker_id=None,
    speaker_name=None,
    source_type="rp",
    source_id=None,
    summarizer=None,
):
    _ensure_tables()

    content = _clean(
        content
    )

    if content is None:
        return None

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO character_scene_turns (
            character_id,
            scene_id,
            location_id,
            visibility,
            speaker_type,
            speaker_id,
            speaker_name,
            content,
            source_type,
            source_id
        )
        VALUES (?, ?, ?, 'public', ?, ?, ?, ?, ?, ?)
        """,
        (
            int(character_id),
            scene_id,
            location_id,
            _clean(
                speaker_type
            ),
            (
                None
                if speaker_id is None
                else str(
                    speaker_id
                )
            ),
            _clean(
                speaker_name
            ),
            content,
            str(
                source_type
            ),
            (
                None
                if source_id is None
                else str(
                    source_id
                )
            ),
        ),
    )

    turn_id = int(
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    compact_public_history(
        character_id,
        summarizer=summarizer,
    )

    return turn_id


def record_private_thought(
    character_id,
    thought,
    *,
    scene_id=None,
    location_id=None,
    source_type="character_brain",
    source_id=None,
):
    _ensure_tables()

    thought = _clean(
        thought
    )

    if thought is None:
        return None

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO character_scene_turns (
            character_id,
            scene_id,
            location_id,
            visibility,
            speaker_type,
            speaker_id,
            content,
            source_type,
            source_id
        )
        VALUES (
            ?, ?, ?, 'private_self',
            'character', ?, ?, ?, ?
        )
        """,
        (
            int(character_id),
            scene_id,
            location_id,
            str(
                character_id
            ),
            thought,
            str(
                source_type
            ),
            (
                None
                if source_id is None
                else str(
                    source_id
                )
            ),
        ),
    )

    thought_id = int(
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return thought_id


def _budgeted_rows(
    character_id,
    *,
    visibility,
    token_budget,
):
    _ensure_tables()

    compacted_clause = (
        "AND compacted = 0"
        if visibility
        == "public"
        else ""
    )

    conn = get_connection()

    rows = conn.execute(
        f"""
        SELECT *
        FROM character_scene_turns
        WHERE character_id = ?
          AND visibility = ?
          {compacted_clause}
        ORDER BY id DESC
        """,
        (
            int(character_id),
            visibility,
        ),
    ).fetchall()

    conn.close()

    chosen = []
    running = 0

    for row in rows:
        cost = estimate_tokens(
            row["content"]
        )

        if (
            chosen
            and running + cost
            > int(token_budget)
        ):
            break

        chosen.append(
            row
        )
        running += cost

    return list(
        reversed(
            chosen
        )
    )


def get_recent_public_turns(
    character_id,
    *,
    token_budget=None,
):
    if token_budget is None:
        token_budget = (
            recent_scene_token_budget()
        )

    return _budgeted_rows(
        character_id,
        visibility="public",
        token_budget=int(
            token_budget
        ),
    )


def get_recent_private_thoughts(
    character_id,
    *,
    token_budget=None,
):
    if token_budget is None:
        token_budget = (
            private_thought_token_budget()
        )

    return _budgeted_rows(
        character_id,
        visibility=
            "private_self",
        token_budget=int(
            token_budget
        ),
    )


def get_scene_summaries(
    character_id,
    *,
    limit=4,
):
    _ensure_tables()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM character_scene_summaries
        WHERE character_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (
            int(character_id),
            int(limit),
        ),
    ).fetchall()

    conn.close()

    return list(
        reversed(
            rows
        )
    )


def open_thread(
    character_id,
    content,
    *,
    source_type="character_brain",
    source_id=None,
):
    _ensure_tables()

    content = _clean(
        content
    )

    if content is None:
        return None

    conn = get_connection()

    existing = conn.execute(
        """
        SELECT id
        FROM character_open_threads
        WHERE character_id = ?
          AND status = 'open'
          AND LOWER(content) = LOWER(?)
        LIMIT 1
        """,
        (
            int(character_id),
            content,
        ),
    ).fetchone()

    if existing is not None:
        thread_id = int(
            existing["id"]
        )
        conn.close()
        return thread_id

    cursor = conn.execute(
        """
        INSERT INTO character_open_threads (
            character_id,
            content,
            source_type,
            source_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            int(character_id),
            content,
            str(
                source_type
            ),
            (
                None
                if source_id is None
                else str(
                    source_id
                )
            ),
        ),
    )

    thread_id = int(
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return thread_id


def resolve_thread(
    character_id,
    thread_id,
):
    _ensure_tables()

    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE character_open_threads
        SET
            status = 'resolved',
            resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND character_id = ?
          AND status = 'open'
        """,
        (
            int(thread_id),
            int(character_id),
        ),
    )

    changed = bool(
        cursor.rowcount
    )

    conn.commit()
    conn.close()

    return changed


def get_open_threads(
    character_id,
):
    _ensure_tables()

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM character_open_threads
        WHERE character_id = ?
          AND status = 'open'
        ORDER BY id
        """,
        (
            int(character_id),
        ),
    ).fetchall()

    conn.close()

    return rows


def apply_thread_updates(
    character_id,
    *,
    open_threads=(),
    resolve_thread_ids=(),
    source_type="character_brain",
    source_id=None,
):
    opened = []

    for content in (
        open_threads
        or ()
    ):
        thread_id = open_thread(
            character_id,
            content,
            source_type=
                source_type,
            source_id=
                source_id,
        )

        if (
            thread_id
            is not None
        ):
            opened.append(
                thread_id
            )

    resolved = []

    for thread_id in (
        resolve_thread_ids
        or ()
    ):
        if resolve_thread(
            character_id,
            thread_id,
        ):
            resolved.append(
                int(
                    thread_id
                )
            )

    return (
        tuple(
            opened
        ),
        tuple(
            resolved
        ),
    )


def build_continuity_context(
    character_id,
):
    public_rows = (
        get_recent_public_turns(
            character_id
        )
    )
    private_rows = (
        get_recent_private_thoughts(
            character_id
        )
    )
    summaries = (
        get_scene_summaries(
            character_id
        )
    )
    threads = (
        get_open_threads(
            character_id
        )
    )

    return {
        "recent_public": [
            {
                "turn_id":
                    int(row["id"]),
                "scene_id":
                    row["scene_id"],
                "location_id":
                    row["location_id"],
                "speaker_type":
                    row["speaker_type"],
                "speaker_id":
                    row["speaker_id"],
                "speaker_name":
                    row["speaker_name"],
                "content":
                    row["content"],
            }
            for row in public_rows
        ],
        "recent_private_thoughts": [
            {
                "turn_id":
                    int(row["id"]),
                "scene_id":
                    row["scene_id"],
                "location_id":
                    row["location_id"],
                "content":
                    row["content"],
            }
            for row in private_rows
        ],
        "scene_summaries": [
            {
                "scene_id":
                    row["scene_id"],
                "summary":
                    row["summary"],
                "through_turn_id":
                    int(
                        row[
                            "through_turn_id"
                        ]
                    ),
            }
            for row in summaries
        ],
        "open_threads": [
            {
                "thread_id":
                    int(row["id"]),
                "content":
                    row["content"],
            }
            for row in threads
        ],
        "budgets": {
            "recent_public_estimated_tokens":
                recent_scene_token_budget(),
            "private_thought_estimated_tokens":
                private_thought_token_budget(),
        },
    }


def render_scene_continuity(
    character_id,
):
    """
    Render only this character's sanitized continuity.

    No raw Discord history is read here. The public rows were explicitly
    recorded as perceived, and private rows belong to this character only.
    """
    continuity = (
        build_continuity_context(
            character_id
        )
    )

    if not (
        continuity[
            "recent_public"
        ]
        or continuity[
            "recent_private_thoughts"
        ]
        or continuity[
            "scene_summaries"
        ]
        or continuity[
            "open_threads"
        ]
    ):
        return ""

    lines = [
        "CHARACTER-SPECIFIC CONTINUITY",
        (
            "This is only what you personally perceived or privately thought. "
            "It is not raw Discord history."
        ),
    ]

    if continuity[
        "scene_summaries"
    ]:
        lines.extend(
            [
                "",
                "EARLIER SCENE CONTINUITY",
            ]
        )

        for item in continuity[
            "scene_summaries"
        ]:
            lines.append(
                "- "
                + item[
                    "summary"
                ]
            )

    if continuity[
        "recent_public"
    ]:
        lines.extend(
            [
                "",
                "RECENT PERCEIVED SCENE HISTORY",
            ]
        )

        for item in continuity[
            "recent_public"
        ]:
            speaker = (
                item[
                    "speaker_name"
                ]
                or item[
                    "speaker_type"
                ]
                or "Someone"
            )

            lines.append(
                f"- {speaker}: "
                f"{item['content']}"
            )

    if continuity[
        "recent_private_thoughts"
    ]:
        lines.extend(
            [
                "",
                "YOUR RECENT PRIVATE THOUGHTS",
                (
                    "These are yours alone. Other characters do not receive them."
                ),
            ]
        )

        for item in continuity[
            "recent_private_thoughts"
        ]:
            lines.append(
                "- "
                + item[
                    "content"
                ]
            )

    if continuity[
        "open_threads"
    ]:
        lines.extend(
            [
                "",
                "UNRESOLVED BUSINESS YOU ARE CARRYING",
                (
                    "Keep these active until genuinely resolved."
                ),
            ]
        )

        for item in continuity[
            "open_threads"
        ]:
            lines.append(
                f"- [thread #{item['thread_id']}] "
                f"{item['content']}"
            )

    return "\n".join(
        lines
    )


def record_human_story_post_for_characters(
    text,
    character_ids,
    *,
    scene_id=None,
    location_id=None,
    speaker_id=None,
    speaker_name=None,
    source_id=None,
    summarizer=None,
):
    """
    AI observers receive only the non-italic public portion of a human post.
    """
    parsed = parse_story_post(
        text
    )

    ids = []

    if parsed.public_text:
        for character_id in (
            character_ids
        ):
            turn_id = (
                record_perceived_public_turn(
                    character_id,
                    parsed.public_text,
                    scene_id=
                        scene_id,
                    location_id=
                        location_id,
                    speaker_type=
                        "player_persona",
                    speaker_id=
                        speaker_id,
                    speaker_name=
                        speaker_name,
                    source_type=
                        "discord_message",
                    source_id=
                        source_id,
                    summarizer=
                        summarizer,
                )
            )

            if (
                turn_id
                is not None
            ):
                ids.append(
                    turn_id
                )

    return (
        parsed,
        tuple(
            ids
        ),
    )


def commit_character_turn(
    character_id,
    turn,
    perceiver_character_ids,
    *,
    scene_id=None,
    location_id=None,
    speaker_name=None,
    source_id=None,
    summarizer=None,
):
    """
    Commit an accepted AI turn to continuity.

    Public prose goes only to explicitly supplied perceivers (plus the speaker
    themself). Private thought is written only to the owner. Mechanical action
    metadata is never copied into conversational history.
    """
    observer_ids = []

    for observer_id in (
        [character_id]
        + list(
            perceiver_character_ids
            or ()
        )
    ):
        observer_id = int(
            observer_id
        )

        if observer_id not in observer_ids:
            observer_ids.append(
                observer_id
            )

    public_ids = []

    public_text = _clean(
        getattr(
            turn,
            "public",
            None,
        )
    )

    if public_text:
        for observer_id in observer_ids:
            turn_id = (
                record_perceived_public_turn(
                    observer_id,
                    public_text,
                    scene_id=
                        scene_id,
                    location_id=
                        location_id,
                    speaker_type=
                        "character",
                    speaker_id=
                        character_id,
                    speaker_name=
                        speaker_name,
                    source_type=
                        "character_turn",
                    source_id=
                        source_id,
                    summarizer=
                        summarizer,
                )
            )

            if turn_id is not None:
                public_ids.append(
                    turn_id
                )

    private_id = (
        record_private_thought(
            character_id,
            getattr(
                turn,
                "thought",
                None,
            ),
            scene_id=scene_id,
            location_id=
                location_id,
            source_id=source_id,
        )
    )

    (
        opened,
        resolved,
    ) = apply_thread_updates(
        character_id,
        open_threads=getattr(
            turn,
            "open_threads",
            (),
        ),
        resolve_thread_ids=getattr(
            turn,
            "resolve_thread_ids",
            (),
        ),
        source_id=source_id,
    )

    return ContinuityCommitResult(
        public_turn_ids=tuple(
            public_ids
        ),
        private_thought_id=
            private_id,
        opened_thread_ids=
            opened,
        resolved_thread_ids=
            resolved,
    )
