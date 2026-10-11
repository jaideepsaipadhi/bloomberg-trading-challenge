import pytest

from trading_bot.config import WhatsAppConfig
from trading_bot import whatsapp as wa


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_console_notifier_delivers(capsys):
    res = wa.ConsoleNotifier().send("hello")
    assert res["provider"] == "console" and res["delivered"] is True
    assert "hello" in capsys.readouterr().out


def test_build_notifier_defaults_to_console():
    cfg = WhatsAppConfig(provider="console")
    assert isinstance(wa.build_notifier(cfg), wa.ConsoleNotifier)


def test_twilio_requires_full_config():
    with pytest.raises(ValueError):
        wa.TwilioNotifier(account_sid="", auth_token="", from_="", recipients=[])


def test_twilio_broadcasts_to_each_recipient(monkeypatch):
    calls = []

    def fake_post(url, data=None, auth=None, timeout=None):
        calls.append({"url": url, "data": data, "auth": auth})
        return _Resp(201, {"sid": "SM123"})

    monkeypatch.setattr(wa.requests, "post", fake_post)
    n = wa.TwilioNotifier("AC1", "tok", "whatsapp:+14155238886",
                          ["whatsapp:+15551111111", "whatsapp:+15552222222"])
    res = n.send("book update")
    assert res["delivered"] is True and res["sent"] == 2 and res["failed"] == 0
    assert len(calls) == 2
    # correct From/Body and auth wired through
    assert calls[0]["data"]["From"] == "whatsapp:+14155238886"
    assert calls[0]["data"]["Body"] == "book update"
    assert calls[0]["auth"] == ("AC1", "tok")
    assert calls[0]["data"]["To"] == "whatsapp:+15551111111"


def test_twilio_surfaces_errors(monkeypatch):
    def fake_post(url, data=None, auth=None, timeout=None):
        return _Resp(400, {"code": 63015, "message": "Channel not found"})

    monkeypatch.setattr(wa.requests, "post", fake_post)
    n = wa.TwilioNotifier("AC1", "tok", "whatsapp:+1", ["whatsapp:+15551111111"])
    res = n.send("x")
    assert res["delivered"] is False and res["failed"] == 1
    assert res["results"][0]["error"] == "Channel not found"
    assert res["results"][0]["code"] == 63015


def test_recipients_parsing():
    cfg = WhatsAppConfig(recipients_raw="whatsapp:+1555 , whatsapp:+1444 ,")
    assert cfg.recipients == ["whatsapp:+1555", "whatsapp:+1444"]


# ---- Telegram ----

def test_telegram_requires_token_and_chats():
    with pytest.raises(ValueError):
        wa.TelegramNotifier(token="", chat_ids=[])


def test_build_notifier_selects_telegram():
    cfg = WhatsAppConfig(provider="telegram")
    cfg.telegram_token = "123:abc"
    cfg.telegram_chat_ids_raw = "-100123"
    assert isinstance(wa.build_notifier(cfg), wa.TelegramNotifier)


def test_telegram_posts_to_each_chat(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None):
        calls.append({"url": url, "data": data})
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(wa.requests, "post", fake_post)
    n = wa.TelegramNotifier("123:abc", ["-1001", "222"])
    res = n.send("*book* update")
    assert res["delivered"] is True and res["sent"] == 2
    assert calls[0]["data"]["chat_id"] == "-1001"
    assert calls[0]["data"]["text"] == "*book* update"
    assert "sendMessage" in calls[0]["url"]


def test_telegram_retries_plain_on_parse_error(monkeypatch):
    attempts = []

    def fake_post(url, data=None, timeout=None):
        attempts.append(data.get("parse_mode"))
        if data.get("parse_mode") == "Markdown":
            return _Resp(400, {"description": "Bad Request: can't parse entities"})
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(wa.requests, "post", fake_post)
    n = wa.TelegramNotifier("123:abc", ["-1001"])
    res = n.send("weird _ * markup")
    assert res["delivered"] is True
    assert attempts == ["Markdown", None]   # retried without parse_mode


def test_telegram_chat_ids_parsing():
    cfg = WhatsAppConfig(telegram_chat_ids_raw="-1001234567890, 987654321 ,")
    assert cfg.telegram_chat_ids == ["-1001234567890", "987654321"]
