from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from database import get_connection

MAX_PROFILE_CHARS = 12000

@dataclass(frozen=True)
class CharacterProfile:
    character_id: int
    profile_text: str
    source_name: Optional[str] = None

def initialize_character_profile_storage():
    conn=get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS character_profiles (
            character_id INTEGER PRIMARY KEY,
            profile_text TEXT NOT NULL,
            source_name TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
        )
    """)
    conn.commit(); conn.close()

def _require_character(character_id):
    character_id=int(character_id)
    conn=get_connection()
    row=conn.execute(
        "SELECT id, name FROM characters WHERE id=? AND active=1",
        (character_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"Character {character_id} does not exist or is inactive.")
    return row

def _clean_profile_text(profile_text):
    text=str(profile_text or "").strip()
    if not text:
        raise ValueError("Character profile text cannot be empty.")
    if len(text)>MAX_PROFILE_CHARS:
        raise ValueError(f"Character profile exceeds the {MAX_PROFILE_CHARS}-character limit.")
    return text

def set_character_profile(character_id, profile_text, *, source_name=None):
    _require_character(character_id)
    initialize_character_profile_storage()
    text=_clean_profile_text(profile_text)
    source_name=None if source_name is None else str(source_name).strip() or None
    conn=get_connection()
    conn.execute("""
        INSERT INTO character_profiles(character_id,profile_text,source_name)
        VALUES(?,?,?)
        ON CONFLICT(character_id) DO UPDATE SET
            profile_text=excluded.profile_text,
            source_name=excluded.source_name,
            updated_at=CURRENT_TIMESTAMP
    """,(int(character_id),text,source_name))
    conn.commit(); conn.close()
    return get_character_profile(character_id)

def import_character_profile_file(character_id,path):
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Character profile file not found: {path}")
    return set_character_profile(
        character_id,path.read_text(encoding="utf-8"),source_name=path.name
    )

def get_character_profile(character_id):
    _require_character(character_id)
    initialize_character_profile_storage()
    conn=get_connection()
    row=conn.execute(
        "SELECT character_id,profile_text,source_name FROM character_profiles WHERE character_id=?",
        (int(character_id),)
    ).fetchone()
    conn.close()
    if row is None: return None
    return CharacterProfile(int(row["character_id"]),row["profile_text"],row["source_name"])

def delete_character_profile(character_id):
    _require_character(character_id); initialize_character_profile_storage()
    conn=get_connection()
    conn.execute("DELETE FROM character_profiles WHERE character_id=?",(int(character_id),))
    conn.commit(); conn.close()
