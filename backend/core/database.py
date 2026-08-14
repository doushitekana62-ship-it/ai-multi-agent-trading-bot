import os
import logging
from typing import Optional, Dict, Any, List

from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("https://opclkckfdlkqzunzmwym.supabase.co")
SUPABASE_KEY = os.getenv("sb_publishable_uoNDfyIKNCkA7hEWgemVsw_uae5Q6gN")


class SupabaseDatabase:
    """
    Centralized Supabase database client.

    Semua operasi database backend diarahkan melalui class ini.
    """

    def __init__(self):
        self.client: Optional[Client] = None

        if SUPABASE_URL and SUPABASE_KEY:
            try:
                self.client = create_client(
                    SUPABASE_URL,
                    SUPABASE_KEY
                )

                logger.info("Supabase connection initialized")

            except Exception as e:
                logger.error(
                    f"Failed to initialize Supabase: {e}"
                )
        else:
            logger.warning(
                "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY "
                "is not configured"
            )

    def is_connected(self) -> bool:
        return self.client is not None

    # ---------------------------------------------------------
    # GENERIC SELECT
    # ---------------------------------------------------------

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:

        if not self.client:
            return []

        try:
            query = self.client.table(table).select(columns)

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            response = query.execute()

            return response.data or []

        except Exception as e:
            logger.error(
                f"Supabase SELECT error [{table}]: {e}"
            )
            return []

    # ---------------------------------------------------------
    # INSERT
    # ---------------------------------------------------------

    def insert(
        self,
        table: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:

        if not self.client:
            return None

        try:
            response = (
                self.client
                .table(table)
                .insert(data)
                .execute()
            )

            if response.data:
                return response.data[0]

            return None

        except Exception as e:
            logger.error(
                f"Supabase INSERT error [{table}]: {e}"
            )
            return None

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:

        if not self.client:
            return None

        try:
            query = self.client.table(table).update(data)

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()

            if response.data:
                return response.data[0]

            return None

        except Exception as e:
            logger.error(
                f"Supabase UPDATE error [{table}]: {e}"
            )
            return None

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------

    def delete(
        self,
        table: str,
        filters: Dict[str, Any]
    ) -> bool:

        if not self.client:
            return False

        try:
            query = self.client.table(table).delete()

            for key, value in filters.items():
                query = query.eq(key, value)

            query.execute()

            return True

        except Exception as e:
            logger.error(
                f"Supabase DELETE error [{table}]: {e}"
            )
            return False


# Singleton
db = SupabaseDatabase()
