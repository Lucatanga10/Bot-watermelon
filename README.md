# Watermelon Bot

Bot Discord per il server **Watermelon** con:
- **Ticket panel** (`/panel …`) per vendere ruoli come Staffer, Helper, ecc.
- **Annunci** (`/annuncio`) con embed colorati che taggano `@everyone` / `@here`.

## File .env locale

Copia `.env.example` in `.env` e riempi:

```
DISCORD_TOKEN=il_tuo_token
GUILD_ID=id_del_server
```

## Avvio locale

```bash
pip install -r requirements.txt
python bot.py
```

## Deploy su Render (Web Service free)

1. Vai su https://render.com e crea un account.
2. **New +** → **Web Service** → collega il repo GitHub `Bot-watermelon`.
3. Render legge automaticamente `render.yaml`. Compila:
   - **Name:** `watermelon-bot`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** Free
4. Sezione **Environment** → aggiungi le variabili:
   - `DISCORD_TOKEN` → il token del bot
   - `GUILD_ID` → l'ID del server Watermelon
5. **Create Web Service** → attende il build. In log dovrebbe apparire:
   ```
   Health server in ascolto su :10000
   Sincronizzati N comandi sulla guild ...
   Connesso come WaterMelon BOT#... 
   ```
6. **Tenere sveglio il free tier:** Render Web Service free si addormenta dopo 15 min senza HTTP.
   Registrati su https://uptimerobot.com (gratis) e imposta un monitor HTTP che pinga:
   `https://watermelon-bot.onrender.com/health` ogni 5 minuti. Il bot resta sveglio 24/7.

## Persistenza dati

I file `data/panels.json` e `data/tickets.json` sono salvati sul disco del container.
Su **Render free** il disco è **effimero**: quando il servizio si riavvia (deploy o crash) i dati vengono persi.
Per persistenza vera:
- Attivare un disco Render a pagamento (~$1/mese)
- Oppure migrare a PostgreSQL (Render offre un DB Postgres free)

Se il bot si riavvia, il pannello resta visibile in Discord ma le opzioni potrebbero non
essere più configurate — dovrai rifare `/panel create` e `/panel option add`.

## Comandi

### Ticket
- `/panel create category titolo descrizione [messaggio] [colore] [image]` — crea pannello
- `/panel option add panel_id label role [price] [emoji] [description]` — aggiungi ruolo acquistabile
- `/panel option remove panel_id index` — rimuovi voce
- `/panel option list panel_id` — elenca voci
- `/panel staff panel_id role action:add|remove` — chi vede/gestisce i ticket
- `/panel list` — elenca i pannelli
- `/panel delete panel_id` — elimina un pannello
- `/panel send panel_id channel` — posta il pannello in un canale
- `/close` — chiude il ticket corrente

### Annunci
- `/annuncio tipo mention titolo testo [channel] [messaggio] [footer] [colore] [image]`
