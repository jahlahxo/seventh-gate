import json
import os
import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_DB_PATH = Path(__file__).with_name("seventh_gate.db")
DB_PATH = DEFAULT_DB_PATH  # Backward-compatible name; use get_db_path() internally.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_embedding_model = None
_db_path_override = None


def set_database_path(path):
    """Temporarily point Seventh Gate at a different SQLite database.

    Intended primarily for automated tests so production data is never touched.
    All modules that call database.get_connection() will follow this override.
    """
    global _db_path_override
    _db_path_override = Path(path).expanduser().resolve()
    return _db_path_override


def reset_database_path():
    """Clear the runtime database override and return to the configured/default DB."""
    global _db_path_override
    _db_path_override = None


def get_db_path():
    """Return the active database path.

    Priority: runtime override -> SEVENTH_GATE_DB_PATH env var -> default project DB.
    Relative environment paths are resolved relative to this project directory.
    """
    if _db_path_override is not None:
        return _db_path_override

    configured = os.getenv("SEVENTH_GATE_DB_PATH")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
        return path.resolve()

    return DEFAULT_DB_PATH


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# EMBEDDINGS
# ============================================================

def get_embedding_model():
    global _embedding_model

    if _embedding_model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )
        print("Embedding model ready.")

    return _embedding_model


def create_embedding(text):
    model = get_embedding_model()

    vector = model.encode(
        text,
        normalize_embeddings=True,
    )

    return vector.astype(np.float32)


def embedding_to_text(vector):
    return json.dumps(vector.tolist())


def text_to_embedding(value):
    return np.array(
        json.loads(value),
        dtype=np.float32,
    )


# ============================================================
# INITIALIZATION
# ============================================================

def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript(
        """

        -- ===================================================
        -- AI CHARACTERS
        -- ===================================================

        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL UNIQUE,
            discord_bot_user_id TEXT UNIQUE,

            description TEXT,
            personality TEXT,
            background TEXT,
            appearance TEXT,
            speech_style TEXT,

            goals TEXT,
            fears TEXT,
            values_beliefs TEXT,
            habits_mannerisms TEXT,

            private_character_notes TEXT,

            preferred_model TEXT,
            fallback_models TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- HUMAN RP PERSONAS
        -- ===================================================

        CREATE TABLE IF NOT EXISTS player_personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            discord_user_id TEXT NOT NULL,
            discord_name TEXT,

            rp_name TEXT NOT NULL,

            description TEXT,
            appearance TEXT,
            background TEXT,
            personality TEXT,

            family TEXT,
            occupation TEXT,
            social_status TEXT,

            private_player_notes TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_player_personas_discord
        ON player_personas(discord_user_id);


        -- ===================================================
        -- CHARACTER SHEETS
        --
        -- Works for both humans and NPCs.
        -- owner_type = character / player_persona
        -- ===================================================

        CREATE TABLE IF NOT EXISTS character_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,

            stat_name TEXT NOT NULL,
            stat_value INTEGER NOT NULL,

            UNIQUE(owner_type, owner_id, stat_name)
        );


        CREATE TABLE IF NOT EXISTS character_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,

            skill_name TEXT NOT NULL,
            skill_value INTEGER NOT NULL DEFAULT 0,

            notes TEXT,

            UNIQUE(owner_type, owner_id, skill_name)
        );


        CREATE TABLE IF NOT EXISTS character_traits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_type TEXT NOT NULL,
            owner_id INTEGER NOT NULL,

            trait_name TEXT NOT NULL,

            description TEXT,

            mechanical_effect TEXT,

            UNIQUE(owner_type, owner_id, trait_name)
        );



        -- ===================================================
        -- WORLD OBJECTS
        --
        -- Physical things that can exist in locations,
        -- inventories, containers, hands, clothing, etc.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,
            object_type TEXT NOT NULL DEFAULT 'item',

            description TEXT,

            portable INTEGER NOT NULL DEFAULT 1,
            is_container INTEGER NOT NULL DEFAULT 0,
            is_openable INTEGER NOT NULL DEFAULT 0,
            is_lockable INTEGER NOT NULL DEFAULT 0,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_objects_name
        ON objects(name);


        -- ===================================================
        -- OBJECT PLACEMENT / POSSESSION
        --
        -- Exactly one authoritative placement per object.
        --
        -- holder_type examples:
        --   location
        --   character
        --   player_persona
        --   object
        --
        -- relation examples:
        --   at
        --   carried
        --   held
        --   worn
        --   inside
        --   on
        -- ===================================================

        CREATE TABLE IF NOT EXISTS object_placements (
            object_id INTEGER PRIMARY KEY,

            holder_type TEXT NOT NULL,
            holder_id TEXT NOT NULL,

            relation TEXT NOT NULL DEFAULT 'at',

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (object_id)
                REFERENCES objects(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_object_placements_holder
        ON object_placements(holder_type, holder_id);


        -- ===================================================
        -- OBJECT STATE
        --
        -- State that should be authoritative rather than
        -- inferred from prose.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS object_states (
            object_id INTEGER PRIMARY KEY,

            is_open INTEGER,
            is_locked INTEGER,

            condition_name TEXT NOT NULL DEFAULT 'intact',
            condition_level INTEGER NOT NULL DEFAULT 0,

            lock_code TEXT,

            notes TEXT,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (object_id)
                REFERENCES objects(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- CHARACTER / PERSONA CONDITIONS
        --
        -- Persistent bodily or situational conditions such as
        -- injuries, intoxication, exhaustion, restraint,
        -- unconsciousness, illness, etc.
        --
        -- These are objective state. A character's awareness
        -- or belief about them is handled elsewhere.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS entity_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,

            condition_type TEXT NOT NULL,
            name TEXT NOT NULL,

            severity INTEGER NOT NULL DEFAULT 1,
            description TEXT,

            source_world_event_id INTEGER,

            active INTEGER NOT NULL DEFAULT 1,

            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,

            FOREIGN KEY (source_world_event_id)
                REFERENCES world_events(id)
        );

        CREATE INDEX IF NOT EXISTS idx_entity_conditions_owner
        ON entity_conditions(owner_type, owner_id, active);



        -- ===================================================
        -- CAMPAIGN CLOCK
        -- Authoritative fictional time; real-world downtime
        -- never advances it automatically.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS campaign_clock (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_datetime TEXT NOT NULL,
            calendar_name TEXT NOT NULL DEFAULT 'gregorian',
            time_scale REAL NOT NULL DEFAULT 1.0,
            paused INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS campaign_clock_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            old_datetime TEXT NOT NULL,
            new_datetime TEXT NOT NULL,
            seconds_advanced INTEGER NOT NULL,
            reason TEXT,
            source_type TEXT NOT NULL,
            source_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_campaign_clock_events_created
        ON campaign_clock_events(created_at);


        -- ===================================================
        -- CAMPAIGN CONTENT ASSUMPTIONS
        --
        -- These are server/campaign-level facts, not per-scene
        -- prompts. Seventh Gate does not interrupt RP to ask
        -- for runtime consent checks.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS campaign_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- LIFE / AGE PROFILES
        --
        -- General fictional birth-date state used by aging,
        -- reproduction, birthdays and later child development.
        -- Age is derived from the campaign clock rather than
        -- stored as a drifting number.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS entity_life_profiles (
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,

            birth_date TEXT,

            notes TEXT,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (owner_type, owner_id)
        );


        -- ===================================================
        -- MORTALITY / LIFE STATUS
        --
        -- Death is objective world state and is deliberately
        -- separate from the generic "active" flag. A deceased
        -- character remains a persistent historical entity:
        -- memories, relationships, family links and location
        -- history are not deleted merely because they died.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS entity_mortality (
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'living',

            death_datetime TEXT,
            cause_of_death TEXT,
            manner_of_death TEXT,

            world_event_id INTEGER,

            notes TEXT,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (owner_type, owner_id),

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE SET NULL
        );


        -- ===================================================
        -- CHARACTER DEVELOPMENT / LIFECYCLE
        --
        -- Chronological age is derived from birth date + campaign
        -- time. This stores only individual developmental context
        -- and AI-orchestration state.
        --
        -- Developmental grounding constrains plausible comprehension
        -- and expression. It must not prescribe personality, morality,
        -- beliefs, emotions, or choices.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS character_lifecycle_profiles (
            character_id INTEGER PRIMARY KEY,

            developmental_stage_override TEXT,
            developmental_notes TEXT,

            ai_participation_mode TEXT NOT NULL DEFAULT 'deferred',

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- DEVELOPMENTAL MILESTONES
        --
        -- Optional objective story facts. Age alone never invents a
        -- milestone; record one only when it is established in-world.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS developmental_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,

            milestone_type TEXT NOT NULL,
            description TEXT,

            achieved_at TEXT NOT NULL,

            world_event_id INTEGER,
            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_developmental_milestones_character
        ON developmental_milestones(
            character_id,
            achieved_at
        );


        -- ===================================================
        -- REPRODUCTIVE PROFILES
        --
        -- Objective biological/reproductive state for fictional
        -- characters/personas. This is separate from what any
        -- character knows or believes.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS reproductive_profiles (
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,

            can_conceive INTEGER NOT NULL DEFAULT 0,
            can_impregnate INTEGER NOT NULL DEFAULT 0,

            fertility_status TEXT NOT NULL DEFAULT 'normal',
            fertility_modifier REAL NOT NULL DEFAULT 1.0,

            cycle_length_days INTEGER,
            cycle_day INTEGER,

            notes TEXT,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (owner_type, owner_id)
        );


        -- ===================================================
        -- INTIMATE / SEXUAL ENCOUNTERS
        --
        -- Records the objective occurrence and context of an
        -- adult encounter. It does not itself determine
        -- conception and does not grant knowledge to anyone.
        --
        -- consent_context describes the in-fiction situation:
        -- consensual / coercive / nonconsensual / unclear
        -- ===================================================

        CREATE TABLE IF NOT EXISTS intimate_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            world_event_id INTEGER,

            participant_a_type TEXT NOT NULL,
            participant_a_id TEXT NOT NULL,

            participant_b_type TEXT NOT NULL,
            participant_b_id TEXT NOT NULL,

            consent_context TEXT NOT NULL DEFAULT 'consensual',

            pregnancy_possible INTEGER NOT NULL DEFAULT 0,

            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_intimate_events_a
        ON intimate_events(participant_a_type, participant_a_id);

        CREATE INDEX IF NOT EXISTS idx_intimate_events_b
        ON intimate_events(participant_b_type, participant_b_id);


        -- ===================================================
        -- PARTICIPANT-SPECIFIC INTIMATE EXPERIENCE
        --
        -- Subjective experience belongs only to the individual
        -- participant. No subjective state is inferred merely
        -- because an intimate event occurred.
        --
        -- Numeric experience fields use:
        --   NULL = unknown / not established
        --   0-4  = none through very strong
        -- ===================================================

        CREATE TABLE IF NOT EXISTS intimate_experiences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            intimate_event_id INTEGER NOT NULL,

            participant_type TEXT NOT NULL,
            participant_id TEXT NOT NULL,

            willingness TEXT,

            desire_level INTEGER,
            physical_arousal_level INTEGER,
            enjoyment_level INTEGER,
            pain_level INTEGER,

            climax INTEGER,

            emotional_response TEXT,
            private_notes TEXT,

            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (intimate_event_id)
                REFERENCES intimate_events(id)
                ON DELETE CASCADE,

            UNIQUE(
                intimate_event_id,
                participant_type,
                participant_id
            )
        );

        CREATE INDEX IF NOT EXISTS idx_intimate_experiences_participant
        ON intimate_experiences(
            participant_type,
            participant_id
        );

        -- ===================================================
        -- GENERALIZED CONCEPTION CHECKS
        --
        -- This is intentionally independent of intimate_events.
        -- A pregnancy/conception may originate from biological,
        -- assisted, magical, supernatural, imported, unknown,
        -- or other setting-defined causes.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS conception_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            gestational_parent_type TEXT NOT NULL,
            gestational_parent_id TEXT NOT NULL,

            other_parent_type TEXT,
            other_parent_id TEXT,

            source_type TEXT NOT NULL,
            source_id TEXT,

            base_chance REAL NOT NULL,
            age_factor REAL NOT NULL DEFAULT 1.0,
            fertility_factor REAL NOT NULL DEFAULT 1.0,
            final_chance REAL NOT NULL,

            roll REAL NOT NULL,
            conceived INTEGER NOT NULL DEFAULT 0,

            campaign_datetime TEXT NOT NULL,

            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- PREGNANCY ORIGIN / PROVENANCE
        --
        -- One pregnancy can exist without a conception check.
        -- This is what lets pre-existing/imported/unknown or
        -- setting-specific pregnancies exist cleanly.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS pregnancy_origins (
            pregnancy_id INTEGER PRIMARY KEY,

            origin_type TEXT NOT NULL,
            origin_source_type TEXT,
            origin_source_id TEXT,

            conception_check_id INTEGER,

            certainty TEXT NOT NULL DEFAULT 'known',
            description TEXT,

            FOREIGN KEY (pregnancy_id)
                REFERENCES pregnancies(id)
                ON DELETE CASCADE,

            FOREIGN KEY (conception_check_id)
                REFERENCES conception_checks(id)
                ON DELETE SET NULL
        );


        -- ===================================================
        -- PREGNANCIES
        --
        -- Objective pregnancy state only.
        -- Awareness/suspicion belongs in knowledge/memory.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS pregnancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            gestational_parent_type TEXT NOT NULL,
            gestational_parent_id TEXT NOT NULL,

            other_parent_type TEXT,
            other_parent_id TEXT,

            status TEXT NOT NULL DEFAULT 'ongoing',

            conceived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estimated_due_at DATETIME,

            ended_at DATETIME,
            outcome TEXT,

            notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_pregnancies_parent
        ON pregnancies(
            gestational_parent_type,
            gestational_parent_id,
            status
        );


        -- ===================================================
        -- PREGNANCY AWARENESS
        --
        -- Objective pregnancy and knowledge of pregnancy are
        -- separate. Awareness belongs only to the individual
        -- participant and is never granted by conception alone.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS pregnancy_awareness (
            pregnancy_id INTEGER NOT NULL,

            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,

            awareness_state TEXT NOT NULL DEFAULT 'unaware',
            confidence REAL NOT NULL DEFAULT 0.0,

            source_type TEXT NOT NULL,
            source_id TEXT,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (
                pregnancy_id,
                owner_type,
                owner_id
            ),

            FOREIGN KEY (pregnancy_id)
                REFERENCES pregnancies(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- PREGNANCY SIGNS / PRIVATE PERCEPTS
        --
        -- A sign is evidence available to the gestational
        -- character. It does not itself assert what the
        -- character thinks the sign means.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS pregnancy_signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            pregnancy_id INTEGER NOT NULL,

            sign_type TEXT NOT NULL,
            description TEXT NOT NULL,

            gestational_age_days INTEGER NOT NULL,
            severity INTEGER NOT NULL DEFAULT 1,

            private_to_owner INTEGER NOT NULL DEFAULT 1,

            noticed INTEGER NOT NULL DEFAULT 0,
            noticed_at TEXT,

            created_campaign_datetime TEXT NOT NULL,

            FOREIGN KEY (pregnancy_id)
                REFERENCES pregnancies(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pregnancy_signs_pregnancy
        ON pregnancy_signs(pregnancy_id, noticed);


        -- ===================================================
        -- PREGNANCY PROGRESSION / OUTCOMES
        --
        -- Allows gestational milestones, complications, birth,
        -- miscarriage, etc. to be recorded as authoritative
        -- events without encoding them as prose-only facts.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS pregnancy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            pregnancy_id INTEGER NOT NULL,
            world_event_id INTEGER,

            event_type TEXT NOT NULL,
            gestational_age_days INTEGER,

            description TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (pregnancy_id)
                REFERENCES pregnancies(id)
                ON DELETE CASCADE,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE SET NULL
        );


        -- ===================================================
        -- BIRTHS
        --
        -- A birth concludes one pregnancy and can contain one
        -- or more children. Each child has its own birth
        -- outcome, allowing mixed outcomes among multiples.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS births (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            pregnancy_id INTEGER NOT NULL UNIQUE,

            world_event_id INTEGER,
            location_id INTEGER,

            birth_datetime TEXT NOT NULL,

            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (pregnancy_id)
                REFERENCES pregnancies(id)
                ON DELETE CASCADE,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE SET NULL,

            FOREIGN KEY (location_id)
                REFERENCES locations(id)
                ON DELETE SET NULL
        );


        CREATE TABLE IF NOT EXISTS birth_children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            birth_id INTEGER NOT NULL,
            child_character_id INTEGER NOT NULL UNIQUE,

            birth_order INTEGER NOT NULL DEFAULT 1,

            given_name TEXT,

            outcome TEXT NOT NULL DEFAULT 'live_birth',

            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (birth_id)
                REFERENCES births(id)
                ON DELETE CASCADE,

            FOREIGN KEY (child_character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            UNIQUE(birth_id, birth_order)
        );


        -- ===================================================
        -- OBJECTIVE FAMILY / CARE RELATIONSHIPS
        --
        -- These are objective relationship facts, not feelings
        -- or beliefs. A character can believe something
        -- different from family_links; that belongs in the
        -- character knowledge/memory system.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS family_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,

            relative_type TEXT NOT NULL,
            relative_id TEXT NOT NULL,

            relation_type TEXT NOT NULL,

            certainty TEXT NOT NULL DEFAULT 'known',

            source_type TEXT NOT NULL,
            source_id TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            started_at TEXT,
            ended_at TEXT,

            notes TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(
                subject_type,
                subject_id,
                relative_type,
                relative_id,
                relation_type
            )
        );

        CREATE INDEX IF NOT EXISTS idx_family_links_subject
        ON family_links(
            subject_type,
            subject_id,
            active
        );

        CREATE INDEX IF NOT EXISTS idx_family_links_relative
        ON family_links(
            relative_type,
            relative_id,
            active
        );


        -- ===================================================
        -- CANONICAL FACTS
        --
        -- Objective truth.
        -- Does NOT imply NPC knowledge.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS canonical_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            subject_type TEXT NOT NULL,
            subject_id TEXT,

            predicate TEXT,
            content TEXT NOT NULL,

            source_type TEXT NOT NULL,
            source_id TEXT,

            authority INTEGER NOT NULL DEFAULT 50,
            confidence REAL NOT NULL DEFAULT 1.0,

            supersedes_fact_id INTEGER,

            active INTEGER NOT NULL DEFAULT 1,

            embedding TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (supersedes_fact_id)
                REFERENCES canonical_facts(id)
        );

        CREATE INDEX IF NOT EXISTS idx_canonical_subject
        ON canonical_facts(subject_type, subject_id);


        -- ===================================================
        -- NPC KNOWLEDGE / BELIEF
        -- ===================================================

        CREATE TABLE IF NOT EXISTS character_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,

            subject_type TEXT,
            subject_id TEXT,

            content TEXT NOT NULL,

            knowledge_type TEXT NOT NULL,

            source_type TEXT NOT NULL,
            source_id TEXT,

            confidence REAL NOT NULL DEFAULT 1.0,
            importance INTEGER NOT NULL DEFAULT 5,

            is_secret INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,

            embedding TEXT,

            learned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_character_knowledge_owner
        ON character_knowledge(character_id);


        -- ===================================================
        -- EPISODIC NPC MEMORY
        -- ===================================================

        CREATE TABLE IF NOT EXISTS character_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,

            scene_id INTEGER,

            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,

            emotional_context TEXT,

            importance INTEGER NOT NULL DEFAULT 5,
            confidence REAL NOT NULL DEFAULT 1.0,

            source_message_start_id INTEGER,
            source_message_end_id INTEGER,

            embedding TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_character_memories_owner
        ON character_memories(character_id);


        -- ===================================================
        -- RELATIONSHIPS
        -- ===================================================

        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            character_id INTEGER NOT NULL,

            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,

            relationship_label TEXT,
            summary TEXT,

            affection INTEGER NOT NULL DEFAULT 0,
            trust INTEGER NOT NULL DEFAULT 0,
            respect INTEGER NOT NULL DEFAULT 0,
            fear INTEGER NOT NULL DEFAULT 0,
            resentment INTEGER NOT NULL DEFAULT 0,
            attraction INTEGER NOT NULL DEFAULT 0,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            UNIQUE(character_id, target_type, target_id)
        );


        -- ===================================================
        -- WORLD LORE
        -- ===================================================

        CREATE TABLE IF NOT EXISTS world_lore (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT NOT NULL,
            category TEXT NOT NULL,

            content TEXT NOT NULL,

            location_scope TEXT,
            social_scope TEXT,
            time_scope TEXT,

            knowledge_level TEXT NOT NULL DEFAULT 'common',

            authority INTEGER NOT NULL DEFAULT 100,

            embedding TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_world_lore_category
        ON world_lore(category);


        -- ===================================================
        -- WORLD STATE
        -- ===================================================

        CREATE TABLE IF NOT EXISTS world_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            state_key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,

            source_type TEXT NOT NULL,
            source_id TEXT,

            authority INTEGER NOT NULL DEFAULT 100,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- LOCATIONS
        -- ===================================================

        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL UNIQUE,

            parent_location_id INTEGER,

            description TEXT,
            private_notes TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            FOREIGN KEY (parent_location_id)
                REFERENCES locations(id)
        );


        -- ===================================================
        -- LOCATION CONNECTIONS
        --
        -- Describes physical routes AND sensory relationships.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS location_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            from_location_id INTEGER NOT NULL,
            to_location_id INTEGER NOT NULL,

            connection_type TEXT NOT NULL DEFAULT 'passage',

            travel_difficulty INTEGER NOT NULL DEFAULT 0,

            visible_between INTEGER NOT NULL DEFAULT 0,
            audible_between INTEGER NOT NULL DEFAULT 0,

            locked INTEGER NOT NULL DEFAULT 0,
            restricted INTEGER NOT NULL DEFAULT 0,

            notes TEXT,

            FOREIGN KEY (from_location_id)
                REFERENCES locations(id)
                ON DELETE CASCADE,

            FOREIGN KEY (to_location_id)
                REFERENCES locations(id)
                ON DELETE CASCADE,

            UNIQUE(from_location_id, to_location_id)
        );


        -- ===================================================
        -- DISCORD CHANNEL -> WORLD LOCATION
        -- ===================================================

        CREATE TABLE IF NOT EXISTS location_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            location_id INTEGER NOT NULL UNIQUE,
            discord_channel_id TEXT NOT NULL UNIQUE,

            private_location INTEGER NOT NULL DEFAULT 0,

            FOREIGN KEY (location_id)
                REFERENCES locations(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- SCENES
        -- ===================================================

        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            discord_channel_id TEXT NOT NULL,

            title TEXT,

            location_id INTEGER,

            status TEXT NOT NULL DEFAULT 'active',

            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,

            summary TEXT,

            FOREIGN KEY (location_id)
                REFERENCES locations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_scene_channel
        ON scenes(discord_channel_id);


        -- ===================================================
        -- SCENE PARTICIPANTS
        -- ===================================================

        CREATE TABLE IF NOT EXISTS scene_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            scene_id INTEGER NOT NULL,

            participant_type TEXT NOT NULL,
            participant_id TEXT NOT NULL,

            present INTEGER NOT NULL DEFAULT 1,
            conscious INTEGER NOT NULL DEFAULT 1,

            entered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            left_at DATETIME,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id)
                ON DELETE CASCADE,

            UNIQUE(scene_id, participant_type, participant_id)
        );


        -- ===================================================
        -- CURRENT PHYSICAL LOCATION
        --
        -- This enforces one physical location per participant.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS participant_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            participant_type TEXT NOT NULL,
            participant_id TEXT NOT NULL,

            location_id INTEGER NOT NULL,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (location_id)
                REFERENCES locations(id),

            UNIQUE(participant_type, participant_id)
        );


        -- ===================================================
        -- RAW RP HISTORY
        --
        -- Records what was written.
        -- Dialogue itself is NOT objective truth.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS rp_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            discord_message_id TEXT UNIQUE,
            discord_channel_id TEXT NOT NULL,

            scene_id INTEGER,

            author_type TEXT NOT NULL,
            author_id TEXT NOT NULL,
            author_name TEXT,

            character_id INTEGER,
            player_persona_id INTEGER,

            content TEXT NOT NULL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id),

            FOREIGN KEY (character_id)
                REFERENCES characters(id),

            FOREIGN KEY (player_persona_id)
                REFERENCES player_personas(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_scene
        ON rp_messages(scene_id);

        CREATE INDEX IF NOT EXISTS idx_messages_channel
        ON rp_messages(discord_channel_id);


        -- ===================================================
        -- AUTHORITATIVE EVENT LEDGER
        --
        -- This records what ACTUALLY happened.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS world_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            scene_id INTEGER,
            location_id INTEGER,

            event_type TEXT NOT NULL,

            actor_type TEXT,
            actor_id TEXT,

            target_type TEXT,
            target_id TEXT,

            content TEXT NOT NULL,

            outcome TEXT,

            source_type TEXT NOT NULL,
            source_id TEXT,

            authority INTEGER NOT NULL DEFAULT 100,

            embedding TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id),

            FOREIGN KEY (location_id)
                REFERENCES locations(id)
        );

        CREATE INDEX IF NOT EXISTS idx_world_events_scene
        ON world_events(scene_id);

        CREATE INDEX IF NOT EXISTS idx_world_events_location
        ON world_events(location_id);


        -- ===================================================
        -- ACTION ATTEMPTS
        --
        -- The Director records uncertain/contested attempts.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS action_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            scene_id INTEGER,

            actor_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,

            target_type TEXT,
            target_id TEXT,

            action_type TEXT NOT NULL,

            description TEXT NOT NULL,

            difficulty INTEGER,

            opposed INTEGER NOT NULL DEFAULT 0,

            status TEXT NOT NULL DEFAULT 'pending',

            source_message_id INTEGER,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id),

            FOREIGN KEY (source_message_id)
                REFERENCES rp_messages(id)
        );


        -- ===================================================
        -- ACTION RESOLUTIONS / DICE
        -- ===================================================

        CREATE TABLE IF NOT EXISTS action_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            action_attempt_id INTEGER NOT NULL,

            resolution_type TEXT NOT NULL DEFAULT 'roll',

            actor_stat TEXT,
            actor_skill TEXT,

            target_stat TEXT,
            target_skill TEXT,

            actor_roll INTEGER,
            target_roll INTEGER,

            actor_total INTEGER,
            target_total INTEGER,

            difficulty INTEGER,

            degree TEXT NOT NULL,

            outcome TEXT NOT NULL,

            authority_overridden INTEGER NOT NULL DEFAULT 0,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (action_attempt_id)
                REFERENCES action_attempts(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- STATE CHANGES
        --
        -- Auditable changes caused by authoritative events.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            world_event_id INTEGER NOT NULL,

            entity_type TEXT NOT NULL,
            entity_id TEXT,

            field_name TEXT NOT NULL,

            old_value TEXT,
            new_value TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE CASCADE
        );


        -- ===================================================
        -- EVENT WITNESSES
        --
        -- Presence/visibility/audibility determines who
        -- actually perceived an event.
        -- ===================================================

        CREATE TABLE IF NOT EXISTS event_witnesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            world_event_id INTEGER NOT NULL,

            witness_type TEXT NOT NULL,
            witness_id TEXT NOT NULL,

            perception_type TEXT NOT NULL,

            certainty REAL NOT NULL DEFAULT 1.0,

            FOREIGN KEY (world_event_id)
                REFERENCES world_events(id)
                ON DELETE CASCADE,

            UNIQUE(
                world_event_id,
                witness_type,
                witness_id,
                perception_type
            )
        );


        -- ===================================================
        -- PROVENANCE
        -- ===================================================

        CREATE TABLE IF NOT EXISTS provenance_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,

            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,

            relation TEXT NOT NULL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- DIRECTOR / HUMAN WORLD OPERATORS (legacy table name: game_masters)
        -- ===================================================

        CREATE TABLE IF NOT EXISTS game_masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            discord_user_id TEXT NOT NULL UNIQUE,
            discord_name TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );


        -- ===================================================
        -- NPC SCENE CONTROL
        -- ===================================================

        CREATE TABLE IF NOT EXISTS character_scene_control (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            scene_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL,

            participation_mode TEXT NOT NULL DEFAULT 'auto',

            silenced INTEGER NOT NULL DEFAULT 0,

            forced_turn_priority INTEGER,

            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id)
                ON DELETE CASCADE,

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
                ON DELETE CASCADE,

            UNIQUE(scene_id, character_id)
        );


        -- ===================================================
        -- TURN HISTORY
        -- ===================================================

        CREATE TABLE IF NOT EXISTS turn_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            scene_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL,

            reason TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scene_id)
                REFERENCES scenes(id),

            FOREIGN KEY (character_id)
                REFERENCES characters(id)
        );


        -- ===================================================
        -- MODEL PROFILES
        -- ===================================================

        CREATE TABLE IF NOT EXISTS model_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL UNIQUE,

            provider TEXT NOT NULL DEFAULT 'aihorde',
            model_name TEXT NOT NULL,

            context_limit INTEGER,
            response_token_limit INTEGER,

            temperature REAL,

            active INTEGER NOT NULL DEFAULT 1,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        """
    )

    # Compatibility migration: older databases used gm_overridden.
    resolution_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(action_resolutions)"
        ).fetchall()
    }

    if (
        "gm_overridden" in resolution_columns
        and "authority_overridden" not in resolution_columns
    ):
        conn.execute(
            """
            ALTER TABLE action_resolutions
            ADD COLUMN authority_overridden INTEGER NOT NULL DEFAULT 0
            """
        )
        conn.execute(
            """
            UPDATE action_resolutions
            SET authority_overridden = gm_overridden
            """
        )

    conn.commit()
    conn.close()

    print(f"Production database ready: {get_db_path()}")


# ============================================================
# GENERIC SEMANTIC SEARCH
# ============================================================

def semantic_search_rows(
    rows,
    query,
    limit=8,
    minimum_similarity=0.25,
):
    if not rows:
        return []

    query_vector = create_embedding(query)

    results = []

    for row in rows:
        if not row["embedding"]:
            continue

        stored_vector = text_to_embedding(
            row["embedding"]
        )

        similarity = float(
            np.dot(query_vector, stored_vector)
        )

        if similarity < minimum_similarity:
            continue

        results.append(
            {
                "row": row,
                "similarity": similarity,
            }
        )

    results.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return results[:limit]


# ============================================================
# CHARACTER MEMORY SEARCH
# ============================================================

def search_character_memories(
    character_id,
    query,
    limit=8,
):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM character_memories
        WHERE character_id = ?
          AND active = 1
          AND embedding IS NOT NULL
        """,
        (character_id,),
    ).fetchall()

    conn.close()

    return semantic_search_rows(
        rows,
        query,
        limit=limit,
    )


# ============================================================
# CHARACTER KNOWLEDGE SEARCH
# ============================================================

def search_character_knowledge(
    character_id,
    query,
    limit=8,
):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM character_knowledge
        WHERE character_id = ?
          AND active = 1
          AND embedding IS NOT NULL
        """,
        (character_id,),
    ).fetchall()

    conn.close()

    return semantic_search_rows(
        rows,
        query,
        limit=limit,
    )


# ============================================================
# WORLD LORE SEARCH
# ============================================================

def search_world_lore(
    query,
    limit=8,
):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM world_lore
        WHERE active = 1
          AND embedding IS NOT NULL
        """
    ).fetchall()

    conn.close()

    return semantic_search_rows(
        rows,
        query,
        limit=limit,
    )


# ============================================================
# WORLD EVENT SEARCH
# ============================================================

def search_world_events(
    query,
    limit=8,
):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM world_events
        WHERE embedding IS NOT NULL
        """
    ).fetchall()

    conn.close()

    return semantic_search_rows(
        rows,
        query,
        limit=limit,
    )


if __name__ == "__main__":
    initialize_database()