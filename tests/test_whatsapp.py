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
