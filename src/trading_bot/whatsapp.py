"""WhatsApp delivery adapters.

IMPORTANT — the group limitation:
    The official WhatsApp Business API (Twilio and Meta Cloud API) does NOT
    support sending messages into a WhatsApp *group*. It only supports 1:1
    conversations with individuals who have opted in / messaged you first
    (or via approved templates). So the ``twilio`` adapter BROADCASTS the
    signal to each number in your recipients list individually.

    If you truly need it posted inside one group thread, that requires an
    UNOFFICIAL WhatsApp-Web automation library (e.g. whatsapp-web.js or
    Baileys), which risks the sending number being banned by WhatsApp. That
    path is intentionally not implemented here; see the README.

The ``console`` adapter (default) just prints — perfect for development and
for running the scan without any credentials.
"""
from __future__ import annotations

from typing import Protocol

import requests


class Notifier(Protocol):
    def send(self, message: str) -> dict: ...


class ConsoleNotifier:
    """Prints the message. Zero setup; the safe default."""

    def send(self, message: str) -> dict:
        print("\n===== Message (console / dry-run) =====")
        print(message)
        print("========================================\n")
        return {"provider": "console", "delivered": True}


class TwilioNotifier:
    """Broadcasts a message 1:1 to each recipient via Twilio's WhatsApp API."""

    def __init__(self, account_sid: str, auth_token: str, from_: str, recipients: list[str]):
        if not (account_sid and auth_token and from_ and recipients):
            raise ValueError(
                "Twilio notifier needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_WHATSAPP_FROM and a non-empty WHATSAPP_RECIPIENTS list."
            )
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_ = from_
        self.recipients = recipients
        self.url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    def send(self, message: str) -> dict:
        results = []
        for to in self.recipients:
            try:
                resp = requests.post(
                    self.url,
                    data={"From": self.from_, "To": to, "Body": message},
                    auth=(self.account_sid, self.auth_token),
                    timeout=30,
                )
                row = {"to": to, "status": resp.status_code, "ok": resp.ok}
                if not resp.ok:
                    # Twilio returns a JSON body with a human-readable reason.
                    try:
                        err = resp.json()
                        row["error"] = err.get("message") or str(err)
                        row["code"] = err.get("code")
                    except Exception:
                        row["error"] = (resp.text or "")[:300]
                results.append(row)
            except Exception as exc:  # pragma: no cover - network path
                results.append({"to": to, "status": None, "ok": False, "error": str(exc)})
        sent = sum(1 for r in results if r.get("ok"))
        return {"provider": "twilio", "results": results,
                "sent": sent, "failed": len(results) - sent,
                "delivered": sent == len(results) and len(results) > 0}


class TelegramNotifier:
    """Posts a message to one or more Telegram chats — including GROUPS.

    Add the bot to your group and use the group's chat id (a negative number).
    Free, no templates, no approval. The recommended delivery path.
    """

    def __init__(self, token: str, chat_ids: list[str]):
        if not token or not chat_ids:
            raise ValueError(
                "Telegram notifier needs TELEGRAM_BOT_TOKEN and a non-empty "
                "TELEGRAM_CHAT_IDS list."
            )
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_ids = chat_ids

    def send(self, message: str) -> dict:
        results = []
        for cid in self.chat_ids:
            row = {"chat_id": cid, "ok": False, "status": None, "error": None}
            # Try Markdown (for *bold*/_italic_); if Telegram can't parse the
            # entities, retry as plain text so a stray char never blocks a send.
            for parse_mode in ("Markdown", None):
                try:
                    data = {"chat_id": cid, "text": message,
                            "disable_web_page_preview": True}
                    if parse_mode:
                        data["parse_mode"] = parse_mode
                    resp = requests.post(self.base + "/sendMessage", data=data, timeout=30)
                    row["status"] = resp.status_code
                    if resp.ok:
                        row["ok"] = True
                        break
                    err = ""
                    try:
                        err = resp.json().get("description", "")
                    except Exception:
                        err = (resp.text or "")[:200]
                    row["error"] = err
                    if parse_mode and "parse" in err.lower():
                        continue  # retry without Markdown
                    break
                except Exception as exc:  # pragma: no cover - network path
                    row["error"] = str(exc)
                    break
            results.append(row)
        sent = sum(1 for r in results if r["ok"])
        return {"provider": "telegram", "results": results,
                "sent": sent, "failed": len(results) - sent,
                "delivered": sent == len(results) and len(results) > 0}


def build_notifier(cfg) -> Notifier:
    provider = (cfg.provider or "console").lower()
    if provider == "telegram":
        return TelegramNotifier(token=cfg.telegram_token, chat_ids=cfg.telegram_chat_ids)
    if provider == "twilio":
        return TwilioNotifier(
            account_sid=cfg.twilio_account_sid,
            auth_token=cfg.twilio_auth_token,
            from_=cfg.twilio_from,
            recipients=cfg.recipients,
        )
    return ConsoleNotifier()
