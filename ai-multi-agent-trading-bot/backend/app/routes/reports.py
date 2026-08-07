"""
Reports Routes
Daily, weekly, monthly performance reports
"""

import os
import sys
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.app.core.security import verify_token
from exchange_integration.paper_trading import PaperTrading

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router
router = APIRouter()
security = HTTPBearer()

# Initialize paper trading
paper_trading = PaperTrading()

def generate_report(trades: List[Dict]) -> Dict:
    """
    Generate report from trades
    """
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
            "profit_factor": 0.0,
            "winning_trades": 0,
            "losing_trades": 0
        }
    
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losing_trades = sum(1 for t in trades if t.get("pnl", 0) < 0)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    
    pnls = [t.get("pnl", 0) for t in trades]
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "max_profit": max(pnls) if pnls else 0,
        "max_loss": min(pnls) if pnls else 0,
        "profit_factor": profit_factor
    }

@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get daily report
    """
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Parse date
        if date:
            report_date = datetime.fromisoformat(date)
        else:
            report_date = datetime.now()
        
        # Filter trades for the day
        trades = paper_trading.trade_history
        daily_trades = [
            t for t in trades
            if datetime.fromisoformat(t.get("exit_time", "")).date() == report_date.date()
        ]
        
        report = generate_report(daily_trades)
        
        return {
            "report_type": "daily",
            "date": report_date.date().isoformat(),
            **report,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get daily report"
        )

@router.get("/weekly")
async def get_weekly_report(
    week: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get weekly report
    """
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Get current week
        now = datetime.now()
        if week:
            # Parse week format: "2024-W01"
            year, week_num = week.split('-W')
            start_date = datetime.strptime(f"{year}-{week_num}-1", "%Y-%W-%w")
        else:
            start_date = now - timedelta(days=now.weekday())
        
        end_date = start_date + timedelta(days=7)
        
        # Filter trades for the week
        trades = paper_trading.trade_history
        weekly_trades = [
            t for t in trades
            if start_date <= datetime.fromisoformat(t.get("exit_time", "")) < end_date
        ]
        
        report = generate_report(weekly_trades)
        
        return {
            "report_type": "weekly",
            "week_start": start_date.date().isoformat(),
            "week_end": end_date.date().isoformat(),
            **report,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting weekly report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get weekly report"
        )

@router.get("/monthly")
async def get_monthly_report(
    month: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get monthly report
    """
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Get current month
        now = datetime.now()
        if month:
            # Parse month format: "2024-01"
            year, month_num = map(int, month.split('-'))
            start_date = datetime(year, month_num, 1)
        else:
            start_date = datetime(now.year, now.month, 1)
        
        # Calculate end of month
        if start_date.month == 12:
            end_date = datetime(start_date.year + 1, 1, 1)
        else:
            end_date = datetime(start_date.year, start_date.month + 1, 1)
        
        # Filter trades for the month
        trades = paper_trading.trade_history
        monthly_trades = [
            t for t in trades
            if start_date <= datetime.fromisoformat(t.get("exit_time", "")) < end_date
        ]
        
        report = generate_report(monthly_trades)
        
        return {
            "report_type": "monthly",
            "month": start_date.strftime("%Y-%m"),
            "month_start": start_date.date().isoformat(),
            "month_end": end_date.date().isoformat(),
            **report,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting monthly report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get monthly report"
        )

@router.get("/all-time")
async def get_all_time_report(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get all-time report
    """
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        trades = paper_trading.trade_history
        report = generate_report(trades)
        
        # Additional metrics
        if trades:
            # Total days trading
            first_trade = min(datetime.fromisoformat(t.get("entry_time", "")) for t in trades)
            days_trading = (datetime.now() - first_trade).days
            
            report["days_trading"] = days_trading
            report["avg_daily_trades"] = len(trades) / max(1, days_trading)
        else:
            report["days_trading"] = 0
            report["avg_daily_trades"] = 0
        
        return {
            "report_type": "all_time",
            **report,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting all-time report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get all-time report"
        )
