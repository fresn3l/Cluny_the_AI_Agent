# Telegram capture

Text notes from your phone into Cluny’s searchable library via a Telegram bot.

## Prerequisites

- [Ollama](https://ollama.com/) running locally (embeddings required for capture)
- A Telegram account
- Mac (or machine running Cluny) online when you capture

## 1. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow prompts, copy the **bot token**
3. Message [@userinfobot](https://t.me/userinfobot) to get your **numeric user id**

## 2. Configure Cluny

Add to `.env`:

```bash
CLUNY_TELEGRAM_BOT_TOKEN=123456:ABC-your-token
CLUNY_TELEGRAM_ALLOWED_USER_IDS=your_numeric_id

# Optional overrides (defaults shown)
CLUNY_CAPTURE_SOURCE=telegram-capture
CLUNY_CAPTURE_COLLECTION=capture
```

Only user ids in `CLUNY_TELEGRAM_ALLOWED_USER_IDS` can use the bot (comma-separated for multiple people).

## 3. Run the bot

```bash
cluny telegram run
```

Leave this running (or install a LaunchAgent later). Send your bot a plain text message — it replies with chunk count when indexed.

Commands: `/start`, `/help`

## 4. Verify

```bash
cluny library list --source telegram-capture
cluny ask "What did I capture today?"
```

## HTTP alternative

If `cluny serve` is running, any client can POST:

```http
POST /capture
Content-Type: application/json
X-Cluny-Token: …

{ "text": "Note from anywhere" }
```

Same indexing as the Telegram bot.

## Kosistenz (later)

Captures go into Cluny’s `capture` collection only. To append to Kosistenz journal files, wire [Sprint 17 Phase A](SPRINT_17.md) in the Kosistenz app or add a bridge when journal format is confirmed.

## Security

- **Always** set `CLUNY_TELEGRAM_ALLOWED_USER_IDS` — without it the bot refuses to start
- Do not share your bot token; revoke via BotFather if leaked
- The bot talks to Telegram’s API outbound only (long polling); no inbound port required
