"""Human-controlled TP/SL policy templates for the canonical paper risk engine."""
from __future__ import annotations

TEMPLATES = {
    "CONSERVATIVE": {
        "label": "Conservative",
        "description": "Wider protection, earlier profit activation, and shorter exposure. Favors capital preservation over maximum upside.",
        "stop_loss_mode": "ATR",
        "stop_atr_multiplier": 1.80,
        "take_profit_mode": "RISK_REWARD",
        "risk_reward_ratio": 1.40,
        "profit_activation_pct": 0.60,
        "trailing_enabled": True,
        "trailing_mode": "ATR",
        "trailing_atr_multiplier": 1.50,
        "trailing_pct": 0.70,
        "break_even_enabled": True,
        "break_even_trigger_r": 0.80,
        "break_even_offset_pct": 0.05,
        "hard_take_profit_enabled": True,
        "max_hold_minutes": 12,
    },
    "BALANCED": {
        "label": "Balanced",
        "description": "Middle ground between protection and reward. Intended as the baseline for paper validation.",
        "stop_loss_mode": "ATR",
        "stop_atr_multiplier": 1.50,
        "take_profit_mode": "RISK_REWARD",
        "risk_reward_ratio": 2.00,
        "profit_activation_pct": 1.00,
        "trailing_enabled": True,
        "trailing_mode": "ATR",
        "trailing_atr_multiplier": 1.25,
        "trailing_pct": 0.60,
        "break_even_enabled": True,
        "break_even_trigger_r": 1.00,
        "break_even_offset_pct": 0.05,
        "hard_take_profit_enabled": False,
        "max_hold_minutes": 15,
    },
    "AGGRESSIVE": {
        "label": "Aggressive",
        "description": "Tighter initial stop and larger reward target. Higher variance and lower tolerance for market noise.",
        "stop_loss_mode": "ATR",
        "stop_atr_multiplier": 1.10,
        "take_profit_mode": "RISK_REWARD",
        "risk_reward_ratio": 2.20,
        "profit_activation_pct": 0.50,
        "trailing_enabled": True,
        "trailing_mode": "ATR",
        "trailing_atr_multiplier": 1.00,
        "trailing_pct": 0.50,
        "break_even_enabled": True,
        "break_even_trigger_r": 1.00,
        "break_even_offset_pct": 0.05,
        "hard_take_profit_enabled": False,
        "max_hold_minutes": 10,
    },
}


def normalize_template(value: str | None) -> str:
    name = str(value or "BALANCED").strip().upper().replace("-", "_").replace(" ", "_")
    return name if name in TEMPLATES else "BALANCED"


def template_settings(value: str | None) -> dict:
    name = normalize_template(value)
    return {k: v for k, v in TEMPLATES[name].items() if k not in {"label", "description"}}


def template_catalog() -> list[dict]:
    return [
        {"name": name, "label": data["label"], "description": data["description"], "settings": template_settings(name)}
        for name, data in TEMPLATES.items()
    ]
