"""Deterministic paper-trading risk control plane."""
from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
from risk_templates import normalize_template, template_settings
DEFAULT_RISK_SETTINGS={"enabled":True,"tp_sl_template":"BALANCED","stop_loss_mode":"ATR","take_profit_mode":"RISK_REWARD","stop_loss_pct":.80,"take_profit_pct":1.60,"atr_period":14,"stop_atr_multiplier":1.50,"take_profit_atr_multiplier":2.50,"risk_reward_ratio":2.0,"profit_activation_enabled":True,"profit_activation_pct":1.0,"hard_take_profit_enabled":False,"trailing_enabled":True,"trailing_mode":"ATR","trailing_atr_multiplier":1.25,"trailing_pct":.60,"break_even_enabled":True,"break_even_trigger_r":1.0,"break_even_offset_pct":.05,"fee_rate":.0015,"slippage_bps":5.0,"max_hold_minutes":15,"max_position_size":.10,"max_total_exposure":.30,"max_daily_loss_pct":.03,"minimum_confidence":.55,"minimum_net_edge_pct":.45}
def _num(v,d=0.):
    try:v=float(v);return v if isfinite(v) else d
    except (TypeError,ValueError):return d
def settings_with_defaults(value=None):
    raw=dict(value or {});template=normalize_template(raw.get("tp_sl_template","BALANCED"));out=dict(DEFAULT_RISK_SETTINGS);out.update(template_settings(template));out.update(raw);out["tp_sl_template"]=template;out["stop_loss_mode"]=str(out.get("stop_loss_mode") or "ATR").upper();out["take_profit_mode"]=str(out.get("take_profit_mode") or "RISK_REWARD").upper();out["trailing_mode"]=str(out.get("trailing_mode") or "ATR").upper()
    for k in ("stop_loss_pct","take_profit_pct","stop_atr_multiplier","take_profit_atr_multiplier","risk_reward_ratio","profit_activation_pct","trailing_atr_multiplier","trailing_pct","break_even_trigger_r","break_even_offset_pct","fee_rate","slippage_bps","max_position_size","max_total_exposure","max_daily_loss_pct","minimum_confidence","minimum_net_edge_pct"):out[k]=_num(out.get(k),DEFAULT_RISK_SETTINGS[k])
    try:out["atr_period"]=max(2,min(100,int(out.get("atr_period",14))))
    except (TypeError,ValueError):out["atr_period"]=14
    try:out["max_hold_minutes"]=max(0,int(out.get("max_hold_minutes",15)))
    except (TypeError,ValueError):out["max_hold_minutes"]=15
    return out
def minute_candles(points,lookback_minutes=180):
    valid=[p for p in points if isinstance(p,dict) and _ts(p)>0 and _num(p.get("price"))>0]
    if not valid:return []
    anchor=max(_ts(p) for p in valid);rows={}
    for p in valid:
        ts=_ts(p)
        if ts<anchor-lookback_minutes*60 or ts>anchor:continue
        price=_num(p.get("price"));b=int(ts//60)*60;r=rows.setdefault(b,{"timestamp":b,"open":price,"high":price,"low":price,"close":price});r["high"]=max(r["high"],price);r["low"]=min(r["low"],price);r["close"]=price
    return [rows[k] for k in sorted(rows)]
def _ts(p):
    v=(p.get("timestamp") or p.get("date")) if isinstance(p,dict) else 0
    if isinstance(v,str):
        try:return datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()
        except ValueError:return 0.
    v=_num(v);return v/1000 if v>1_000_000_000_000 else v
def atr(points,period=14):
    cs=minute_candles(points,max(180,period*4))
    if len(cs)<2:return None
    trs=[];prev=None
    for c in cs:
        tr=c["high"]-c["low"] if prev is None else max(c["high"]-c["low"],abs(c["high"]-prev),abs(c["low"]-prev));trs.append(max(0,tr));prev=c["close"]
    w=trs[-max(2,int(period)):];return sum(w)/len(w) if w else None
def initial_levels(entry_price,points,settings=None):
    cfg=settings_with_defaults(settings);entry=_num(entry_price)
    if entry<=0:return {"stop_loss":None,"take_profit":None,"profit_activation_price":None,"atr":None,"risk_distance":None}
    a=atr(points,cfg["atr_period"]);risk=entry*cfg["stop_loss_pct"]/100 if cfg["stop_loss_mode"]=="FIXED_PERCENT" or not a else a*cfg["stop_atr_multiplier"];reward=entry*cfg["take_profit_pct"]/100 if cfg["take_profit_mode"]=="FIXED_PERCENT" else risk*cfg["risk_reward_ratio"] if cfg["take_profit_mode"]=="RISK_REWARD" or not a else a*cfg["take_profit_atr_multiplier"]
    return {"stop_loss":max(0,entry-risk),"take_profit":entry+reward,"profit_activation_price":entry*(1+cfg["profit_activation_pct"]/100) if cfg["profit_activation_enabled"] else None,"atr":a,"risk_distance":risk,"reward_distance":reward,"risk_reward":reward/risk if risk>0 else None,"settings":cfg}
def update_protection(position,current_price,points,settings=None):
    cfg=settings_with_defaults(settings);price=_num(current_price);entry=_num(position.get("entry_price"))
    if entry<=0 or price<=0:return {"triggered":False,"position":position,"reason":None}
    if not position.get("initial_stop_loss"):
        levels=initial_levels(entry,points,cfg);position.update({"initial_stop_loss":levels["stop_loss"],"initial_take_profit":levels["take_profit"],"profit_activation_price":levels.get("profit_activation_price"),"stop_loss":levels["stop_loss"],"take_profit":levels["take_profit"],"atr_at_entry":levels.get("atr"),"risk_distance":levels.get("risk_distance"),"tp_sl_template":cfg["tp_sl_template"]})
    else:levels={"atr":atr(points,cfg["atr_period"]),"risk_distance":_num(position.get("risk_distance"))}
    high=max(_num(position.get("high_water_mark"),entry),price);position["high_water_mark"]=high;activation=_num(position.get("profit_activation_price"));position["profit_active"]=bool(position.get("profit_active")) or (activation>0 and high>=activation);risk_distance=_num(position.get("risk_distance"));stop=_num(position.get("stop_loss"))
    if cfg["break_even_enabled"] and risk_distance>0 and high>=entry+risk_distance*cfg["break_even_trigger_r"]:position["break_even_armed"]=True;stop=max(stop,entry*(1+cfg["break_even_offset_pct"]/100));position["stop_loss"]=stop
    if cfg["trailing_enabled"] and position["profit_active"] and high>entry:
        distance=high*cfg["trailing_pct"]/100 if cfg["trailing_mode"]=="PERCENT" else (levels.get("atr") or _num(position.get("atr_at_entry")))*cfg["trailing_atr_multiplier"] or high*cfg["trailing_pct"]/100
        if distance>0:stop=max(stop,high-distance);position["stop_loss"]=stop
    if price<=_num(position.get("stop_loss")):
        reason="BREAK_EVEN" if position.get("break_even_armed") and price>=entry else "TRAILING_STOP" if high>entry and _num(position.get("stop_loss"))>_num(position.get("initial_stop_loss")) else "STOP_LOSS";return {"triggered":True,"reason":reason,"position":position,"stop_loss":position.get("stop_loss"),"take_profit":position.get("take_profit"),"profit_active":position["profit_active"]}
    if (cfg["hard_take_profit_enabled"] or not cfg["trailing_enabled"]) and price>=_num(position.get("take_profit")):return {"triggered":True,"reason":"TAKE_PROFIT","position":position,"stop_loss":position.get("stop_loss"),"take_profit":position.get("take_profit"),"profit_active":position["profit_active"]}
    if cfg["max_hold_minutes"]>0:
        stamp=position.get("created_at")
        try:
            created=datetime.fromisoformat(str(stamp));created=created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created;age=(datetime.now(timezone.utc)-created).total_seconds()/60
            if age>=cfg["max_hold_minutes"]:return {"triggered":True,"reason":"TIME_EXIT","position":position,"stop_loss":position.get("stop_loss"),"take_profit":position.get("take_profit"),"profit_active":position["profit_active"]}
        except (TypeError,ValueError,OverflowError):pass
    return {"triggered":False,"reason":None,"position":position,"stop_loss":position.get("stop_loss"),"take_profit":position.get("take_profit"),"profit_active":position["profit_active"]}
def apply_slippage(price,side,slippage_bps):
    p=_num(price);x=max(0,_num(slippage_bps))/10000;return p*(1+x) if str(side).upper()=="BUY" else p*(1-x)
def evaluate_entry(*,action,confidence,requested_position_size,net_edge_pct,balance,portfolio_value,open_positions,current_exposure,settings=None):
    cfg=settings_with_defaults(settings);action=str(action or "HOLD").upper();confidence=_num(confidence);requested=_num(requested_position_size);edge=_num(net_edge_pct);balance=_num(balance);portfolio=_num(portfolio_value);positions=int(_num(open_positions));exposure=max(0,_num(current_exposure));checks={"risk_enabled":bool(cfg["enabled"]),"action_is_entry":action in {"BUY","STRONG_BUY"},"confidence":confidence>=cfg["minimum_confidence"],"net_edge":edge>=cfg["minimum_net_edge_pct"],"position_limit":0<requested<=cfg["max_position_size"],"open_position_limit":positions<3,"exposure_limit":exposure+requested<=cfg["max_total_exposure"],"balance_available":balance>0 and portfolio>0};approved=all(checks.values());reason="RISK_CHECKS_PASSED" if approved else next((k.upper() for k,v in checks.items() if not v),"RISK_REJECTED");size=min(requested,cfg["max_position_size"],max(0,cfg["max_total_exposure"]-exposure)) if approved else 0;return {"approved":approved and size>0,"action":action,"requested_position_size":requested,"approved_position_size":size,"confidence":confidence,"net_edge_pct":edge,"checks":checks,"reason":reason if approved else f"{reason}:FAILED","timestamp":datetime.now(timezone.utc).isoformat()}
