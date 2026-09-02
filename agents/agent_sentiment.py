"""Market-sentiment specialist using only the shared Indodax market snapshot.

No news, social feed, fear/greed vendor, or alternate exchange is consulted.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime,timezone
from typing import Any,Dict,List,Optional
import numpy as np
from core.signal_contract import SignalStatus,safe_float,utc_age_seconds

@dataclass
class SentimentResult:
    symbol:str;timestamp:datetime;overall_score:float;sentiment_label:str;confidence:float;news_sentiment:float;social_sentiment:float;price_momentum:float;fear_greed_index:float;source_contributions:Dict[str,float];key_events:List[str];summary:str;direction:str="NEUTRAL";score:float=0.0;timeframe:str="1m";evidence:List[str]=field(default_factory=list);data_timestamp:datetime=field(default_factory=lambda:datetime.now(timezone.utc));data_age_seconds:float=0.0;status:str=SignalStatus.OK.value;limitations:List[str]=field(default_factory=list)

class SentimentAgent:
    def __init__(self,config:Optional[Dict[str,Any]]=None):
        cfg=config or {};self.max_age_seconds=float(cfg.get("max_age_seconds",30));self.max_contribution=float(cfg.get("max_contribution",1.0))
    def analyze(self,symbol:str,market_data:Optional[Dict[str,Any]]=None)->SentimentResult:
        data=market_data or {};symbol=str(symbol).upper();timestamp=data.get("timestamp",datetime.now(timezone.utc));age=utc_age_seconds(timestamp);points=data.get("recent_trades") or [];closes=[safe_float(x.get("price")) for x in points if isinstance(x,dict) and safe_float(x.get("price"))>0]
        if len(closes)<2:return self._result(symbol,0,0,"INSUFFICIENT_INDODAX_OBSERVATIONS",age,SignalStatus.UNAVAILABLE.value,[])
        momentum=float(np.clip((closes[-1]/closes[max(0,len(closes)-6)]-1)*12,-1,1))
        trades=[x for x in points[-120:] if isinstance(x,dict) and str(x.get("observation_type","TRADE")).upper()=="TRADE"];buy=sum(1 for x in trades if str(x.get("side") or x.get("type") or "").lower()=="buy");sell=sum(1 for x in trades if str(x.get("side") or x.get("type") or "").lower()=="sell");imbalance=(buy-sell)/max(1,buy+sell)
        candles=data.get("ohlcv") or [];volumes=[safe_float(x.get("volume")) for x in candles if isinstance(x,dict) and safe_float(x.get("volume"))>0];volume_confirmation=0.0
        if len(volumes)>=10:
            baseline=sum(volumes[-10:-1])/9;volume_confirmation=float(np.clip((volumes[-1]/baseline-1)/0.75,-1,1)) if baseline>0 else 0.0
        score=float(np.clip(momentum*0.50+imbalance*0.30+volume_confirmation*0.20,-self.max_contribution,self.max_contribution));direction="BULLISH" if score>=0.10 else "BEARISH" if score<=-0.10 else "NEUTRAL";confidence=float(np.clip(0.45+abs(score)*0.35+min(len(trades)/60,1)*0.15,0.30,0.80))
        return self._result(symbol,score,confidence,"OK",age,SignalStatus.OK.value,[f"momentum={momentum:+.2f}",f"tape_imbalance={imbalance:+.2f}",f"volume_confirmation={volume_confirmation:+.2f}"],direction)
    def _result(self,symbol,score,confidence,reason,age,status,evidence,direction=None,fg=0.0):
        direction=direction or ("BULLISH" if score>0.10 else "BEARISH" if score<-0.10 else "NEUTRAL")
        return SentimentResult(symbol=symbol,timestamp=datetime.now(timezone.utc),overall_score=score,sentiment_label=direction,confidence=confidence,news_sentiment=0.0,social_sentiment=0.0,price_momentum=score,fear_greed_index=fg,source_contributions={"indodax_tape":score},key_events=[],summary=f"Indodax market sentiment {symbol}: {reason}; tape-only.",direction=direction,score=score,evidence=evidence+[reason],data_timestamp=datetime.now(timezone.utc),data_age_seconds=age,status=status,limitations=["Indodax public market data only","No external sentiment feed"])
