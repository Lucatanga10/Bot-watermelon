"""Sistema ticket panel per Watermelon.

Comandi:
  /panel create        — crea nuovo pannello (modal)
  /panel option add    — aggiunge una voce (ruolo acquistabile) al pannello
  /panel option remove — rimuove una voce
  /panel list          — elenca pannelli
  /panel send          — posta il pannello in un canale (embed + select menu)
  /panel delete        — elimina un pannello
  /ticket close        — chiude il ticket corrente (anche via bottone)

Pannelli e ticket sono persistenti: le View sono registrate all'avvio del bot
in bot.py con add_view() usando custom_id fissi.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import storage

log = logging.getLogger("watermelon.tickets")

PANELS_KEY = "panels"
TICKETS_KEY = "tickets"

DEFAULT_COLOR = 0xE74C3C  # rosso Watermelon
GREEN = 0x2ECC71


def parse_color(value: str | None, fallback: int = DEFAULT_COLOR) -> int:
    if not value:
        return fallback
    v = value.strip().lstrip("#")
    try:
        return int(v, 16)
    except ValueError:
        return fallback


async def get_panels() -> dict[str, dict[str, Any]]:
    return await storage.load(PANELS_KEY, {})


async def save_panels(panels: dict[str, dict[str, Any]]) -> None:
    await storage.save(PANELS_KEY, panels)


async def get_tickets() -> dict[str, dict[str, Any]]:
    return await storage.load(TICKETS_KEY, {})


async def save_tickets(tickets: dict[str, dict[str, Any]]) -> None:
    await storage.save(TICKETS_KEY, tickets)


# ---------------------------------------------------------------------------
# View persistente per il PANNELLO (select con le opzioni ruolo)
# ---------------------------------------------------------------------------
class PanelSelect(discord.ui.Select):
    def __init__(self) -> None:
        # Le opzioni reali le mettiamo prima dell'invio. Placeholder qui.
        super().__init__(
            custom_id="watermelon:panel_select",
            placeholder="Scegli il ruolo per cui aprire il ticket…",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="placeholder", value="_")],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await handle_panel_selection(interaction, self.values[0])


class PanelView(discord.ui.View):
    """View persistente: rimane viva anche dopo restart del bot."""

    def __init__(self, bot: Optional[commands.Bot] = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(PanelSelect())


# ---------------------------------------------------------------------------
# View persistente per i CONTROLLI del ticket (close / claim)
# ---------------------------------------------------------------------------
class TicketControlView(discord.ui.View):
    def __init__(self, bot: Optional[commands.Bot] = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Chiudi ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="watermelon:ticket_close",
    )
    async def close_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await close_ticket(interaction)

    @discord.ui.button(
        label="Prendi in carico",
        style=discord.ButtonStyle.success,
        emoji="🎫",
        custom_id="watermelon:ticket_claim",
    )
    async def claim_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await claim_ticket(interaction)


# ---------------------------------------------------------------------------
# Modal creazione pannello
# ---------------------------------------------------------------------------
# Panel create ora usa parametri slash diretti (niente modal).


# ---------------------------------------------------------------------------
# Gestione selezione dal pannello: crea il ticket
# ---------------------------------------------------------------------------
async def handle_panel_selection(interaction: discord.Interaction, value: str) -> None:
    # value = f"{panel_id}:{option_index}"
    if ":" not in value:
        await interaction.response.send_message(
            "❌ Opzione non riconosciuta (pannello obsoleto?).", ephemeral=True
        )
        return

    panel_id, idx_s = value.split(":", 1)
    if not idx_s.isdigit():
        await interaction.response.send_message("❌ Opzione non valida.", ephemeral=True)
        return
    idx = int(idx_s)

    panels = await get_panels()
    panel = panels.get(panel_id)
    if not panel or idx >= len(panel.get("options", [])):
        await interaction.response.send_message(
            "❌ Pannello o opzione non trovata.", ephemeral=True
        )
        return

    option = panel["options"][idx]
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "❌ Devi usarlo dentro il server.", ephemeral=True
        )
        return

    # Ha già un ticket aperto per questo pannello/opzione?
    tickets = await get_tickets()
    for tid, t in tickets.items():
        if (
            t.get("user_id") == interaction.user.id
            and t.get("panel_id") == panel_id
            and t.get("option_index") == idx
            and t.get("open", True)
        ):
            ch = guild.get_channel(t.get("channel_id", 0))
            if ch is not None:
                await interaction.response.send_message(
                    f"⚠️ Hai già un ticket aperto: {ch.mention}", ephemeral=True
                )
                return

    await interaction.response.defer(ephemeral=True, thinking=True)

    category = guild.get_channel(panel["category_id"])
    if not isinstance(category, discord.CategoryChannel):
        await interaction.followup.send(
            "❌ Categoria configurata non trovata. Contatta uno staff.", ephemeral=True
        )
        return

    # Permessi
    overwrites: dict[Any, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
            read_message_history=True,
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
    }
    for rid in panel.get("staff_role_ids", []):
        role = guild.get_role(int(rid))
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

    safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum() or c in "-_")[:20] or "user"
    ch_name = f"🎫-{option['label'][:20].lower().replace(' ', '-')}-{safe_name}"

    try:
        channel = await guild.create_text_channel(
            name=ch_name[:95],
            category=category,
            overwrites=overwrites,
            reason=f"Ticket aperto da {interaction.user} per {option['label']}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Non ho i permessi per creare canali in quella categoria.",
            ephemeral=True,
        )
        return
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Errore creazione canale: {e}", ephemeral=True)
        return

    ticket_id = uuid.uuid4().hex[:8]
    tickets[ticket_id] = {
        "id": ticket_id,
        "guild_id": guild.id,
        "channel_id": channel.id,
        "user_id": interaction.user.id,
        "panel_id": panel_id,
        "option_index": idx,
        "option_label": option["label"],
        "open": True,
        "claimed_by": None,
    }
    await save_tickets(tickets)

    price_line = f"\n**Prezzo:** {option['price']}" if option.get("price") else ""
    role_line = ""
    if option.get("role_id"):
        role_line = f"\n**Ruolo richiesto:** <@&{option['role_id']}>"

    embed = discord.Embed(
        title=f"🎫 Ticket · {option['label']}",
        description=(
            f"Ciao {interaction.user.mention}!\n\n"
            f"Hai aperto un ticket per: **{option['label']}**."
            f"{role_line}{price_line}\n\n"
            "Descrivi la tua richiesta qui sotto. Uno staff ti risponderà appena possibile.\n"
            "Usa il bottone **Chiudi ticket** per chiudere quando hai finito."
        ),
        color=panel.get("color", DEFAULT_COLOR),
    )
    if panel.get("image"):
        embed.set_image(url=panel["image"])
    embed.set_footer(text=f"Watermelon · ticket {ticket_id}")

    staff_mentions = " ".join(f"<@&{rid}>" for rid in panel.get("staff_role_ids", []))
    content = f"{interaction.user.mention} {staff_mentions}".strip()

    await channel.send(
        content=content,
        embed=embed,
        view=TicketControlView(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )

    await interaction.followup.send(
        f"✅ Ticket creato: {channel.mention}", ephemeral=True
    )


async def claim_ticket(interaction: discord.Interaction) -> None:
    tickets = await get_tickets()
    ticket = next(
        (t for t in tickets.values() if t.get("channel_id") == interaction.channel_id),
        None,
    )
    if ticket is None:
        await interaction.response.send_message(
            "❌ Questo non è un ticket.", ephemeral=True
        )
        return

    panels = await get_panels()
    panel = panels.get(ticket["panel_id"], {})
    staff_ids = {int(r) for r in panel.get("staff_role_ids", [])}
    member = interaction.user
    is_staff = isinstance(member, discord.Member) and (
        member.guild_permissions.manage_channels
        or any(r.id in staff_ids for r in member.roles)
    )
    if not is_staff:
        await interaction.response.send_message(
            "❌ Solo lo staff può prendere in carico.", ephemeral=True
        )
        return

    if ticket.get("claimed_by"):
        await interaction.response.send_message(
            f"⚠️ Ticket già preso da <@{ticket['claimed_by']}>.", ephemeral=True
        )
        return

    ticket["claimed_by"] = interaction.user.id
    await save_tickets(tickets)

    embed = discord.Embed(
        description=f"🎫 Ticket preso in carico da {interaction.user.mention}.",
        color=GREEN,
    )
    await interaction.response.send_message(embed=embed)


async def close_ticket(interaction: discord.Interaction) -> None:
    tickets = await get_tickets()
    ticket_id = None
    for tid, t in tickets.items():
        if t.get("channel_id") == interaction.channel_id:
            ticket_id = tid
            break

    if ticket_id is None:
        await interaction.response.send_message(
            "❌ Questo non è un ticket.", ephemeral=True
        )
        return

    ticket = tickets[ticket_id]
    ticket["open"] = False
    await save_tickets(tickets)

    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"🔒 Ticket in chiusura da {interaction.user.mention}… "
            "canale eliminato tra 5 secondi.",
            color=DEFAULT_COLOR,
        )
    )

    import asyncio as _a
    await _a.sleep(5)
    try:
        if interaction.channel is not None:
            await interaction.channel.delete(reason=f"Ticket chiuso da {interaction.user}")
    except (discord.Forbidden, discord.HTTPException):
        pass


# ---------------------------------------------------------------------------
# Cog con i comandi
# ---------------------------------------------------------------------------
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    panel = app_commands.Group(
        name="panel",
        description="Gestione pannelli ticket Watermelon",
        default_permissions=discord.Permissions(manage_guild=True),
    )
    option = app_commands.Group(
        name="option",
        description="Gestione opzioni dei pannelli",
        parent=panel,
    )

    # --- CREATE -----------------------------------------------------------
    @panel.command(name="create", description="Crea un nuovo pannello ticket.")
    @app_commands.describe(
        category="Categoria dove verranno creati i canali ticket",
        titolo="Titolo dell'embed del pannello",
        descrizione="Testo dell'embed (usa \\n per andare a capo)",
        messaggio="Testo sopra l'embed (facoltativo)",
        colore="Colore hex (facoltativo, default rosso)",
        image="Immagine/GIF banner per l'embed (facoltativa)",
    )
    async def panel_create(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        titolo: str,
        descrizione: str,
        messaggio: Optional[str] = None,
        colore: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
    ) -> None:
        image_url = ""
        if image is not None:
            ct = (image.content_type or "").lower()
            if not ct.startswith("image/"):
                await interaction.response.send_message(
                    "❌ L'allegato deve essere un'immagine o GIF.", ephemeral=True
                )
                return
            image_url = image.url

        panel_id = uuid.uuid4().hex[:8]
        panels = await get_panels()
        panels[panel_id] = {
            "id": panel_id,
            "guild_id": interaction.guild_id,
            "title": titolo,
            "description": descrizione.replace("\\n", "\n"),
            "content": (messaggio.replace("\\n", "\n") if messaggio else None),
            "image": image_url or None,
            "color": parse_color(colore),
            "category_id": category.id,
            "staff_role_ids": [],
            "options": [],
        }
        await save_panels(panels)

        await interaction.response.send_message(
            f"✅ Pannello creato con id **`{panel_id}`**.\n"
            f"Ora aggiungi le opzioni con `/panel option add panel_id:{panel_id} …`\n"
            f"Quando è pronto: `/panel send panel_id:{panel_id} channel:#canale`.",
            ephemeral=True,
        )

    # --- LIST -------------------------------------------------------------
    @panel.command(name="list", description="Elenca i pannelli creati.")
    async def panel_list(self, interaction: discord.Interaction) -> None:
        panels = await get_panels()
        mine = [p for p in panels.values() if p.get("guild_id") == interaction.guild_id]
        if not mine:
            await interaction.response.send_message(
                "Nessun pannello. Crealo con `/panel create`.", ephemeral=True
            )
            return
        lines = [
            f"• `{p['id']}` — **{p['title']}** — {len(p.get('options', []))} opzioni"
            for p in mine
        ]
        await interaction.response.send_message(
            "\n".join(lines), ephemeral=True
        )

    # --- DELETE -----------------------------------------------------------
    @panel.command(name="delete", description="Elimina un pannello.")
    @app_commands.describe(panel_id="ID del pannello da eliminare")
    async def panel_delete(
        self, interaction: discord.Interaction, panel_id: str
    ) -> None:
        panels = await get_panels()
        if panel_id not in panels:
            await interaction.response.send_message("❌ Pannello non trovato.", ephemeral=True)
            return
        del panels[panel_id]
        await save_panels(panels)
        await interaction.response.send_message(
            f"🗑️ Pannello `{panel_id}` eliminato.", ephemeral=True
        )

    # --- STAFF ROLE -------------------------------------------------------
    @panel.command(
        name="staff",
        description="Aggiungi o rimuovi un ruolo staff che vede i ticket del pannello.",
    )
    @app_commands.describe(
        panel_id="ID del pannello",
        role="Ruolo staff",
        action="Aggiungi o rimuovi",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ]
    )
    async def panel_staff(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        role: discord.Role,
        action: app_commands.Choice[str],
    ) -> None:
        panels = await get_panels()
        panel = panels.get(panel_id)
        if panel is None:
            await interaction.response.send_message("❌ Pannello non trovato.", ephemeral=True)
            return
        staff = set(panel.get("staff_role_ids", []))
        if action.value == "add":
            staff.add(role.id)
        else:
            staff.discard(role.id)
        panel["staff_role_ids"] = list(staff)
        await save_panels(panels)
        await interaction.response.send_message(
            f"✅ Staff aggiornato ({len(staff)} ruoli).", ephemeral=True
        )

    # --- OPTION ADD -------------------------------------------------------
    @option.command(name="add", description="Aggiungi una voce (ruolo acquistabile) al pannello.")
    @app_commands.describe(
        panel_id="ID del pannello",
        label="Nome mostrato nel menu (es. Admin, Mod, VIP)",
        role="Ruolo da assegnare quando si compra",
        price="Prezzo mostrato nel ticket (facoltativo, es. €10)",
        emoji="Emoji facoltativa nel menu (es. 🛡️)",
        description="Sottotitolo mostrato nel menu (facoltativo)",
    )
    async def option_add(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        label: str,
        role: discord.Role,
        price: Optional[str] = None,
        emoji: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        panels = await get_panels()
        panel = panels.get(panel_id)
        if panel is None:
            await interaction.response.send_message("❌ Pannello non trovato.", ephemeral=True)
            return

        options = panel.setdefault("options", [])
        if len(options) >= 25:
            await interaction.response.send_message(
                "❌ Massimo 25 opzioni per pannello (limite Discord).", ephemeral=True
            )
            return

        options.append(
            {
                "label": label[:80],
                "role_id": role.id,
                "price": price,
                "emoji": emoji,
                "description": (description or "")[:100] or None,
            }
        )
        await save_panels(panels)
        await interaction.response.send_message(
            f"✅ Opzione **{label}** aggiunta al pannello `{panel_id}` "
            f"(totale: {len(options)}).",
            ephemeral=True,
        )

    # --- OPTION REMOVE ----------------------------------------------------
    @option.command(name="remove", description="Rimuovi una voce dal pannello.")
    @app_commands.describe(panel_id="ID del pannello", index="Indice (parte da 0)")
    async def option_remove(
        self, interaction: discord.Interaction, panel_id: str, index: int
    ) -> None:
        panels = await get_panels()
        panel = panels.get(panel_id)
        if panel is None or index < 0 or index >= len(panel.get("options", [])):
            await interaction.response.send_message("❌ Non trovato.", ephemeral=True)
            return
        removed = panel["options"].pop(index)
        await save_panels(panels)
        await interaction.response.send_message(
            f"🗑️ Rimossa **{removed['label']}**.", ephemeral=True
        )

    # --- OPTION LIST ------------------------------------------------------
    @option.command(name="list", description="Elenca le opzioni di un pannello.")
    async def option_list(
        self, interaction: discord.Interaction, panel_id: str
    ) -> None:
        panels = await get_panels()
        panel = panels.get(panel_id)
        if panel is None:
            await interaction.response.send_message("❌ Pannello non trovato.", ephemeral=True)
            return
        opts = panel.get("options", [])
        if not opts:
            await interaction.response.send_message(
                "Nessuna opzione. Aggiungile con `/panel option add`.", ephemeral=True
            )
            return
        lines = []
        for i, o in enumerate(opts):
            emo = f"{o['emoji']} " if o.get("emoji") else ""
            price = f" — {o['price']}" if o.get("price") else ""
            lines.append(f"`{i}` · {emo}**{o['label']}** <@&{o['role_id']}>{price}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # --- SEND -------------------------------------------------------------
    @panel.command(name="send", description="Posta il pannello in un canale.")
    @app_commands.describe(
        panel_id="ID del pannello",
        channel="Canale in cui postarlo",
    )
    async def panel_send(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        channel: discord.TextChannel,
    ) -> None:
        panels = await get_panels()
        panel = panels.get(panel_id)
        if panel is None:
            await interaction.response.send_message("❌ Pannello non trovato.", ephemeral=True)
            return
        opts = panel.get("options", [])
        if not opts:
            await interaction.response.send_message(
                "❌ Aggiungi almeno un'opzione prima con `/panel option add`.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=panel["title"],
            description=panel["description"],
            color=panel.get("color", DEFAULT_COLOR),
        )
        if panel.get("image"):
            embed.set_image(url=panel["image"])
        embed.set_footer(text="Watermelon · Ticket Panel")

        # Costruiamo la view "live" col select popolato
        view = PanelView(self.bot)
        select: PanelSelect = view.children[0]  # type: ignore[assignment]
        select.options = [
            discord.SelectOption(
                label=o["label"],
                value=f"{panel_id}:{i}",
                description=o.get("description") or None,
                emoji=o.get("emoji") or None,
            )
            for i, o in enumerate(opts)
        ]
        select.placeholder = "Scegli il ruolo per cui aprire il ticket…"

        try:
            await channel.send(
                content=panel.get("content") or None,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Non ho i permessi per postare in quel canale.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Pannello postato in {channel.mention}.", ephemeral=True
        )

    # --- TICKET CLOSE (comando slash) ------------------------------------
    @app_commands.command(name="close", description="Chiudi il ticket corrente.")
    async def close_cmd(self, interaction: discord.Interaction) -> None:
        await close_ticket(interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
