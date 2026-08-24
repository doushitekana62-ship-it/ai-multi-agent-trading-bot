"""
Reports Routes

Daily / Weekly / Monthly / All-Time
performance reports from Supabase.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Query,
    status
)

from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from backend.core.security import verify_token
from backend.core.database import get_supabase


logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

supabase = get_supabase()


# =========================================================
# AUTH
# =========================================================

def authenticate(
    credentials: HTTPAuthorizationCredentials
):
    """
    Verify JWT token.
    """

    token = credentials.credentials

    payload = verify_token(token)

    if not payload:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


# =========================================================
# GET ALL TRADES
# =========================================================

def get_all_trades():

    response = (
        supabase
        .table("trades")
        .select("*")
        .order("created_at", desc=False)
        .execute()
    )

    return response.data or []


# =========================================================
# REPORT CALCULATOR
# =========================================================

def generate_report(trades):

    if not trades:

        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
            "profit_factor": 0.0
        }

    pnls = [
        float(trade.get("pnl") or 0)
        for trade in trades
    ]

    total_trades = len(pnls)

    winning_trades = sum(
        1
        for pnl in pnls
        if pnl > 0
    )

    losing_trades = sum(
        1
        for pnl in pnls
        if pnl < 0
    )

    total_pnl = sum(pnls)

    avg_pnl = (
        total_pnl / total_trades
        if total_trades > 0
        else 0
    )

    win_rate = (
        winning_trades / total_trades
        if total_trades > 0
        else 0
    )

    gross_profit = sum(
        pnl
        for pnl in pnls
        if pnl > 0
    )

    gross_loss = abs(
        sum(
            pnl
            for pnl in pnls
            if pnl < 0
        )
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit / gross_loss
        )

    else:

        profit_factor = (
            float("inf")
            if gross_profit > 0
            else 0
        )

    return {
        "total_trades": total_trades,

        "winning_trades": winning_trades,

        "losing_trades": losing_trades,

        "win_rate": win_rate,

        "total_pnl": total_pnl,

        "avg_pnl": avg_pnl,

        "max_profit": max(pnls),

        "max_loss": min(pnls),

        "profit_factor": profit_factor
    }


# =========================================================
# DAILY
# =========================================================

@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = Query(
        default=None,
        description="YYYY-MM-DD"
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    authenticate(credentials)

    try:

        if date:

            report_date = datetime.strptime(
                date,
                "%Y-%m-%d"
            )

        else:

            report_date = datetime.now()

        start = report_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        end = start + timedelta(days=1)

        trades = get_all_trades()

        filtered_trades = []

        for trade in trades:

            created_at = trade.get("created_at")

            if not created_at:
                continue

            trade_date = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            )

            # Make comparison timezone-safe
            trade_date = trade_date.replace(
                tzinfo=None
            )

            if start <= trade_date < end:

                filtered_trades.append(trade)

        report = generate_report(
            filtered_trades
        )

        return {
            "report_type": "daily",

            "date": start.date().isoformat(),

            **report,

            "timestamp":
                datetime.now().isoformat()
        }

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    except Exception:

        logger.exception(
            "Error generating daily report"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to generate daily report"
        )


# =========================================================
# WEEKLY
# =========================================================

@router.get("/weekly")
async def get_weekly_report(
    week: Optional[str] = Query(
        default=None,
        description="YYYY-Www"
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    authenticate(credentials)

    try:

        now = datetime.now()

        if week:

            year, week_number = week.split("-W")

            year = int(year)
            week_number = int(week_number)

            start = datetime.fromisocalendar(
                year,
                week_number,
                1
            )

        else:

            start = (
                now
                - timedelta(days=now.weekday())
            ).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

        end = start + timedelta(days=7)

        trades = get_all_trades()

        filtered_trades = []

        for trade in trades:

            created_at = trade.get("created_at")

            if not created_at:
                continue

            trade_date = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).replace(tzinfo=None)

            if start <= trade_date < end:

                filtered_trades.append(trade)

        report = generate_report(
            filtered_trades
        )

        return {
            "report_type": "weekly",

            "week_start":
                start.date().isoformat(),

            "week_end":
                (end - timedelta(days=1))
                .date()
                .isoformat(),

            **report,

            "timestamp":
                datetime.now().isoformat()
        }

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid week format. Use YYYY-W01"
        )

    except Exception:

        logger.exception(
            "Error generating weekly report"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to generate weekly report"
        )


# =========================================================
# MONTHLY
# =========================================================

@router.get("/monthly")
async def get_monthly_report(
    month: Optional[str] = Query(
        default=None,
        description="YYYY-MM"
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    authenticate(credentials)

    try:

        now = datetime.now()

        if month:

            year, month_number = map(
                int,
                month.split("-")
            )

            start = datetime(
                year,
                month_number,
                1
            )

        else:

            start = datetime(
                now.year,
                now.month,
                1
            )

        if start.month == 12:

            end = datetime(
                start.year + 1,
                1,
                1
            )

        else:

            end = datetime(
                start.year,
                start.month + 1,
                1
            )

        trades = get_all_trades()

        filtered_trades = []

        for trade in trades:

            created_at = trade.get("created_at")

            if not created_at:
                continue

            trade_date = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).replace(tzinfo=None)

            if start <= trade_date < end:

                filtered_trades.append(trade)

        report = generate_report(
            filtered_trades
        )

        return {
            "report_type": "monthly",

            "month":
                start.strftime("%Y-%m"),

            "month_start":
                start.date().isoformat(),

            "month_end":
                (end - timedelta(days=1))
                .date()
                .isoformat(),

            **report,

            "timestamp":
                datetime.now().isoformat()
        }

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid month format. Use YYYY-MM"
        )

    except Exception:

        logger.exception(
            "Error generating monthly report"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to generate monthly report"
        )


# =========================================================
# ALL TIME
# =========================================================

@router.get("/all-time")
async def get_all_time_report(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    authenticate(credentials)

    try:

        trades = get_all_trades()

        report = generate_report(
            trades
        )

        if trades:

            timestamps = []

            for trade in trades:

                created_at = trade.get(
                    "created_at"
                )

                if created_at:

                    timestamp = datetime.fromisoformat(
                        created_at.replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    timestamps.append(
                        timestamp.replace(
                            tzinfo=None
                        )
                    )

            if timestamps:

                first_trade = min(
                    timestamps
                )

                days_trading = max(
                    1,
                    (datetime.now() - first_trade).days
                )

            else:

                days_trading = 0

            report["days_trading"] = days_trading

            report["avg_daily_trades"] = (
                len(trades) /
                max(1, days_trading)
            )

        else:

            report["days_trading"] = 0

            report["avg_daily_trades"] = 0

        return {
            "report_type": "all_time",

            **report,

            "timestamp":
                datetime.now().isoformat()
        }

    except Exception:

        logger.exception(
            "Error generating all-time report"
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to generate all-time report"
        )
