import os
import logging
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)


class SupabaseDatabase:
    def __init__(self):
        self.client: Optional[Client] = None

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

        if not url or not key:
            logger.warning(
                "Supabase environment variables are missing. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )
            return

        try:
            self.client = create_client(url, key)
            logger.info("Supabase connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")

    def is_connected(self) -> bool:
        return self.client is not None

    def save_decision(self, symbol: str, action: str, confidence: float,
                      reasoning: str, agent_votes: Dict[str, Any]):
        if not self.client:
            logger.warning("Supabase not connected. Decision not saved.")
            return None
        data = {
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
            "agent_votes": agent_votes,
        }
        try:
            return self.client.table("decisions").insert(data).execute().data
        except Exception as e:
            logger.error(f"Failed to save decision: {e}")
            return None

    def save_trade(self, symbol: str, action: str, price: float,
                   quantity: float, pnl: float = 0.0, confidence: float = 0.0):
        if not self.client:
            logger.warning("Supabase not connected. Trade not saved.")
            return None
        data = {
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "confidence": confidence,
        }
        try:
            return self.client.table("trades").insert(data).execute().data
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            return None

    def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            response = (
                self.client.table("trades")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def get_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            response = (
                self.client.table("decisions")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get decisions: {e}")
            return []


db = SupabaseDatabase()


def get_supabase() -> SupabaseDatabase:
    return db
