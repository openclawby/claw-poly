import asyncio
import inspect
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import btc, config, db, engine, executor, main, redeem


def test_paper_only_constant_and_mode_are_not_configurable():
    assert config.PAPER_ONLY is True
    assert executor.mode() == "paper"
    assert executor.mode({"live_enabled": True}) == "paper"


@pytest.mark.parametrize("name", ["PM_PRIVATE_KEY", "PM_FUNDER", "PM_SIGNATURE_TYPE"])
def test_trading_credential_environment_rejects_startup(monkeypatch, name):
    monkeypatch.setenv(name, "present-but-not-a-real-credential")
    with pytest.raises(RuntimeError, match="Paper-only research build detected"):
        config.enforce_paper_only_environment()


def test_clawby_key_is_allowed(monkeypatch):
    for name in config.LIVE_TRADING_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAWBY_API_KEY", "read-only-test-placeholder")
    config.enforce_paper_only_environment()


def test_no_clawby_key_is_allowed(monkeypatch):
    monkeypatch.delenv("CLAWBY_API_KEY", raising=False)
    for name in config.LIVE_TRADING_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    config.enforce_paper_only_environment()


def test_lifespan_checks_credentials_before_starting(monkeypatch):
    monkeypatch.setenv("PM_PRIVATE_KEY", "present-but-not-a-real-credential")

    async def run():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="Paper-only research build detected"):
        asyncio.run(run())


def test_lifespan_allows_clawby_only_without_network(monkeypatch):
    for name in config.LIVE_TRADING_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAWBY_API_KEY", "read-only-test-placeholder")
    monkeypatch.setattr(db, "init", lambda: None)

    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(btc, "ws_loop", idle)
    monkeypatch.setattr(engine, "loop", idle)

    async def run():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(run())


def test_get_client_fails_closed():
    with pytest.raises(RuntimeError, match="Live trading is disabled"):
        asyncio.run(executor._get_client())


def test_place_limit_and_tp_are_always_paper(monkeypatch):
    rows = []
    monkeypatch.setattr(db, "log_order", lambda *a, **kw: rows.append((a, kw)))
    round_row = {
        "slug": "btc-updown-5m-test", "token_up": "up", "token_down": "down",
        "tick": 0.01, "side": "up", "entry_price": 0.5, "shares": 2,
    }
    settings = {"take_profit_pct": 20, "live_enabled": True}
    oid, price, shares = asyncio.run(
        executor.place_limit(round_row, "up", 5, 0.51, settings, "pre_trend"))
    tp_oid, tp_price = asyncio.run(
        executor.place_tp(round_row, settings, "pre_trend"))
    assert oid.startswith("paper:") and tp_oid.startswith("paper-tp:")
    assert price == 0.51 and shares > 0 and tp_price == 0.6
    assert all((args[6] if len(args) > 6 else kwargs.get("mode")) == "paper"
               for args, kwargs in rows)


def test_cancel_all_has_no_client_path():
    assert asyncio.run(executor.cancel_all()) == 0


@pytest.mark.parametrize("order_id", ["paper:slug:up:1", "paper-tp:slug:s:1"])
def test_cancel_order_accepts_only_simulated_prefixes(monkeypatch, order_id):
    rows = []
    monkeypatch.setattr(db, "log_order", lambda *a, **kw: rows.append((a, kw)))
    assert asyncio.run(executor.cancel_order(order_id)) is True
    assert rows and rows[0][1]["mode"] == "paper"


def test_cancel_order_rejects_nonpaper_without_logging_identifier(monkeypatch, caplog):
    monkeypatch.setattr(db, "log_order", lambda *a, **kw: pytest.fail("must not log order"))
    marker = "sensitive-looking-order-identifier"
    assert asyncio.run(executor.cancel_order(marker)) is False
    assert marker not in caplog.text


def test_redeem_always_fails_closed():
    with pytest.raises(RuntimeError, match="On-chain redemption is disabled"):
        asyncio.run(redeem.run_once())


def test_sensitive_routes_do_not_exist():
    client = TestClient(main.app, headers={"Host": "127.0.0.1"})
    for method, path in (
        ("get", "/api/private-key"),
        ("post", "/api/private-key"),
        ("post", "/api/private-key/context"),
        ("post", "/api/funder"),
        ("post", "/api/signature-type"),
        ("post", "/api/live"),
        ("post", "/api/auto-redeem"),
    ):
        response = (client.post(path, json={}) if method == "post" else client.get(path))
        assert response.status_code == 404, (method, path, response.text)


@pytest.mark.parametrize("field", [
    "live_enabled", "private_key", "PM_PRIVATE_KEY", "funder", "signature_type",
    "auto_redeem", "clob_creds", "api_secret", "api_passphrase", "unknown_secret",
])
def test_settings_reject_sensitive_and_unknown_fields(field):
    client = TestClient(main.app, headers={"Host": "127.0.0.1"})
    response = client.post("/api/settings", json={field: "test-placeholder"})
    assert response.status_code == 400


def test_settings_validate_ranges_and_allow_research_fields(monkeypatch):
    saved = []
    monkeypatch.setattr(db, "save_settings", lambda updates: saved.append(updates))
    client = TestClient(main.app, headers={"Host": "127.0.0.1"})
    assert client.post("/api/settings", json={"overpay_cap": 2}).status_code == 400
    assert client.post("/api/settings", json={"horizon": 2.5}).status_code == 400
    response = client.post("/api/settings", json={
        "horizon": 6, "take_profit_pct": 20,
        "params": {"edge_min": 0.06, "signal": "revert", "cover": 1},
    })
    assert response.status_code == 200
    assert saved


def test_local_origin_and_host_guards():
    client = TestClient(main.app, headers={"Host": "127.0.0.1"})
    bad_origin = client.post(
        "/api/settings", json={"horizon": 6}, headers={"Origin": "https://example.invalid"})
    assert bad_origin.status_code == 403
    bad_host = client.get("/health", headers={"Host": "example.invalid"})
    assert bad_host.status_code == 400


def test_legacy_database_live_values_and_clob_creds_are_removed(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES ('live_enabled', '1');
        INSERT INTO settings VALUES ('auto_redeem', '1');
        INSERT INTO meta VALUES ('clob_creds', 'sensitive-placeholder');
    """)
    conn.commit()
    conn.close()

    old_path, old_conn = config.DB_PATH, db._conn
    monkeypatch.setattr(config, "DB_PATH", str(path))
    try:
        db.init()
        assert executor.mode(db.get_settings()) == "paper"
        assert "live_enabled" not in db.get_settings()["_raw"]
        assert "auto_redeem" not in db.get_settings()["_raw"]
        assert db.get_meta("clob_creds", "missing") == "missing"
        check = sqlite3.connect(path)
        assert check.execute("SELECT 1 FROM meta WHERE key='clob_creds'").fetchone() is None
        check.close()
    finally:
        if db._conn is not None:
            db._conn.close()
        db._conn = old_conn
        config.DB_PATH = old_path


def test_source_contains_no_exchange_execution_calls():
    source = inspect.getsource(executor)
    forbidden = ("create_or_derive_api_creds", ".create_order(", ".post_order(",
                 ".get_order(", ".cancel_all(", ".cancel(")
    assert not any(term in source for term in forbidden)


def test_frontend_has_no_sensitive_controls_or_copy():
    root = Path(__file__).resolve().parents[1]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "frontend" / "src").rglob("*") if path.is_file()
    ).lower()
    forbidden = ("/api/private-key", "pm_private_key", "funder", "signature_type",
                 "live_enabled", "auto_redeem", "live switch", "实盘开关", "私钥输入")
    assert not any(term in source for term in forbidden)
    assert "paper only" in source
