from __future__ import annotations

import discord

from discord_identity import ensure_character_discord_binding


class SeventhGateCharacterClient(discord.Client):
    """
    Shared Discord shell for Seventh Gate character bots.

    This class currently owns safe Discord identity startup and an optional
    diagnostic ping. RP routing will be added on top of this shared shell,
    rather than creating separate Discord architectures per character.
    """

    def __init__(
        self,
        *,
        character_id,
        diagnostic_trigger=None,
        diagnostic_response=None,
        intents=None,
    ):
        if intents is None:
            intents = discord.Intents.default()
            intents.message_content = True

        super().__init__(intents=intents)

        self.character_id = int(character_id)
        self.diagnostic_trigger = (
            None
            if diagnostic_trigger is None
            else str(diagnostic_trigger).strip().casefold()
        )
        self.diagnostic_response = (
            None
            if diagnostic_response is None
            else str(diagnostic_response)
        )
        self.identity_ready = False
        self.binding_result = None

    async def on_ready(self):
        if self.user is None:
            print(
                "FATAL: Discord connected without a bot user identity."
            )
            await self.close()
            return

        try:
            result = ensure_character_discord_binding(
                self.character_id,
                str(self.user.id),
            )
        except Exception as exc:
            print()
            print(
                "FATAL: Seventh Gate refused the Discord identity binding."
            )
            print(
                f"{type(exc).__name__}: {exc}"
            )
            print(
                "The bot will disconnect rather than overwrite a "
                "character binding."
            )
            await self.close()
            return

        self.binding_result = result
        self.identity_ready = True

        print(f"Logged in as {self.user}")
        print(
            "Seventh Gate character: "
            f"{result.character_name} (ID {result.character_id})"
        )
        print(
            "Discord identity: "
            f"{result.status} ({result.discord_bot_user_id})"
        )

    async def on_message(self, message):
        if not self.identity_ready:
            return

        if message.author.bot:
            return

        if (
            self.diagnostic_trigger
            and self.diagnostic_response
            and str(message.content or "").strip().casefold()
            == self.diagnostic_trigger
        ):
            await message.channel.send(
                self.diagnostic_response
            )


def run_character_bot(
    *,
    token,
    character_id,
    diagnostic_trigger=None,
    diagnostic_response=None,
):
    token = str(token or "").strip()

    if not token:
        raise RuntimeError(
            "Discord bot token is missing."
        )

    client = SeventhGateCharacterClient(
        character_id=character_id,
        diagnostic_trigger=diagnostic_trigger,
        diagnostic_response=diagnostic_response,
    )

    client.run(token)
