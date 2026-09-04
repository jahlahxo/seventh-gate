from database import (
    get_connection,
    create_embedding,
    embedding_to_text,
    search_character_memories,
    search_character_knowledge,
)


# ============================================================
# AUTHORITY LEVELS
# ============================================================

AUTHORITY = {
    "engine": 100,
    "director": 100,
    "canonical_world": 100,

    # Legacy source label retained for old records/imports.
    "gm": 100,

    "player_self": 95,
    "observed_event": 85,
    "trusted_source": 70,
    "other_character_claim": 50,
    "rumour": 30,
    "inference": 25,
    "ai_generated": 0,
}


# ============================================================
# CANONICAL FACTS
# Objective truth known by Seventh Gate itself.
# This does NOT automatically mean an NPC knows the fact.
# ============================================================

def add_canonical_fact(
    subject_type,
    subject_id,
    content,
    source_type,
    source_id=None,
    predicate=None,
    authority=None,
    confidence=1.0,
):
    if authority is None:
        authority = AUTHORITY.get(source_type, 50)

    vector = create_embedding(content)

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO canonical_facts (
            subject_type,
            subject_id,
            predicate,
            content,
            source_type,
            source_id,
            authority,
            confidence,
            embedding
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subject_type,
            str(subject_id) if subject_id is not None else None,
            predicate,
            content,
            source_type,
            str(source_id) if source_id is not None else None,
            authority,
            confidence,
            embedding_to_text(vector),
        ),
    )

    fact_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return fact_id


# ============================================================
# NPC KNOWLEDGE / BELIEFS
#
# This is what a specific NPC thinks is true.
# It can differ from canonical reality.
# ============================================================

def add_character_knowledge(
    character_id,
    content,
    knowledge_type,
    source_type,
    source_id=None,
    subject_type=None,
    subject_id=None,
    confidence=1.0,
    importance=5,
    is_secret=0,
):
    vector = create_embedding(content)

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO character_knowledge (
            character_id,
            subject_type,
            subject_id,
            content,
            knowledge_type,
            source_type,
            source_id,
            confidence,
            importance,
            is_secret,
            embedding
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            subject_type,
            str(subject_id) if subject_id is not None else None,
            content,
            knowledge_type,
            source_type,
            str(source_id) if source_id is not None else None,
            confidence,
            importance,
            is_secret,
            embedding_to_text(vector),
        ),
    )

    knowledge_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return knowledge_id


# ============================================================
# EPISODIC NPC MEMORY
#
# Something an NPC personally experienced/remembers.
# ============================================================

def add_character_memory(
    character_id,
    content,
    memory_type="event",
    scene_id=None,
    emotional_context=None,
    importance=5,
    confidence=1.0,
    source_message_start_id=None,
    source_message_end_id=None,
):
    vector = create_embedding(content)

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO character_memories (
            character_id,
            scene_id,
            memory_type,
            content,
            emotional_context,
            importance,
            confidence,
            source_message_start_id,
            source_message_end_id,
            embedding
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            scene_id,
            memory_type,
            content,
            emotional_context,
            importance,
            confidence,
            source_message_start_id,
            source_message_end_id,
            embedding_to_text(vector),
        ),
    )

    memory_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return memory_id


# ============================================================
# PROVENANCE
#
# Links a derived fact/knowledge/memory back to its evidence.
# ============================================================

def add_provenance(
    target_type,
    target_id,
    source_type,
    source_id,
    relation,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO provenance_links (
            target_type,
            target_id,
            source_type,
            source_id,
            relation
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            target_type,
            target_id,
            source_type,
            source_id,
            relation,
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# PLAYER SELF-DECLARED FACT
#
# Important:
# A player declaring something about THEIR OWN persona can
# establish canonical persona truth.
#
# It does NOT automatically inject that truth into every NPC's
# mind. NPC knowledge is recorded separately.
# ============================================================

def record_player_self_fact(
    player_persona_id,
    content,
    source_message_id=None,
    predicate=None,
):
    fact_id = add_canonical_fact(
        subject_type="player_persona",
        subject_id=player_persona_id,
        predicate=predicate,
        content=content,
        source_type="player_self",
        source_id=source_message_id,
        authority=AUTHORITY["player_self"],
        confidence=1.0,
    )

    if source_message_id is not None:
        add_provenance(
            target_type="canonical_fact",
            target_id=fact_id,
            source_type="rp_message",
            source_id=source_message_id,
            relation="declared_in",
        )

    return fact_id


# ============================================================
# NPC HEARS A CLAIM
#
# Hearing something makes it knowledge/belief.
# It does NOT automatically make the claim objectively true.
# ============================================================

def record_heard_claim(
    character_id,
    content,
    source_message_id,
    speaker_type,
    speaker_id,
    speaker_is_subject=False,
    importance=5,
):
    if speaker_is_subject and speaker_type == "player_persona":
        source_type = "player_self"
        knowledge_type = "reported_fact"
        confidence = 0.95
    else:
        source_type = "other_character_claim"
        knowledge_type = "claim"
        confidence = 0.65

    knowledge_id = add_character_knowledge(
        character_id=character_id,
        content=content,
        knowledge_type=knowledge_type,
        source_type=source_type,
        source_id=source_message_id,
        subject_type=speaker_type,
        subject_id=speaker_id,
        confidence=confidence,
        importance=importance,
    )

    add_provenance(
        target_type="character_knowledge",
        target_id=knowledge_id,
        source_type="rp_message",
        source_id=source_message_id,
        relation="heard_in",
    )

    return knowledge_id


# ============================================================
# AI DIALOGUE
#
# An AI saying something is NEVER automatically promoted to
# canonical truth.
# ============================================================

def record_ai_statement_as_dialogue_only():
    return None


# ============================================================
# RETRIEVAL FOR ONE NPC
# ============================================================

def retrieve_for_character(
    character_id,
    query,
    memory_limit=6,
    knowledge_limit=8,
):
    memories = search_character_memories(
        character_id,
        query,
        limit=memory_limit,
    )

    knowledge = search_character_knowledge(
        character_id,
        query,
        limit=knowledge_limit,
    )

    return {
        "memories": memories,
        "knowledge": knowledge,
    }