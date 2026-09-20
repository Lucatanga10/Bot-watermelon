import asyncio
import logging
import os
from pathlib import Path

import discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID_RAW = os.getenv("GUILD_ID", "").strip()
GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW.isdigit() else None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("watermelon")


class WatermelonBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=True, users=True, roles=True
            ),
        )
        self.synced = False

    async def setup_hook(self) -> None:
        cogs_dir = Path(__file__).parent / "cogs"
        # Solo veri cog: non file utility.
        cog_modules = {"tickets", "announcements"}
        for file in sorted(cogs_dir.glob("*.py")):
            if file.stem.startswith("_") or file.stem not in cog_modules:
                continue
            ext = f"cogs.{file.stem}"
            try:
                await self.load_extension(ext)
                log.info("Cog caricato: %s", ext)
            except Exception as e:
                log.exception("Errore caricamento %s: %s", ext, e)

        # Register persistent views before sync so buttons/selects survive restart.
        from cogs.tickets import PanelView, TicketControlView
        self.add_view(PanelView(self))
        self.add_view(TicketControlView(self))

        # Sync commands immediately. Guild-scoped = istantaneo, no duplicati.
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info("Sincronizzati %d comandi sulla guild %s", len(synced), GUILD_ID)
            else:
                synced = await self.tree.sync()
                log.info("Sincronizzati %d comandi globali", len(synced))
            self.synced = True
        except Exception as e:
            log.exception("Sync fallita: %s", e)

    async def on_ready(self) -> None:
        log.info("Connesso come %s (id=%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Watermelon Server",
            )
        )


async def _health(_: web.Request) -> web.Response:
    return web.Response(text="Watermelon bot online 🍉")


async def _start_health_server() -> None:
    """Piccolo server HTTP per Render/UptimeRobot: tiene sveglio il worker."""
    port_raw = os.getenv("PORT", "").strip()
    if not port_raw.isdigit():
        return
    port = int(port_raw)
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("Health server in ascolto su :%d", port)


async def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN mancante. Compila il file .env con il token del bot."
        )
    await _start_health_server()
    bot = WatermelonBot()
    async with bot:
        await bot.start(TOKEN, reconnect=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot fermato manualmente.")
