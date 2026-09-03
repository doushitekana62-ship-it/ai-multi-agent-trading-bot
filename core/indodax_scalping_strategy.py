"""Single-source Indodax compounding-scalping strategy."""
from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

SOURCE="INDODAX public market data"
STRATEGY_VERSION="compounding-scalping-v3"
BASE_TP_PCT=0.40
BASE_SL_PCT=0.50

def _num(v,default=0.0):
    try:
        x=float(v);return x if isfinite(x) else default
    except (TypeError,ValueError):return default

def _clip(v,lo=-1.0,hi=1.0):return max(lo,min(hi,_num(v)))

def _ts(v):
    if isinstance(v,datetime):return v.timestamp()
    if isinstance(v,str):
        try:return datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()
        except ValueError:pass
    x=_num(v);return x/1000.0 if x>1_000_000_000_000 else x

def _candles(points:List[Dict[str,Any]],now_ts:float)->List[Dict[str,Any]]:
    buckets={};current=int(now_ts//60)*60
    for p in points[-1440:]:
        if not isinstance(p,dict):continue
        ts=_ts(p.get("timestamp") or p.get("date"));price=_num(p.get("price"))
        if ts<=0 or price<=0 or ts<current-30*60 or ts>now_ts+2:continue
        b=int(ts//60)*60;row=buckets.setdefault(b,{"timestamp":b,"open":price,"high":price,"low":price,"close":price,"volume":0.0,"trades":0,"observations":0})
        row["high"]=max(row["high"],price);row["low"]=min(row["low"],price);row["close"]=price;row["volume"]+=max(0.0,_num(p.get("amount")));row["trades"]+=1 if str(p.get("observation_type","TRADE")).upper()=="TRADE" else 0;row["observations"]+=1
    return [buckets[k] for k in sorted(buckets)]

def _move(points:List[Dict[str,Any]],now_ts:float,minutes:int)->Optional[float]:
    cutoff=now_ts-minutes*60;rows=[]
    for p in points:
        if not isinstance(p,dict):continue
        ts=_ts(p.get("timestamp") or p.get("date"));price=_num(p.get("price"))
        if cutoff<=ts<=now_ts and price>0:rows.append((ts,price))
    rows.sort()
    if len(rows)<2 or rows[0][1]<=0:return None
    return (rows[-1][1]/rows[0][1]-1.0)*100.0

def _pulse(points:List[Dict[str,Any]],now_ts:float)->Dict[str,Any]:
    current=int(now_ts//60)*60;by_minute={}
    for p in points:
        if not isinstance(p,dict):continue
        ts=_ts(p.get("timestamp") or p.get("date"));price=_num(p.get("price"))
        if price>0 and current-29*60<=ts<=now_ts+2:by_minute.setdefault(int(ts//60)*60,[]).append((ts,price))
    segments=[]
    for i in range(30):
        b=current-(29-i)*60;rows=sorted(by_minute.get(b,[]))
        if len(rows)>=2:
            o,c=rows[0][1],rows[-1][1];move=(c/o-1)*100 if o else 0;status="GREEN" if move>0 else "RED" if move<0 else "GRAY"
        else:o=rows[0][1] if rows else None;c=rows[-1][1] if rows else None;move=None;status="GRAY"
        segments.append({"timestamp":datetime.fromtimestamp(b,timezone.utc).isoformat(),"status":status,"move_pct":move,"observations":len(rows),"open":o,"close":c})
    populated=[x for x in segments if x["observations"]>=2 and x["open"]]
    if populated:net=(populated[-1]["close"]/populated[0]["open"]-1)*100;overall="GREEN" if net>0 else "RED" if net<0 else "GRAY"
    else:net,overall=None,"GRAY"
    return {"segments":segments,"overall":overall,"current":segments[-1]["status"],"net_move_pct":net}

def _rsi(closes:List[float],period:int=14)->float:
    if len(closes)<=period:return 50.0
    changes=[closes[i]-closes[i-1] for i in range(len(closes)-period,len(closes))];gains=[x for x in changes if x>0];losses=[-x for x in changes if x<0];ag,al=sum(gains)/period,sum(losses)/period
    if al==0:return 100.0 if ag>0 else 50.0
    return 100.0-100.0/(1+ag/al)

def _role(agent,direction,score,confidence,evidence):
    return {"agent":agent,"direction":direction,"score":round(_clip(score),6),"confidence":round(max(0,min(1,_num(confidence))),6),"timeframe":"1m","status":"OK","data_source":SOURCE,"evidence":evidence,"data_age_seconds":0.0}

def _forecast_exit(position:Dict[str,Any],price:float,forecast:float,m1:float,m3:float,m5:float,volatility:float)->Dict[str,Any]:
    entry=_num(position.get("entry_price"));side=str(position.get("side") or position.get("action") or "BUY").upper()
    if entry<=0:return {"exit_action":"HOLD","exit_reason":"INVALID_ENTRY"}
    pnl_pct=((price/entry)-1)*100 if side=="BUY" else ((entry/price)-1)*100
    if pnl_pct<BASE_TP_PCT:return {"exit_action":"HOLD","exit_reason":"TP_NOT_REACHED","pnl_pct":pnl_pct,"take_profit_pct":BASE_TP_PCT}
    continuation=forecast>=.25 and m1>0 and m3>0 and m5>0
    if continuation and forecast>=.45 and m3>=.10:
        trail=max(.10,min(.25,abs(volatility)*100*1.5));return {"exit_action":"HOLD","exit_reason":"TP_HIT_FORECAST_CONTINUATION","pnl_pct":pnl_pct,"take_profit_pct":BASE_TP_PCT,"trailing_stop_pct":trail,"forecast":forecast}
    if continuation:return {"exit_action":"HOLD","exit_reason":"TP_HIT_FORECAST_EXTEND","pnl_pct":pnl_pct,"take_profit_pct":BASE_TP_PCT,"trailing_stop_pct":.15,"forecast":forecast}
    return {"exit_action":"SELL","exit_reason":"TP_HIT_NO_CONTINUATION","pnl_pct":pnl_pct,"take_profit_pct":BASE_TP_PCT,"forecast":forecast}

def analyze(symbol:str,market_data:Dict[str,Any],*,fee_rate:float=.0015,slippage_rate:float=.0002,min_edge_pct:float=.45,position:Optional[Dict[str,Any]]=None)->Dict[str,Any]:
    symbol=str(symbol).upper().replace("_","/");points=[p for p in (market_data.get("recent_trades") or []) if isinstance(p,dict)];now_ts=max([_ts(p.get("timestamp") or p.get("date")) for p in points]+[_ts(market_data.get("timestamp")),datetime.now(timezone.utc).timestamp()]);price=_num(market_data.get("current_price") or market_data.get("unified_price"))
    if price<=0:return {"action":"HOLD","confidence":0.0,"reason":"INVALID_PRICE","data_source":SOURCE}
    candles=_candles(points,now_ts);closes=[x["close"] for x in candles];moves={m:_move(points,now_ts,m) for m in (1,3,5,15,30)};m1,m3,m5,m15,m30=[moves[x] or 0.0 for x in (1,3,5,15,30)];pulse=_pulse(points,now_ts)
    technical=_clip((m1/.08)*.35+(m5/.20)*.25+(m15/.45)*.20)
    if len(candles)>=10:
        recent,prior=candles[-5:],candles[-10:-5];hh=max(x["high"] for x in recent)>max(x["high"] for x in prior);hl=min(x["low"] for x in recent)>min(x["low"] for x in prior);lh=max(x["high"] for x in recent)<max(x["high"] for x in prior);ll=min(x["low"] for x in recent)<min(x["low"] for x in prior);structure=1 if hh and hl else -1 if lh and ll else .25 if hh or hl else -.25 if lh or ll else 0;technical=_clip(technical*.75+structure*.25)
    rsi=_rsi(closes);technical=_clip(technical+(.08 if 52<=rsi<=68 else -.08 if 32<=rsi<=48 else 0))
    one_minute_returns=[closes[i]/closes[i-1]-1 for i in range(max(1,len(closes)-12),len(closes)) if closes[i-1]>0];mean_ret=mean(one_minute_returns) if one_minute_returns else 0;vol=pstdev(one_minute_returns) if len(one_minute_returns)>=3 else .001;last5=one_minute_returns[-5:];persistence=(sum(x>0 for x in last5)-sum(x<0 for x in last5))/max(1,len(last5));forecast=_clip((m3/.12)*.45+(m5/.20)*.25+persistence*.20+_clip(mean_ret/max(vol,.0005))*.10)
    trade_rows=[p for p in points if str(p.get("observation_type","TRADE")).upper()=="TRADE"];buys=sum(1 for p in trade_rows[-60:] if str(p.get("side") or p.get("type") or "").lower()=="buy");sells=sum(1 for p in trade_rows[-60:] if str(p.get("side") or p.get("type") or "").lower()=="sell");imbalance=(buys-sells)/max(1,buys+sells);sentiment=_clip((m1/.10)*.40+(m30/.60)*.25+imbalance*.35)
    volumes=[x["volume"] for x in candles if x["volume"]>0];baseline=mean(volumes[-10:-1]) if len(volumes)>=10 else 0;volume_ratio=volumes[-1]/baseline if baseline>0 else 1;volume_confirmation=_clip((volume_ratio-1)/.75,0,1);regime=_clip((m30/.80)*.60+(m15/.45)*.40);pulse_score=1 if pulse["current"]=="GREEN" else -1 if pulse["current"]=="RED" else 0;raw_edge=_clip(technical*.30+forecast*.30+sentiment*.15+regime*.15+pulse_score*.10);expected_move_pct=abs(raw_edge)*1.10;friction_pct=(fee_rate*2+slippage_rate*2)*100;net_edge_pct=expected_move_pct-friction_pct;confirmations=sum([abs(technical)>=.25,abs(forecast)>=.25,abs(sentiment)>=.20,abs(regime)>=.25,volume_confirmation>=.20]);direction="BUY" if raw_edge>0 else "SELL" if raw_edge<0 else "HOLD";confidence=_clip(.45+abs(raw_edge)*.35+min(confirmations/5,1)*.20,0,.90);action=direction if confirmations>=3 and net_edge_pct>=min_edge_pct else "HOLD"
    if action=="HOLD" and abs(m1)>=.15 and abs(m5)>=.25 and confirmations>=2 and net_edge_pct>=min_edge_pct*.85:action=direction
    if action=="HOLD":confidence=min(confidence,.59)
    exit_plan=_forecast_exit(position,price,forecast,m1,m3,m5,vol) if position else {"exit_action":"HOLD","exit_reason":"NO_OPEN_POSITION","take_profit_pct":BASE_TP_PCT}
    if position and exit_plan.get("exit_action")=="SELL":action="SELL"
    roles={"technical":_role("Technical Agent","BULLISH" if technical>.1 else "BEARISH" if technical<-.1 else "NEUTRAL",technical,.55+abs(technical)*.30,[f"1m={m1:+.3f}%",f"5m={m5:+.3f}%",f"15m={m15:+.3f}%",f"RSI={rsi:.1f}"]),"forecast":_role("Forecast Agent","BULLISH" if forecast>.1 else "BEARISH" if forecast<-.1 else "NEUTRAL",forecast,.50+abs(forecast)*.30,[f"3m={m3:+.3f}%",f"5m={m5:+.3f}%",f"persistence={persistence:+.2f}"]),"sentiment":_role("Sentiment Agent","BULLISH" if sentiment>.1 else "BEARISH" if sentiment<-.1 else "NEUTRAL",sentiment,.45+abs(sentiment)*.25,[f"tape_imbalance={imbalance:+.2f}",f"30m={m30:+.3f}%","source=INDODAX tape only"]),"librarian":_role("Trading Librarian","BULLISH" if pulse["current"]=="GREEN" else "BEARISH" if pulse["current"]=="RED" else "NEUTRAL",.20 if pulse["current"]=="GREEN" else -.20 if pulse["current"]=="RED" else 0,.55 if pulse["current"]!="GRAY" else .35,[f"30x1m pulse={pulse['overall']}",f"current_segment={pulse['current']}"]),"decision":_role("Decision Agent","BULLISH" if raw_edge>0 else "BEARISH" if raw_edge<0 else "NEUTRAL",raw_edge,confidence,[f"net_edge={net_edge_pct:+.3f}%",f"confirmations={confirmations}/5",f"friction={friction_pct:.3f}%"]),"reflection":_role("Reflector Agent","BULLISH" if action=="BUY" else "BEARISH" if action=="SELL" else "NEUTRAL",raw_edge,confidence,["same Indodax snapshot","risk remains downstream","no alternate data source"])}
    position_size=min(.10,max(0,(net_edge_pct/1)*.10)) if action in {"BUY","SELL"} else 0
    return {"strategy_version":STRATEGY_VERSION,"data_source":SOURCE,"symbol":symbol,"price":price,"action":action,"candidate_action":direction,"confidence":confidence,"score":raw_edge,"expected_move_pct":expected_move_pct,"friction_pct":friction_pct,"net_edge_pct":net_edge_pct,"confirmations":confirmations,"moves":{f"move_{k}m_pct":moves[k] for k in moves},"pulse":pulse,"volume_ratio":volume_ratio,"volatility_1m":vol,"position_size":position_size,"exit_plan":exit_plan,"take_profit_pct":BASE_TP_PCT,"stop_loss_pct":BASE_SL_PCT,"agents":roles,"summary":f"{symbol} {action}: edge={raw_edge:+.3f}, net_edge={net_edge_pct:+.3f}%, confirmations={confirmations}/5","reason":exit_plan.get("exit_reason") if position else ("NET_EDGE_AVAILABLE" if action!="HOLD" else "NO_NET_EDGE")}
