import os
import sys

# Ensure project root is on path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agentic_tools import marketing_tools as mt

class DummyChannel(mt.NotificationChannel):
    def send(self, recipient_segment: str, message: str, **kwargs):
        return {"status": "success", "channel": "dummy", "recipient": recipient_segment, "message": message}


def test_activate_channel_invalid():
    res = mt.activate_channel("no-such-channel", "seg_a", "hello")
    assert res["status"] == "error"
    assert "available" in res


def test_register_and_execute_dummy_channel():
    # Register dummy channel and execute
    mt.ActivationManager.register_channel("dummy", DummyChannel)
    res = mt.activate_channel("dummy", "seg_b", "hi")
    assert res["status"] == "success"
    assert res["channel"] == "dummy"
    assert res["recipient"] == "seg_b"


def test_activate_channel_validation():
    # Missing message
    res = mt.activate_channel("email", "seg_c", "")
    assert res["status"] == "error"


def test_zalo_oa_send_success(monkeypatch):
    class FakeResp:
        def __init__(self):
            self.status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"ok": True}

    calls = {"n": 0}

    def fake_post(url, json, headers, timeout):
        calls["n"] += 1
        assert "recipient" in json
        return FakeResp()

    monkeypatch.setenv("ZALO_OA_TOKEN", "fake-token")
    monkeypatch.setattr("requests.post", fake_post)

    res = mt.activate_channel("zalo", "seg_z", "promo message")
    assert res["status"] == "success"
    assert res["channel"] == "zalo_oa"
    assert "response" in res
    assert calls["n"] == 1


def test_zalo_oa_retries(monkeypatch):
    # Simulate first attempt failing and second succeeding
    class FailOnceResp:
        def __init__(self, fail):
            self.status_code = 200
            self._fail = fail
        def raise_for_status(self):
            if self._fail:
                raise requests.exceptions.RequestException("temporary")
            return None
        def json(self):
            return {"ok": True}

    state = {"calls": 0}

    def fake_post(url, json, headers, timeout):
        state["calls"] += 1
        if state["calls"] == 1:
            return FailOnceResp(True)
        return FailOnceResp(False)

    monkeypatch.setenv("ZALO_OA_TOKEN", "fake-token")
    monkeypatch.setattr("requests.post", fake_post)

    res = mt.activate_channel("zalo", "seg_z", "promo 2", timeout=1, retries=1)
    assert res["status"] == "success"
    assert state["calls"] == 2


def test_facebook_push_alias(monkeypatch):
    # facebook_push should be recognized and map to facebook_page channel
    res = mt.activate_channel("facebook_push", "Summer Sale Target", "Hello, this is our products")
    assert res["status"] == "success"
    assert res["channel"] == "facebook_page"


def test_zalo_oa_variants(monkeypatch):
    # Ensure spaced/hyphenated/compact variants are accepted
    monkeypatch.setenv("ZALO_OA_TOKEN", "fake-token")

    class FakeResp:
        def __init__(self):
            self.status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"ok": True}

    def fake_post(url, json, headers, timeout):
        return FakeResp()

    monkeypatch.setattr("requests.post", fake_post)

    for variant in ("Zalo OA", "zalo-oa", "ZaloOA", "zalooa", "zalo oa"):
        res = mt.activate_channel(variant, "Summer Sale Target", "Hello, this is our products")
        assert res["status"] == "success"
        assert res["channel"] == "zalo_oa"


def test_email_sendgrid_requires_api_key(monkeypatch):
    # configure for sendgrid but without API key
    monkeypatch.setattr(mt.MarketingConfigs, "EMAIL_PROVIDER", "sendgrid", raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SENDGRID_API_KEY", None, raising=False)
    ch = mt.EmailChannel()
    res = ch.send("alice@example.com", "hello", provider="sendgrid", subject="Hi")
    assert res["status"] == "error"
    assert "SENDGRID_API_KEY not set" in res["message"]


def test_email_sendgrid_success(monkeypatch):
    # setup sendgrid config
    monkeypatch.setattr(mt.MarketingConfigs, "SENDGRID_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SENDGRID_FROM", "from@ex.com", raising=False)

    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status=202):
            self.status_code = status

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        assert url == "https://api.sendgrid.com/v3/mail/send"
        assert headers and headers.get("Authorization") == "Bearer fake-key"
        # Validate payload structure
        assert "personalizations" in json
        p = json["personalizations"][0]
        assert p["subject"] == "Greetings"
        assert p["to"] == [{"email": "alice@example.com"}]
        assert json["content"][0]["value"] == "Hello sendgrid"
        # mimic successful creation
        return FakeResp(202)

    monkeypatch.setattr(mt.requests, "post", fake_post)

    ch = mt.EmailChannel()
    res = ch.send("alice@example.com", "Hello sendgrid", provider="sendgrid", subject="Greetings", timeout=2)
    assert res["status"] == "success"
    assert res["provider"] == "sendgrid"
    assert res["response_status"] == 202
    assert calls["n"] == 1


def test_email_smtp_requires_credentials(monkeypatch):
    # clear SMTP credentials
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_USERNAME", None, raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_PASSWORD", None, raising=False)
    ch = mt.EmailChannel()
    res = ch.send("bob@example.com", "hello smtp", provider="smtp")
    assert res["status"] == "error"
    assert "SMTP credentials not set" in res["message"]


def test_email_smtp_success_and_subject_title(monkeypatch):
    # configure SMTP credentials
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_USERNAME", "me@example.com", raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_HOST", "smtp.fake", raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(mt.MarketingConfigs, "SMTP_USE_TLS", True, raising=False)

    sent = {"called": False, "msg": None, "starttls": False, "logged_in": False, "login_creds": ()}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout
            self._starttls = False
            self._logged = False
            self._login_creds = None

        def starttls(self, context=None):
            self._starttls = True
            sent["starttls"] = True

        def login(self, username, password):
            self._logged = True
            self._login_creds = (username, password)
            sent["logged_in"] = True
            sent["login_creds"] = self._login_creds

        def send_message(self, msg):
            sent["called"] = True
            sent["msg"] = msg

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    # patch the SMTP class used inside module
    monkeypatch.setattr(mt.smtplib, "SMTP", FakeSMTP)

    ch = mt.EmailChannel()
    # multiple recipients, explicit subject
    res = ch.send("a@x.com, b@y.com", "SMTP body", provider="smtp", subject="Subj")
    assert res["status"] == "success"
    assert res["provider"] == "smtp"
    assert res["sent_to"] == ["a@x.com", "b@y.com"]
    assert sent["called"] is True
    assert sent["starttls"] is True
    assert sent["logged_in"] is True
    assert sent["login_creds"] == ("me@example.com", "secret")
    # verify message headers
    msg = sent["msg"]
    assert msg["Subject"] == "Subj"
    # To header is comma-joined
    assert msg["To"] == "a@x.com, b@y.com"

    # Now test subject fallback to title when no subject given
    sent["called"] = False
    sent["msg"] = None
    res2 = ch.send(["z@z.com"], "Body two", provider="smtp", title="MyTitle")
    assert res2["status"] == "success"
    assert sent["called"] is True
    assert sent["msg"]["Subject"] == "MyTitle"
    assert sent["msg"]["To"] == "z@z.com"


