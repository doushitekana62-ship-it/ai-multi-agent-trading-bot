from fronted.risk_engine import initial_levels, settings_with_defaults
from fronted.risk_templates import TEMPLATES, normalize_template


def tape():
    base = 100.0
    return [{"timestamp": i * 60, "price": base + (i % 3) * 0.2} for i in range(31)]


def test_template_catalog_has_three_distinct_risk_profiles():
    assert set(TEMPLATES) == {"CONSERVATIVE", "BALANCED", "AGGRESSIVE"}
    stops = [TEMPLATES[x]["stop_atr_multiplier"] for x in TEMPLATES]
    rewards = [TEMPLATES[x]["risk_reward_ratio"] for x in TEMPLATES]
    assert len(set(stops)) == 3
    assert len(set(rewards)) == 3


def test_template_is_server_risk_policy_not_only_ui_label():
    conservative = settings_with_defaults({"tp_sl_template": "CONSERVATIVE"})
    aggressive = settings_with_defaults({"tp_sl_template": "AGGRESSIVE"})
    assert conservative["stop_atr_multiplier"] > aggressive["stop_atr_multiplier"]
    assert conservative["risk_reward_ratio"] < aggressive["risk_reward_ratio"]
    assert conservative["max_hold_minutes"] > aggressive["max_hold_minutes"]


def test_initial_levels_change_with_human_template():
    conservative = initial_levels(100.0, tape(), {"tp_sl_template": "CONSERVATIVE"})
    aggressive = initial_levels(100.0, tape(), {"tp_sl_template": "AGGRESSIVE"})
    assert conservative["stop_loss"] < aggressive["stop_loss"]
    assert conservative["take_profit"] < aggressive["take_profit"]


def test_unknown_template_falls_back_to_balanced():
    assert normalize_template("not-a-template") == "BALANCED"
