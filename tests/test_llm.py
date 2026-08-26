"""Tests for the L4 LLM layer (offline/fallback and grounding)."""

from gungnir.llm import build_explanation_context, explain
from gungnir.models import GameState, MarketId, ProductId, ProductState
from gungnir.proposal import propose


def _state():
    return GameState(
        period=0,
        cash=2_945_500.0,
        workers=150,
        machines=100,
        raw_material_units=1_236_000.0,
        net_assets=6_395_930.0,
        bond_outstanding=550_000.0,
        products={
            ProductId.A: ProductState(factory_inventory=204, rnd_level=1),
            ProductId.B: ProductState(factory_inventory=188, rnd_level=1),
        },
    )


def test_explain_falls_back_without_api_key(monkeypatch):
    import gungnir.llm as llm

    monkeypatch.setattr(llm.settings, "llm_api_key", "")
    p = propose(_state())
    expl = explain(p)
    assert expl.used_llm is False
    assert expl.text  # non-empty Chinese fallback
    assert "税前利润" in expl.text
    assert "期末现金" in expl.text
    # citations carry the grounded numbers
    assert any("税前利润" in c for c in expl.citations)


def test_context_contains_grounded_numbers():
    p = propose(_state())
    ctx = build_explanation_context(p)
    assert f"{p.result.profit:,.0f}" in ctx
    assert f"{p.result.ending_cash:,.0f}" in ctx
    assert "规则要点" in ctx
    assert "可运出比例" in ctx  # a rule fact, not an invention


def test_live_call_uses_injected_client(monkeypatch):
    import gungnir.llm as llm

    monkeypatch.setattr(llm.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_model", "test-model")

    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "好方案"})()})()]})

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    p = propose(_state())
    expl = explain(p, client=FakeClient())
    assert expl.used_llm is True
    assert expl.text == "好方案"
    assert expl.model == "test-model"
