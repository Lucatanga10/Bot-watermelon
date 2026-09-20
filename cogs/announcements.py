"""Sistema annunci per Watermelon.

Comando:
  /annuncio          — annuncio con embed che tagga @everyone/@here.
                       Tutti i campi (titolo, testo, footer, colore, ecc.)
                       sono parametri del comando slash.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

RED = 0xE74C3C
GREEN = 0x2ECC71


def parse_hex(value: str | None, fallback: int) -> int:
    if not value:
        return fallback
    v = value.strip().lstrip("#")
    try:
        return int(v, 16)
    except ValueError:
        return fallback


class Announcements(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="annuncio",
        description="Crea un annuncio con embed che tagga @everyone/@here.",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        tipo="Colore/tono dell'annuncio",
        mention="Chi taggare sopra l'embed",
        titolo="Titolo dell'embed",
        testo="Corpo dell'embed (usa \\n per andare a capo)",
        channel="Canale in cui postare (default: qui)",
        messaggio="Testo sopra l'embed, accanto al ping (facoltativo)",
        footer="Piè di pagina dell'embed (facoltativo)",
        colore="Override colore hex, es. E74C3C (facoltativo)",
        image="Immagine/GIF da mostrare nell'embed (facoltativa)",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="🟢 Verde (positivo)", value="green"),
            app_commands.Choice(name="🔴 Rosso (importante)", value="red"),
            app_commands.Choice(name="⚪ Neutro (custom)", value="neutral"),
        ],
        mention=[
            app_commands.Choice(name="@everyone", value="@everyone"),
            app_commands.Choice(name="@here", value="@here"),
            app_commands.Choice(name="@everyone + @here", value="@everyone @here"),
            app_commands.Choice(name="Nessuno", value="none"),
        ],
    )
    async def annuncio(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        mention: app_commands.Choice[str],
        titolo: str,
        testo: str,
        channel: Optional[discord.TextChannel] = None,
        messaggio: Optional[str] = None,
        footer: Optional[str] = None,
        colore: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
    ) -> None:
        target = channel or (
            interaction.channel
            if isinstance(interaction.channel, discord.TextChannel)
            else None
        )
        if target is None:
            await interaction.response.send_message(
                "❌ Devi specificare un canale testuale.", ephemeral=True
            )
            return

        image_url = ""
        if image is not None:
            ct = (image.content_type or "").lower()
            if not ct.startswith("image/"):
                await interaction.response.send_message(
                    "❌ L'allegato deve essere un'immagine o GIF.", ephemeral=True
                )
                return
            image_url = image.url

        color_map = {"green": GREEN, "red": RED, "neutral": 0x2B2D31}
        base_color = color_map.get(tipo.value, RED)
        color = parse_hex(colore, base_color)

        # Interpreta \n come vero a-capo (Discord slash param è single-line).
        desc_text = testo.replace("\\n", "\n")
        embed = discord.Embed(
            title=titolo,
            description=desc_text,
            color=color,
        )
        if image_url:
            embed.set_image(url=image_url)
        if footer:
            embed.set_footer(text=footer)

        parts = []
        if mention.value != "none":
            parts.append(mention.value)
        if messaggio:
            parts.append(messaggio.replace("\\n", "\n"))
        content = "\n".join(parts) if parts else None

        try:
            await target.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=True, roles=True),
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Non ho i permessi per postare in quel canale.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Annuncio postato in {target.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Announcements(bot))
