import os
import time
import asyncio
import requests
import discord

from dotenv import load_dotenv
from database import (
    get_connection,
    initialize_database,
    semantic_memory_search,
)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HORDE_API_KEY = os.getenv("HORDE_API_KEY")

MODEL = "aphrodite/TheDrummer/Skyfall-31B-v4.2"
CHARACTER_ID = 1

RECENT_MESSAGE_LIMIT = 20
MEMORY_RESULT_LIMIT = 8

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

HORDE_HEADERS = {
    "apikey": HORDE_API_KEY,
    "Client-Agent": "SeventhGateRP:0.1",
    "Content-Type": "application/json",
}


def log_message(
    discord_message_id,
    channel_id,
    author_type,
    author_id,
    author_name,
    content,
    character_id=None,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT OR IGNORE INTO rp_messages (
            discord_message_id,
            channel_id,
            author_type,
            author_id,
            author_name,
            character_id,
            content
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(discord_message_id),
            str(channel_id),
            author_type,
            str(author_id),
            author_name,
            character_id,
            content,
        ),
    )

    conn.commit()
    conn.close()


def get_recent_messages(channel_id, limit=RECENT_MESSAGE_LIMIT):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            author_type,
            author_name,
            content,
            character_id
        FROM rp_messages
        WHERE channel_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(channel_id), limit),
    ).fetchall()

    conn.close()

    return list(reversed(rows))


def build_conversation_history(messages):
    history = []

    for row in messages:
        content = row["content"].strip()

        if not content:
            continue

        if row["author_type"] == "character":
            speaker = "Character"
        else:
            speaker = row["author_name"]

        history.append(f"{speaker}: {content}")

    return "\n".join(history)


def build_memory_context(memories):
    if not memories:
        return "No relevant long-term memories were found."

    lines = []

    for memory in memories:
        lines.append(
            f"- {memory['content']} "
            f"(importance {memory['importance']}, "
            f"similarity {memory['similarity']:.3f})"
        )

    return "\n".join(lines)


def generate_horde_reply(conversation_history, memory_context):
    prompt = (
        "You are a temporary test character in a Discord roleplay system.\n"
        "Reply naturally and conversationally.\n"
        "Do not explain that you are an AI or language model.\n"
        "Use both the recent conversation and relevant long-term memories.\n"
        "Treat established facts as true unless someone later corrects them.\n"
        "Do not invent facts merely because you do not know something.\n"
        "If a memory is relevant to the current question, use it.\n"
        "Respond ONLY as Character.\n"
        "Do not write dialogue for the human participants.\n"
        "Do not invent additional Human: or Character: exchanges.\n"
        "Keep the response fairly short for now.\n\n"
        "RELEVANT LONG-TERM MEMORIES:\n"
        f"{memory_context}\n\n"
        "RECENT CONVERSATION:\n"
        f"{conversation_history}\n\n"
        "Character:"
    )

    payload = {
        "prompt": prompt,
        "models": [MODEL],
        "params": {
            "max_length": 180,
            "temperature": 0.75,
            "stop_sequence": [
                "\nHuman:",
                "\nUser:",
                "\nkikorangi.xo:",
            ],
        },
        "trusted_workers": False,
        "slow_workers": True,
    }

    response = requests.post(
        "https://aihorde.net/api/v2/generate/text/async",
        headers=HORDE_HEADERS,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()
    request_id = response.json()["id"]

    while True:
        check = requests.get(
            f"https://aihorde.net/api/v2/generate/text/status/{request_id}",
            headers=HORDE_HEADERS,
            timeout=30,
        )

        check.raise_for_status()
        data = check.json()

        if data.get("done"):
            generations = data.get("generations", [])

            if not generations:
                return "The Horde returned no response."

            return generations[0]["text"].strip()

        time.sleep(2)


@client.event
async def on_ready():
    initialize_database()
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    print(f"SAW MESSAGE: {message.author} -> {message.content}")

    log_message(
        discord_message_id=message.id,
        channel_id=message.channel.id,
        author_type="player",
        author_id=message.author.id,
        author_name=str(message.author),
        content=message.content,
    )

    if not client.user.mentioned_in(message):
        return

    clean_text = message.content

    for mention in message.mentions:
        clean_text = clean_text.replace(f"<@{mention.id}>", "")
        clean_text = clean_text.replace(f"<@!{mention.id}>", "")

    clean_text = clean_text.strip()

    if not clean_text:
        clean_text = "Hello."

    recent_messages = get_recent_messages(message.channel.id)
    conversation_history = build_conversation_history(recent_messages)

    print("\nSearching long-term memory...")
    relevant_memories = await asyncio.to_thread(
        semantic_memory_search,
        CHARACTER_ID,
        clean_text,
        MEMORY_RESULT_LIMIT,
    )

    memory_context = build_memory_context(relevant_memories)

    print("\n--- LONG-TERM MEMORIES ---")
    print(memory_context)
    print("--------------------------\n")

    print("--- RECENT CONTEXT ---")
    print(conversation_history)
    print("----------------------\n")

    async with message.channel.typing():
        try:
            reply = await asyncio.to_thread(
                generate_horde_reply,
                conversation_history,
                memory_context,
            )
        except Exception as e:
            print(f"HORDE ERROR: {e}")
            await message.channel.send(
                "Something went wrong talking to the Horde."
            )
            return

    print(f"HORDE REPLY: {reply}")

    sent_message = await message.channel.send(reply)

    log_message(
        discord_message_id=sent_message.id,
        channel_id=sent_message.channel.id,
        author_type="character",
        author_id=client.user.id,
        author_name=str(client.user),
        content=reply,
        character_id=CHARACTER_ID,
    )


client.run(DISCORD_TOKEN)