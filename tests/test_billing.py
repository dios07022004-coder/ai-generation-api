"""Тесты партнёрского биллинга: резерв/возврат/пополнение, изоляция, идемпотентность."""
import pytest
from sqlalchemy import func, select


def _make_key_with_balance(balance: int, overrides: dict | None = None) -> tuple[str, str]:
    """Создать партнёрский ключ с балансом. Возвращает (raw_key, api_key_id)."""
    from app.core.security import generate_api_key
    from app.db.session import SessionLocal
    from app.models import ApiKey
    raw, key_hash = generate_api_key()
    with SessionLocal() as s:
        k = ApiKey(
            name="partner", key_hash=key_hash, status="active",
            balance_credits=balance, price_overrides=overrides or {},
        )
        s.add(k)
        s.commit()
        s.refresh(k)
        kid = k.id
    return raw, kid


def _ledger_count(task_id: str, entry_type: str) -> int:
    from app.db.session import SessionLocal
    from app.models import BillingLedger
    with SessionLocal() as s:
        return s.execute(
            select(func.count()).select_from(BillingLedger).where(
                BillingLedger.task_id == task_id, BillingLedger.entry_type == entry_type
            )
        ).scalar()


@pytest.fixture
def billing(client, monkeypatch):
    """Включает биллинг и фиксирует цены (видео 40, фото 10). Возвращает TestClient.

    Зависит от client → запускается ПОСЛЕ lifespan (который читает pricing.yaml),
    поэтому наши цены перекрывают файл.
    """
    from app.core.config import settings
    from app.services.pricing import pricing
    monkeypatch.setattr(settings, "BILLING_ENABLED", True)
    pricing._defaults = {"video": 40, "photo": 10}
    pricing._modes = {}
    pricing._api_keys = {}
    return client


VIDEO = {"task_type": "video", "mode": "VIDEO_VARIATION_1"}


def test_billing_disabled_no_charge(client):
    # По умолчанию биллинг выключен → ничего не списывается, price_credits=None, нет ledger.
    r = client.post("/generate", json=VIDEO)
    assert r.status_code == 202
    tid = r.json()["task_id"]
    st = client.get(f"/tasks/{tid}").json()
    assert st["status"] == "completed"
    assert st["price_credits"] is None
    from app.db.session import SessionLocal
    from app.models import BillingLedger
    with SessionLocal() as s:
        assert s.execute(select(func.count()).select_from(BillingLedger)).scalar() == 0


def test_insufficient_balance_402(billing):
    raw, _ = _make_key_with_balance(0)
    r = billing.post("/generate", json=VIDEO, headers={"X-API-Key": raw})
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "insufficient_balance"
    bal = billing.get("/billing/balance", headers={"X-API-Key": raw}).json()
    assert bal["balance_credits"] == 0


def test_success_debits_once(billing):
    raw, _ = _make_key_with_balance(100)
    h = {"X-API-Key": raw}
    r = billing.post("/generate", json=VIDEO, headers=h)
    assert r.status_code == 202
    tid = r.json()["task_id"]
    st = billing.get(f"/tasks/{tid}", headers=h).json()
    assert st["status"] == "completed"
    assert st["price_credits"] == 40
    assert billing.get("/billing/balance", headers=h).json()["balance_credits"] == 60
    assert _ledger_count(tid, "hold") == 1
    assert _ledger_count(tid, "adjust") == 1
    assert _ledger_count(tid, "refund") == 0


def test_terminal_failure_refunds_once(billing, monkeypatch):
    from app.core.errors import ValidationAppError

    class BadProvider:
        name = "bad"

        def generate(self, req, progress):
            raise ValidationAppError("boom")  # non-retryable → сразу dead-letter

    monkeypatch.setattr("app.queues.tasks.get_provider", lambda: BadProvider())
    raw, _ = _make_key_with_balance(100)
    h = {"X-API-Key": raw}
    r = billing.post("/generate", json=VIDEO, headers=h)
    assert r.status_code == 202
    tid = r.json()["task_id"]
    assert billing.get(f"/tasks/{tid}", headers=h).json()["status"] == "failed"
    # списали 40 при резерве, вернули 40 при сбое → баланс назад к 100.
    assert billing.get("/billing/balance", headers=h).json()["balance_credits"] == 100
    assert _ledger_count(tid, "hold") == 1
    assert _ledger_count(tid, "refund") == 1


def test_idempotent_replay_no_double_charge(billing):
    raw, _ = _make_key_with_balance(100)
    h = {"X-API-Key": raw}
    body = {**VIDEO, "request_id": "rr1"}
    a = billing.post("/generate", json=body, headers=h).json()["task_id"]
    b = billing.post("/generate", json=body, headers=h).json()["task_id"]
    assert a == b
    assert billing.get("/billing/balance", headers=h).json()["balance_credits"] == 60
    assert _ledger_count(a, "hold") == 1


def test_try_debit_no_overspend(db):
    from app.db.session import SessionLocal
    from app.repositories import billing_repo
    _, kid = _make_key_with_balance(40)
    with SessionLocal() as s:
        assert billing_repo.try_debit(s, kid, 40) is True
        s.commit()
        assert billing_repo.try_debit(s, kid, 40) is False
        assert billing_repo.get_balance(s, kid) == 0


def test_topup_admin_and_auth(client):
    from app.core.security import issue_internal_token
    _, kid = _make_key_with_balance(0)
    tok = issue_internal_token("ops", ttl_seconds=60)
    r = client.post(f"/admin/billing/{kid}/topup", json={"amount_credits": 200, "note": "june"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["balance_credits"] == 200
    # без JWT — 401
    no_auth = client.post(f"/admin/billing/{kid}/topup", json={"amount_credits": 50})
    assert no_auth.status_code == 401


def test_partner_usage_isolation(billing):
    raw_a, _ = _make_key_with_balance(100)
    raw_b, _ = _make_key_with_balance(100)
    billing.post("/generate", json=VIDEO, headers={"X-API-Key": raw_a})
    ua = billing.get("/billing/usage", headers={"X-API-Key": raw_a}).json()
    ub = billing.get("/billing/usage", headers={"X-API-Key": raw_b}).json()
    assert ua["summary"]["generations_charged"] == 1
    assert ub["summary"]["generations_charged"] == 0
    assert ub["entries"] == []


def test_pricing_precedence_and_missing():
    from app.core.errors import ValidationAppError
    from app.services.pricing import pricing
    pricing._defaults = {"video": 40}
    pricing._modes = {"VIDEO_VARIATION_7": 45}
    pricing._api_keys = {}

    class K:
        id = "k1"
        price_overrides: dict = {}

    k = K()
    assert pricing.price_for("video", "VIDEO_VARIATION_1", k) == 40   # defaults
    assert pricing.price_for("video", "VIDEO_VARIATION_7", k) == 45   # modes > defaults
    k.price_overrides = {"VIDEO_VARIATION_7": 50}
    assert pricing.price_for("video", "VIDEO_VARIATION_7", k) == 50   # per-key > modes
    with pytest.raises(ValidationAppError):
        pricing.price_for("photo", "PHOTO_MODE_1", k)                 # нет цены → fail-closed


def test_refund_idempotent(db):
    from app.db.session import SessionLocal
    from app.repositories import billing_repo, task_repo
    from app.services import billing
    _, kid = _make_key_with_balance(100)
    with SessionLocal() as s:
        t = task_repo.create(s, task_type="video", mode="VIDEO_VARIATION_1",
                             api_key_id=kid, status="failed")
        tid = t.id
        billing_repo.try_debit(s, kid, 40)
        s.commit()
        bal = billing_repo.get_balance(s, kid)
        billing_repo.add_ledger(s, kid, "hold", -40, bal, task_id=tid)
        s.commit()
        task_repo.update(s, tid, price_credits=40)
    with SessionLocal() as s:
        billing.refund(s, tid)
    with SessionLocal() as s:
        billing.refund(s, tid)  # повторный возврат — no-op
        assert billing_repo.get_balance(s, kid) == 100  # 60 + 40 (один раз)
    assert _ledger_count(tid, "refund") == 1
