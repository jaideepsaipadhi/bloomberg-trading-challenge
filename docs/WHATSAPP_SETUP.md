# Going live: WhatsApp delivery

This wires the bot to post the daily **trend setups** (`signals`) and/or the
weekly **momentum book** (`momentum`) to your team over WhatsApp.

## ⚠️ Read this first: no group messaging

The **official** WhatsApp Business API (Twilio / Meta) **cannot post into a
WhatsApp group.** It only does 1:1 conversations with people who opted in. So
the bot **broadcasts** each message individually to every teammate on the
recipient list — everyone gets it in their own chat with the bot. That's the
compliant, reliable path and what this setup uses.

(Posting inside one real group thread would need an *unofficial* WhatsApp-Web
library that risks your number being banned. Not supported here.)

## Option A — Twilio WhatsApp Sandbox (fastest, free, for the competition)

Good enough for a student team: no business verification, works in minutes.

1. **Create a Twilio account** → https://www.twilio.com/try-twilio
2. In the console: **Messaging → Try it out → Send a WhatsApp message.** You'll
   see a **sandbox number** (e.g. `+1 415 523 8886`) and a **join code**
   (e.g. `join olive-tiger`).
3. **Each teammate** sends that join code as a WhatsApp message to the sandbox
   number. (They must re-join every 72h of inactivity — a sandbox limitation.)
4. Grab your **Account SID** and **Auth Token** from the console dashboard.
5. Fill `.env` (copy from `.env.example`):

   ```ini
   WHATSAPP_PROVIDER=twilio
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   WHATSAPP_RECIPIENTS=whatsapp:+15551111111,whatsapp:+15552222222
   ```
   `WHATSAPP_RECIPIENTS` is a comma-separated list of each opted-in teammate's
   number, each prefixed with `whatsapp:` and in E.164 form (`+<country><number>`).

6. **Test it** (dry-run first, then live):

   ```bash
   trading-bot momentum --dry-run     # prints, sends nothing
   trading-bot momentum               # sends to everyone on the list
   ```

   The command prints a delivery summary (`sent` / `failed`, with Twilio's
   reason on any failure).

## Option B — Twilio production sender

For a permanent number and no 72h re-join, register a WhatsApp sender
(Messaging → Senders → WhatsApp senders); needs a Meta Business profile and
template approval for *unsolicited* messages. The `.env` is identical, just with
your approved `TWILIO_WHATSAPP_FROM`. Overkill for a 6–8 week competition.

## Scheduling (post automatically)

The momentum book rebalances ~monthly, so posting it **weekly** (Monday
pre-open) is plenty; trend setups suit a **daily** pre-open post.

**On your own machine (cron):**

```cron
# Monday 08:00 ET momentum book (13:00 UTC)
0 13 * * 1  cd /path/to/repo && /usr/bin/env trading-bot momentum >> bot.log 2>&1
# Weekday 09:00 ET trend setups (14:00 UTC)
0 14 * * 1-5  cd /path/to/repo && /usr/bin/env trading-bot signals >> bot.log 2>&1
```

**Serverless (GitHub Actions):** see `.github/workflows/daily-momentum.yml`. Add
your Twilio values as repository **Secrets** (Settings → Secrets and variables →
Actions): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
`WHATSAPP_RECIPIENTS`. Without the secrets the workflow runs in console mode and
sends nothing, so it's safe to merge before you're ready.

## Safety

- Keep `.env` out of git (it already is, via `.gitignore`).
- Start with `--dry-run` until a real test message arrives as expected.
- The bot only *posts signals*. Humans place the trades in the terminal.
