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
        print("\n===== WhatsApp (console / dry-run) =====")
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
                results.append({"to": to, "status": resp.status_code, "ok": resp.ok})
            except Exception as exc:  # pragma: no cover - network path
                results.append({"to": to, "status": None, "ok": False, "error": str(exc)})
        return {"provider": "twilio", "results": results,
                "delivered": all(r.get("ok") for r in results)}


def build_notifier(wa_cfg) -> Notifier:
    provider = (wa_cfg.provider or "console").lower()
    if provider == "twilio":
        return TwilioNotifier(
            account_sid=wa_cfg.twilio_account_sid,
            auth_token=wa_cfg.twilio_auth_token,
            from_=wa_cfg.twilio_from,
            recipients=wa_cfg.recipients,
        )
    return ConsoleNotifier()
