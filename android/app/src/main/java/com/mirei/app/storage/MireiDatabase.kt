package com.mirei.app.storage

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class MireiDatabase(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                stake_idr REAL NOT NULL,
                fee_idr REAL NOT NULL DEFAULT 0,
                pnl_idr REAL NOT NULL DEFAULT 0,
                opened_at INTEGER NOT NULL,
                closed_at INTEGER,
                exit_reason TEXT
            )"""
        )
        db.execSQL(
            """CREATE TABLE suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                outcome TEXT
            )"""
        )
        db.execSQL(
            """CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL
            )"""
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            db.execSQL("ALTER TABLE trades ADD COLUMN exit_reason TEXT")
        }
    }

    fun recordAudit(eventType: String, details: String, nowMs: Long = System.currentTimeMillis()) {
        writableDatabase.insertOrThrow(
            "audit_log",
            null,
            ContentValues().apply {
                put("created_at", nowMs)
                put("event_type", eventType)
                put("details", details)
            },
        )
    }

    fun recordSuggestion(
        symbol: String,
        action: String,
        confidence: Double,
        reason: String,
        nowMs: Long = System.currentTimeMillis(),
    ): Long = writableDatabase.insertOrThrow(
        "suggestions",
        null,
        ContentValues().apply {
            put("created_at", nowMs)
            put("symbol", symbol)
            put("action", action)
            put("confidence", confidence)
            put("reason", reason)
        },
    )

    companion object {
        private const val DB_NAME = "mirei.db"
        private const val DB_VERSION = 2
    }
}
