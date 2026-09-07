from __future__ import annotations

import discord

from discord_identity import (
    ensure_character_discord_binding,
)
from player_registration import (
    RegistrationError,
    activate_player_registration,
    cancel_player_registration,
    create_pending_player_registration,
    parse_registration_message,
    render_registration_template,
)


class SeventhGateCharacterClient(
    discord.Client
):
    """
    Shared Discord shell for Seventh Gate character bots.

    Sign-in is OOC and is never passed into scene memory/perception.
    """

    def __init__(
        self,
        *,
        character_id,
        diagnostic_trigger=None,
        diagnostic_response=None,
        registration_channel_id=None,
        registered_role_id=None,
        intents=None,
    ):
        if intents is None:
            intents = (
                discord.Intents.default()
            )
            intents.message_content = True

        super().__init__(
            intents=intents
        )

        self.character_id = int(
            character_id
        )

        self.diagnostic_trigger = (
            None
            if diagnostic_trigger is None
            else str(
                diagnostic_trigger
            ).strip().casefold()
        )

        self.diagnostic_response = (
            None
            if diagnostic_response is None
            else str(
                diagnostic_response
            )
        )

        self.registration_channel_id = (
            None
            if registration_channel_id is None
            else int(registration_channel_id)
        )

        self.registered_role_id = (
            None
            if registered_role_id is None
            else int(registered_role_id)
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
            result = (
                ensure_character_discord_binding(
                    self.character_id,
                    str(self.user.id),
                )
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
            f"{result.character_name} "
            f"(ID {result.character_id})"
        )
        print(
            "Discord identity: "
            f"{result.status} "
            f"({result.discord_bot_user_id})"
        )

        if (
            self.registration_channel_id is not None
            and self.registered_role_id is not None
        ):
            print(
                "Registration handler: active "
                f"(channel {self.registration_channel_id}, "
                f"role {self.registered_role_id})"
            )

    async def _send_registration_errors(
        self,
        channel,
        errors,
    ):
        body = "\n".join(
            f"• {error}"
            for error in errors
        )

        await channel.send(
            "Registration not accepted:\n"
            + body
            + "\n\nFix the form and send it again."
        )

    async def _handle_registration(
        self,
        message,
    ):
        content = str(
            message.content or ""
        ).strip()

        if (
            content.casefold()
            in {
                "template",
                "!template",
            }
        ):
            await message.channel.send(
                "Copy this, fill every field, and send it back here:\n\n"
                "```text\n"
                + render_registration_template()
                + "\n```"
            )
            return

        try:
            draft = parse_registration_message(
                content
            )
        except RegistrationError as exc:
            await self._send_registration_errors(
                message.channel,
                exc.errors,
            )
            return

        if message.guild is None:
            await message.channel.send(
                "Registration must be completed inside the Seventh Gate server."
            )
            return

        role = message.guild.get_role(
            self.registered_role_id
        )

        if role is None:
            await message.channel.send(
                "Registration is temporarily unavailable because the "
                "registered-player role could not be found. Please tell an admin."
            )
            return

        member = message.author

        try:
            pending = (
                create_pending_player_registration(
                    str(member.id),
                    str(member),
                    draft,
                )
            )
        except RegistrationError as exc:
            await self._send_registration_errors(
                message.channel,
                exc.errors,
            )
            return

        old_nick = getattr(
            member,
            "nick",
            None,
        )

        role_was_present = (
            role
            in getattr(
                member,
                "roles",
                [],
            )
        )

        nickname_changed = False
        role_added = False

        try:
            await member.edit(
                nick=draft.character_name,
                reason=(
                    "Seventh Gate character registration"
                ),
            )
            nickname_changed = True

            if not role_was_present:
                await member.add_roles(
                    role,
                    reason=(
                        "Seventh Gate character registration"
                    ),
                )
                role_added = True

            activate_player_registration(
                pending.persona_id
            )

        except Exception as exc:
            if role_added:
                try:
                    await member.remove_roles(
                        role,
                        reason=(
                            "Rollback failed Seventh Gate registration"
                        ),
                    )
                except Exception:
                    pass

            if nickname_changed:
                try:
                    await member.edit(
                        nick=old_nick,
                        reason=(
                            "Rollback failed Seventh Gate registration"
                        ),
                    )
                except Exception:
                    pass

            cancel_player_registration(
                pending.persona_id
            )

            await message.channel.send(
                "Registration could not be completed. No character was "
                "activated. An admin may need to check the bot's Manage "
                "Nicknames / Manage Roles permissions and role order.\n"
                f"Error: {type(exc).__name__}"
            )
            return

        await message.channel.send(
            f"{member.mention} registered as "
            f"**{draft.character_name}**. "
            "Your server nickname has been updated and RP access granted."
        )

    async def on_message(
        self,
        message,
    ):
        if not self.identity_ready:
            return

        if message.author.bot:
            return

        if (
            self.registration_channel_id is not None
            and self.registered_role_id is not None
            and message.guild is not None
            and int(message.channel.id)
            == self.registration_channel_id
        ):
            await self._handle_registration(
                message
            )
            return

        if (
            self.diagnostic_trigger
            and self.diagnostic_response
            and str(
                message.content or ""
            ).strip().casefold()
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
    registration_channel_id=None,
    registered_role_id=None,
):
    token = str(
        token or ""
    ).strip()

    if not token:
        raise RuntimeError(
            "Discord bot token is missing."
        )

    client = SeventhGateCharacterClient(
        character_id=character_id,
        diagnostic_trigger=
            diagnostic_trigger,
        diagnostic_response=
            diagnostic_response,
        registration_channel_id=
            registration_channel_id,
        registered_role_id=
            registered_role_id,
    )

    client.run(token)
