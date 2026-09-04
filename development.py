from __future__ import annotations

from campaign_clock import get_campaign_datetime
from database import get_connection
from family import get_family_links
from life import (
    get_age_days,
    get_age_months,
    get_age_years,
)
from mortality import is_alive


VALID_AI_PARTICIPATION_MODES = {
    "deferred",
    "limited",
    "full",
}


# These are broad RP grounding bands, not diagnoses or claims that every
# person develops identically. Actual age is always supplied alongside
# the band, and individual developmental notes can modify the baseline.
#
# The grounding deliberately focuses on comprehension, social
# interpretation, communication, and self-regulation. It does NOT
# assign personality, morality, emotions, loyalties, or choices.
STAGE_GUIDANCE = {
    "infant": {
        "comprehension": (
            "Understand the immediate world primarily through sensation, "
            "familiar people, routines, simple cause-and-effect, and "
            "developing object/person recognition."
        ),
        "social": (
            "Respond to familiar voices, faces, comfort, distress, and "
            "simple social cues; do not infer complex motives or relationships."
        ),
        "communication": (
            "Communication is pre-verbal or very early verbal depending on "
            "exact age, using cries, sounds, gestures, expressions, and "
            "emerging simple words where plausible."
        ),
        "reasoning": (
            "Keep attention, planning, memory use, and impulse control "
            "appropriate to infancy and the exact age."
        ),
    },
    "toddler": {
        "comprehension": (
            "Reason mainly from concrete, immediate experience. Understand "
            "simple routines, requests, causes, possession, familiar people, "
            "and basic categories; complex or hidden meanings are usually "
            "beyond the character unless specifically learned."
        ),
        "social": (
            "Notice obvious emotions, approval, disapproval, conflict, "
            "affection, and simple rules, but do not supply adult-level "
            "interpretations of motives, relationships, morality, or secrecy."
        ),
        "communication": (
            "Use age-plausible words and sentence complexity based on exact "
            "age and established development. Do not make the character "
            "articulate like an adult merely because the model can be."
        ),
        "reasoning": (
            "Keep attention, planning, emotional regulation, abstraction, "
            "and consideration of consequences strongly age-bounded."
        ),
    },
    "young_child": {
        "comprehension": (
            "Think primarily in concrete terms. Understand increasingly rich "
            "stories, routines, rules, cause-and-effect, and familiar social "
            "situations, while many abstract, adult, political, romantic, "
            "legal, and socially complex meanings remain incomplete unless "
            "the character has genuinely learned them."
        ),
        "social": (
            "Recognize obvious feelings, fairness, rules, friendship, "
            "approval, disapproval, secrecy, and interpersonal conflict, but "
            "do not automatically infer sophisticated motives or adult "
            "relationship implications."
        ),
        "communication": (
            "Use age-plausible vocabulary, explanations, questions, and "
            "sentence structure. Individual children may be unusually "
            "articulate without acquiring adult comprehension."
        ),
        "reasoning": (
            "Allow curiosity and growing problem-solving, while keeping "
            "abstraction, long-range planning, impulse control, perspective "
            "taking, and consequence-weighing plausibly immature."
        ),
    },
    "older_child": {
        "comprehension": (
            "Support stronger concrete reasoning, rules, social patterns, "
            "cause-and-effect, and growing ability to understand other "
            "viewpoints. Abstract and adult social meanings are developing "
            "but must still depend on education and lived experience."
        ),
        "social": (
            "Allow increasingly nuanced friendship, fairness, reputation, "
            "loyalty, deception, embarrassment, and social-rule understanding, "
            "without granting automatic adult insight into complex motives "
            "or relationships."
        ),
        "communication": (
            "Use increasingly fluent language and explanation appropriate to "
            "exact age, education, culture, and experience; avoid adult "
            "professional or scholarly voice unless specifically justified."
        ),
        "reasoning": (
            "Permit growing planning and perspective-taking, while keeping "
            "judgement, self-regulation, abstraction, and long-term "
            "consequence assessment developmentally plausible."
        ),
    },
    "adolescent": {
        "comprehension": (
            "Allow substantial adult-like knowledge where learned and a "
            "growing capacity for abstraction, complex relationships, social "
            "systems, and hidden motives. Do not assume adult experience or "
            "fully mature judgement merely because the model understands it."
        ),
        "social": (
            "Support nuanced moral and social interpretation while respecting "
            "the character's actual upbringing, culture, education, memories, "
            "peer world, and still-developing perspective."
        ),
        "communication": (
            "Use language appropriate to exact age, education, personality, "
            "culture, and setting. Do not default to polished adult assistant "
            "speech."
        ),
        "reasoning": (
            "Complex reasoning is possible, but planning, impulse control, "
            "risk assessment, emotional regulation, and long-range judgement "
            "may still be less consistent than in a mature adult."
        ),
    },
    "adult": {
        "comprehension": (
            "Do not impose childhood developmental limits. Knowledge still "
            "comes from this character's own education, experience, memories, "
            "culture, and access to information."
        ),
        "social": (
            "Interpret social situations through this character's own "
            "personality, values, beliefs, relationships, knowledge, and "
            "experience rather than a universal moral viewpoint."
        ),
        "communication": (
            "Use this character's established speech style, education, "
            "culture, personality, and circumstances."
        ),
        "reasoning": (
            "Do not equate adulthood with wisdom, education, emotional "
            "stability, morality, or good judgement; those remain individual."
        ),
    },
}


def _require_character(character_id):
    character_id = int(character_id)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM characters
        WHERE id = ?
          AND active = 1
        """,
        (character_id,),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(
            f"Character {character_id} does not exist or is inactive."
        )

    return row


def developmental_stage_for_age(
    age_years,
):
    if age_years is None:
        return None

    age_years = int(age_years)

    if age_years < 0:
        raise ValueError(
            "Age cannot be negative."
        )

    if age_years < 2:
        return "infant"

    if age_years < 4:
        return "toddler"

    if age_years < 8:
        return "young_child"

    if age_years < 13:
        return "older_child"

    if age_years < 18:
        return "adolescent"

    return "adult"


def get_developmental_stage(
    character_id,
    *,
    at_datetime=None,
):
    _require_character(character_id)

    profile = get_development_profile(
        character_id
    )

    override = profile[
        "developmental_stage_override"
    ]

    if override:
        return override

    age_years = get_age_years(
        "character",
        character_id,
        at_datetime=at_datetime,
    )

    return developmental_stage_for_age(
        age_years
    )


def get_development_profile(
    character_id,
):
    character = _require_character(
        character_id
    )

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM character_lifecycle_profiles
        WHERE character_id = ?
        """,
        (int(character_id),),
    ).fetchone()
    conn.close()

    if row is None:
        return {
            "character_id": int(character_id),
            "developmental_stage_override": None,
            "developmental_notes": None,
            "ai_participation_mode": "deferred",
            "character_name": character["name"],
        }

    return row


def set_development_profile(
    character_id,
    *,
    developmental_stage_override=None,
    developmental_notes=None,
    ai_participation_mode="deferred",
):
    _require_character(character_id)

    mode = str(
        ai_participation_mode
    ).lower().strip()

    if mode not in VALID_AI_PARTICIPATION_MODES:
        raise ValueError(
            "Invalid ai_participation_mode."
        )

    if developmental_stage_override is not None:
        developmental_stage_override = str(
            developmental_stage_override
        ).strip()

        if (
            developmental_stage_override
            not in STAGE_GUIDANCE
        ):
            raise ValueError(
                "Invalid developmental_stage_override."
            )

    if developmental_notes is not None:
        developmental_notes = str(
            developmental_notes
        ).strip() or None

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO character_lifecycle_profiles (
            character_id,
            developmental_stage_override,
            developmental_notes,
            ai_participation_mode
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(character_id)
        DO UPDATE SET
            developmental_stage_override =
                excluded.developmental_stage_override,
            developmental_notes =
                excluded.developmental_notes,
            ai_participation_mode =
                excluded.ai_participation_mode,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(character_id),
            developmental_stage_override,
            developmental_notes,
            mode,
        ),
    )
    conn.commit()
    conn.close()

    return get_development_profile(
        character_id
    )


def set_ai_participation_mode(
    character_id,
    mode,
):
    current = get_development_profile(
        character_id
    )

    return set_development_profile(
        character_id,
        developmental_stage_override=current[
            "developmental_stage_override"
        ],
        developmental_notes=current[
            "developmental_notes"
        ],
        ai_participation_mode=mode,
    )


def build_developmental_grounding(
    character_id,
    *,
    at_datetime=None,
):
    """
    Compact directive intended for the character brain.

    It explicitly prevents model-level understanding from leaking into
    the character merely because the language model understands the
    scene. It constrains capacity; it never supplies personality,
    morality, emotions, or choices.
    """
    character = _require_character(
        character_id
    )

    age_years = get_age_years(
        "character",
        character_id,
        at_datetime=at_datetime,
    )

    if age_years is None:
        return None

    age_months = get_age_months(
        "character",
        character_id,
        at_datetime=at_datetime,
    )

    stage = get_developmental_stage(
        character_id,
        at_datetime=at_datetime,
    )

    guidance = STAGE_GUIDANCE[stage]
    profile = get_development_profile(
        character_id
    )

    if age_years < 2:
        age_label = (
            f"{age_months} months"
        )
    else:
        age_label = (
            f"{age_years} years"
        )

    notes = profile[
        "developmental_notes"
    ]

    lines = [
        "DEVELOPMENTAL GROUNDING",
        f"Character: {character['name']}",
        f"Actual age: {age_label}",
        f"Developmental stage: {stage.replace('_', ' ').title()}",
        "",
        (
            "Portray this character within plausible developmental "
            "capacity for the exact age and established individual "
            "development."
        ),
        (
            "Do not give the character adult interpretations, concepts, "
            "motives, vocabulary, relationship knowledge, moral reasoning, "
            "or social understanding merely because you as the model "
            "understand them."
        ),
        (
            "The character may know only what is plausible for their "
            "development AND what their own education, experiences, "
            "memories, culture, and prior teaching support."
        ),
        (
            "When an event exceeds their understanding, retain the "
            "concrete observable details without automatically supplying "
            "the hidden or adult meaning."
        ),
        "",
        f"Comprehension: {guidance['comprehension']}",
        f"Social interpretation: {guidance['social']}",
        f"Communication: {guidance['communication']}",
        f"Reasoning/self-regulation: {guidance['reasoning']}",
    ]

    if notes:
        lines.extend(
            [
                "",
                (
                    "Individual developmental context: "
                    + notes
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "Development constrains capacity; it does not dictate "
                "personality, morality, emotions, loyalties, or choices."
            ),
        ]
    )

    return "\n".join(lines)


def get_director_perception_constraints(
    character_id,
    *,
    at_datetime=None,
):
    """
    Structured constraints for the future Director/perception layer.

    The Director should reveal observable reality without pre-interpreting
    hidden adult meaning for a child who could not plausibly understand it.
    """
    _require_character(
        character_id
    )

    age_years = get_age_years(
        "character",
        character_id,
        at_datetime=at_datetime,
    )

    if age_years is None:
        return None

    stage = get_developmental_stage(
        character_id,
        at_datetime=at_datetime,
    )

    if stage == "adult":
        return {
            "stage": stage,
            "developmental_filter_required": False,
            "directive": (
                "Reveal only what this character can perceive and know; "
                "no child-development filter is required."
            ),
        }

    return {
        "stage": stage,
        "developmental_filter_required": True,
        "directive": (
            "Describe perceivable concrete details first. Do not label "
            "hidden motives, adult relationship meanings, moral implications, "
            "or concepts the character could not plausibly understand from "
            "age, development, education, memories, culture, and lived "
            "experience. Preserve ambiguity when understanding is incomplete."
        ),
    }


def record_milestone(
    character_id,
    milestone_type,
    *,
    description=None,
    achieved_at=None,
    world_event_id=None,
    notes=None,
):
    _require_character(
        character_id
    )

    milestone_type = str(
        milestone_type
    ).strip()

    if not milestone_type:
        raise ValueError(
            "milestone_type cannot be empty."
        )

    if achieved_at is None:
        achieved_at = (
            get_campaign_datetime()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
    elif hasattr(
        achieved_at,
        "strftime",
    ):
        achieved_at = achieved_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        achieved_at = str(
            achieved_at
        ).strip()

    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO developmental_milestones (
            character_id,
            milestone_type,
            description,
            achieved_at,
            world_event_id,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(character_id),
            milestone_type,
            description,
            achieved_at,
            world_event_id,
            notes,
        ),
    )
    milestone_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return get_milestone(
        milestone_id
    )


def get_milestone(
    milestone_id,
):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM developmental_milestones
        WHERE id = ?
        """,
        (int(milestone_id),),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(
            "Developmental milestone does not exist."
        )

    return row


def get_milestones(
    character_id,
):
    _require_character(
        character_id
    )

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM developmental_milestones
        WHERE character_id = ?
        ORDER BY achieved_at, id
        """,
        (int(character_id),),
    ).fetchall()
    conn.close()

    return rows


def get_care_relationships(
    character_id,
):
    """
    Objective relationships only. These do not automatically become the
    child's beliefs about who their parents or family are.
    """
    _require_character(
        character_id
    )

    relation_types = (
        "caregiver",
        "guardian",
        "adoptive_parent",
        "social_parent",
        "gestational_parent",
        "biological_parent",
    )

    return {
        relation_type: get_family_links(
            "character",
            character_id,
            relation_type=relation_type,
        )
        for relation_type in relation_types
    }


def get_development_context(
    character_id,
    *,
    at_datetime=None,
):
    character = _require_character(
        character_id
    )

    age_days = get_age_days(
        "character",
        character_id,
        at_datetime=at_datetime,
    )
    age_months = get_age_months(
        "character",
        character_id,
        at_datetime=at_datetime,
    )
    age_years = get_age_years(
        "character",
        character_id,
        at_datetime=at_datetime,
    )

    profile = get_development_profile(
        character_id
    )

    stage = (
        None
        if age_years is None
        else get_developmental_stage(
            character_id,
            at_datetime=at_datetime,
        )
    )

    alive = is_alive(
        "character",
        character_id,
    )

    return {
        "character_id": int(character_id),
        "character_name": character["name"],
        "alive": alive,
        "age_days": age_days,
        "age_months": age_months,
        "age_years": age_years,
        "developmental_stage": stage,
        "developmental_notes": profile[
            "developmental_notes"
        ],
        "ai_participation_mode": profile[
            "ai_participation_mode"
        ],
        "may_invoke_ai_brain": (
            alive
            and profile[
                "ai_participation_mode"
            ]
            in {"limited", "full"}
        ),
        "developmental_grounding": (
            None
            if age_years is None
            else build_developmental_grounding(
                character_id,
                at_datetime=at_datetime,
            )
        ),
        "director_perception_constraints": (
            None
            if age_years is None
            else get_director_perception_constraints(
                character_id,
                at_datetime=at_datetime,
            )
        ),
        "milestones": get_milestones(
            character_id
        ),
        "care_relationships": (
            get_care_relationships(
                character_id
            )
        ),
    }
