"""Tests for the M5 web backend: the 录入→提案→调整→导出 loop via TestClient."""

from fastapi.testclient import TestClient

from gungnir.models import MarketId, ProductId, ProductState
from gungnir.web import app

client = TestClient(app)


def _state() -> dict:
    return {
        "period": 0,
        "cash": 2_945_500.0,
        "workers": 150,
        "machines": 100,
        "raw_material_units": 1_236_000.0,
        "net_assets": 6_395_930.0,
        "bond_outstanding": 550_000.0,
        "bond_principal_due": 20_500.0,
        "products": {
            "A": {"factory_inventory": 204, "rnd_level": 1},
            "B": {"factory_inventory": 188, "rnd_level": 1},
        },
    }


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Gungnir" in r.text


def test_propose_loop():
    r = client.post("/api/propose", json={"state": _state()})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["feasible"] is True
    assert p["result"]["ending_cash"] >= 0
    assert "decision" in p and "result" in p


def test_optimize_loop():
    r = client.post("/api/optimize", json={"state": _state()})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["feasible"] is True


def test_adjust_then_revalidate():
    state = _state()
    proposal = client.post("/api/propose", json={"state": state}).json()
    decision = proposal["decision"]

    # A feasible edit: raise the A/M1 price a little.
    decision["prices"]["A"]["M1"] = 3000.0
    r = client.post("/api/evaluate", json={"state": state, "decision": decision})
    assert r.status_code == 200
    assert r.json()["feasibility"]["feasible"] is True

    # An infeasible edit: ship far more than producible.
    decision["shipments"]["A"]["M1"] = 999999
    r2 = client.post("/api/evaluate", json={"state": state, "decision": decision})
    assert r2.status_code == 200
    assert r2.json()["feasibility"]["feasible"] is False
    assert any(v["code"] == "shipment_infeasible" for v in r2.json()["feasibility"]["violations"])


def test_explain_loop():
    state = _state()
    proposal = client.post("/api/propose", json={"state": state}).json()
    r = client.post(
        "/api/explain",
        json={"state": state, "decision": proposal["decision"]},
    )
    assert r.status_code == 200
    assert r.json()["text"]  # non-empty explanation


def test_export_loop():
    state = _state()
    proposal = client.post("/api/propose", json={"state": state}).json()
    r = client.post(
        "/api/export",
        json={"state": state, "decision": proposal["decision"]},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "决策" in r.text
    assert "期末现金" in r.text


def test_episode_loop():
    r = client.post("/api/episode", json={"state": _state(), "periods": 4})
    assert r.status_code == 200, r.text
    ep = r.json()
    assert len(ep["records"]) == 4
    assert len(ep["profit_curve"]) == 4
    assert ep["ending_state"]["period"] == 4


def test_tournament_loop():
    states = [_state(), _state(), _state()]
    r = client.post("/api/tournament", json={"states": states, "periods": 3})
    assert r.status_code == 200, r.text
    t = r.json()
    assert len(t["firms"]) == 3
    assert len(t["score_curves"]["0"]) == 3
