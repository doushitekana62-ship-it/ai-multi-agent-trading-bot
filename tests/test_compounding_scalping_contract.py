from datetime import datetime, timezone
from fronted.core.indodax_scalping_strategy import _pulse
from fronted.risk_engine import initial_levels, settings_with_defaults, update_protection

def points(prices):return [{"timestamp":i*60,"price":price} for i,price in enumerate(prices,start=1)]
def position():return {"entry_price":100.0,"created_at":datetime.now(timezone.utc).isoformat()}
def test_profit_activation_is_not_a_hard_profit_ceiling():
    settings=settings_with_defaults({"stop_loss_mode":"FIXED_PERCENT","stop_loss_pct":1.0,"take_profit_mode":"FIXED_PERCENT","take_profit_pct":2.0,"profit_activation_enabled":True,"profit_activation_pct":1.0,"hard_take_profit_enabled":False,"trailing_enabled":True,"trailing_mode":"PERCENT","trailing_pct":0.5,"break_even_enabled":False});levels=initial_levels(100.0,points([100,100.2,100.5]),settings);assert levels["profit_activation_price"]==101.0;p=position();result=update_protection(p,101.0,points([100,100.5,101.0]),settings);assert result["triggered"] is False;assert p["profit_active"] is True;assert p["high_water_mark"]==101.0
def test_profit_activation_allows_momentum_to_run_until_trailing_reversal():
    settings=settings_with_defaults({"stop_loss_mode":"FIXED_PERCENT","stop_loss_pct":1.0,"take_profit_mode":"FIXED_PERCENT","take_profit_pct":2.0,"profit_activation_enabled":True,"profit_activation_pct":1.0,"hard_take_profit_enabled":False,"trailing_enabled":True,"trailing_mode":"PERCENT","trailing_pct":0.5,"break_even_enabled":False});p=position();update_protection(p,103.0,points([100,101,102,103]),settings);assert p["high_water_mark"]==103.0;assert p["stop_loss"]>100.0;result=update_protection(p,102.4,points([100,101,103,102.4]),settings);assert result["triggered"] is True;assert result["reason"]=="TRAILING_STOP"
def test_market_pulse_always_returns_30_one_minute_segments():
    now=30*60;pulse=_pulse(points([100+i*0.1 for i in range(31)]),now);assert len(pulse["segments"])==30;assert all("timestamp" in segment and "status" in segment for segment in pulse["segments"])
def test_market_pulse_marks_intraminute_reversal_as_directional():
    now=10*60+2;rows=[{"timestamp":now-1.5,"price":100.0},{"timestamp":now-1.0,"price":101.0},{"timestamp":now-0.5,"price":100.0}];pulse=_pulse(rows,now);current=pulse["segments"][-1];assert current["observations"]==3;assert current["changed"] is True;assert current["status"] in {"GREEN","RED"};assert current["status"]!="GRAY"
def test_market_pulse_keeps_gray_only_for_flat_or_empty_minutes():
    now=10*60+2;rows=[{"timestamp":now-1.5,"price":100.0},{"timestamp":now-0.5,"price":100.0}];pulse=_pulse(rows,now);assert pulse["segments"][-1]["status"]=="GRAY";assert pulse["segments"][-1]["changed"] is False
