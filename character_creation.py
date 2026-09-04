from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Optional
from characters import add_trait,set_attribute,set_skill
from character_profiles import set_character_profile
from database import get_connection
from development import set_development_profile
from life import set_birth_date

@dataclass(frozen=True)
class CreatedCharacter:
    character_id:int
    name:str

CHARACTER_TEXT_FIELDS=(
    "description","personality","background","appearance","speech_style",
    "goals","fears","values_beliefs","habits_mannerisms","private_character_notes",
)

def _required(value,label):
    value=str(value or "").strip()
    if not value: raise ValueError(f"{label} cannot be empty.")
    return value

def _optional(value):
    if value is None:return None
    value=str(value).strip()
    return value or None

def _fallback_text(value):
    if value is None:return None
    if isinstance(value,str):
        models=[x.strip() for x in value.split(",") if x.strip()]
    else:
        models=[str(x).strip() for x in value if str(x).strip()]
    return ",".join(dict.fromkeys(models)) or None

def create_ai_character(
    name,*,profile_text,discord_bot_user_id=None,preferred_model=None,
    fallback_models=None,birth_date=None,developmental_notes=None,
    ai_participation_mode="deferred",attributes:Optional[Mapping[str,int]]=None,
    skills:Optional[Mapping[str,object]]=None,traits=None,**identity_fields
):
    """Create a generic AI character while preserving its rich authored profile verbatim."""
    name=_required(name,"name")
    unknown=set(identity_fields)-set(CHARACTER_TEXT_FIELDS)
    if unknown:
        raise ValueError("Unsupported character fields: "+", ".join(sorted(unknown)))
    vals={f:_optional(identity_fields.get(f)) for f in CHARACTER_TEXT_FIELDS}
    conn=get_connection()
    try:
        cur=conn.execute("""
            INSERT INTO characters(
                name,discord_bot_user_id,description,personality,background,
                appearance,speech_style,goals,fears,values_beliefs,
                habits_mannerisms,private_character_notes,preferred_model,fallback_models
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            name,_optional(discord_bot_user_id),vals["description"],vals["personality"],
            vals["background"],vals["appearance"],vals["speech_style"],vals["goals"],
            vals["fears"],vals["values_beliefs"],vals["habits_mannerisms"],
            vals["private_character_notes"],_optional(preferred_model),
            _fallback_text(fallback_models)
        ))
        character_id=int(cur.lastrowid); conn.commit()
    finally: conn.close()
    try:
        set_character_profile(character_id,profile_text)
        if birth_date is not None:
            set_birth_date("character",character_id,birth_date)
        set_development_profile(
            character_id,developmental_notes=developmental_notes,
            ai_participation_mode=ai_participation_mode
        )
        for key,value in (attributes or {}).items():
            set_attribute("character",character_id,key,value)
        for key,spec in (skills or {}).items():
            if isinstance(spec,Mapping):
                set_skill("character",character_id,key,spec.get("value",0),notes=spec.get("notes"))
            else:
                set_skill("character",character_id,key,spec)
        for trait in traits or ():
            if isinstance(trait,str):
                add_trait("character",character_id,trait)
            elif isinstance(trait,Mapping):
                add_trait("character",character_id,trait["name"],
                          description=trait.get("description"),
                          mechanical_effect=trait.get("mechanical_effect"))
            else:
                raise ValueError("Each trait must be a string or mapping.")
    except Exception:
        conn=get_connection()
        conn.execute("DELETE FROM characters WHERE id=?",(character_id,))
        conn.commit(); conn.close()
        raise
    return CreatedCharacter(character_id,name)

def bind_character_discord_bot(character_id,discord_bot_user_id):
    value=_required(discord_bot_user_id,"discord_bot_user_id")
    conn=get_connection()
    cur=conn.execute("""
        UPDATE characters SET discord_bot_user_id=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND active=1
    """,(value,int(character_id)))
    conn.commit(); conn.close()
    if cur.rowcount!=1: raise ValueError(f"Character {character_id} does not exist or is inactive.")

def configure_character_models(character_id,*,preferred_model=None,fallback_models=None):
    conn=get_connection()
    cur=conn.execute("""
        UPDATE characters SET preferred_model=?,fallback_models=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND active=1
    """,(_optional(preferred_model),_fallback_text(fallback_models),int(character_id)))
    conn.commit(); conn.close()
    if cur.rowcount!=1: raise ValueError(f"Character {character_id} does not exist or is inactive.")
