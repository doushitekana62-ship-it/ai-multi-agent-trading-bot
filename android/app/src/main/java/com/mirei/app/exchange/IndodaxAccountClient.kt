package com.mirei.app.exchange

import com.mirei.app.security.ExchangeCredentials
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

data class IndodaxAccountSnapshot(
    val idrAvailable: Double,
    val idrHold: Double,
    val balances: Map<String, Double>,
    val serverTimeMs: Long,
)

/**
 * Read-only INDODAX Trade API V2 account client.
 *
 * This client intentionally exposes no order methods. Do not add order execution here.
 */
class IndodaxAccountClient(
    private val credentials: ExchangeCredentials,
    private val timeoutMs: Int = 10_000,
) {
    fun getInfo(): IndodaxAccountSnapshot {
        require(credentials.exchangeId == "indodax") { "unsupported_exchange:" + credentials.exchangeId }
        require(credentials.apiKey.isNotBlank()) { "indodax_api_key_missing" }
        require(credentials.apiSecret.isNotBlank()) { "indodax_api_secret_missing" }
        require(timeoutMs in 1_000..30_000) { "invalid_indodax_timeout" }

        val timestamp = System.currentTimeMillis()
        val query = "timestamp=$timestamp&recvWindow=5000"
        val signature = hmacSha512(credentials.apiSecret, query)
        val connection = (URL("$BASE_URL/api/v2/account?$query").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = timeoutMs
            readTimeout = timeoutMs
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-APIKEY", credentials.apiKey)
            setRequestProperty("Sign", signature)
        }

        return try {
            val responseCode = connection.responseCode
            val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
                ?: throw IllegalStateException("indodax_http_error:$responseCode")
            val responseText = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
            val root = JSONObject(responseText)
            if (responseCode !in 200..299) {
                val code = root.optInt("code", responseCode)
                throw IllegalStateException("indodax_api_error:$code")
            }
            if (root.has("code") && root.optInt("code", 0) != 0) {
                throw IllegalStateException("indodax_api_error:" + root.optInt("code"))
            }
            val balanceRows = root.optJSONArray("balances")
                ?: throw IllegalStateException("indodax_missing_balances")
            parseAccountSnapshot(balanceRows, timestamp)
        } finally {
            connection.disconnect()
        }
    }

    internal fun parseAccountSnapshot(rows: JSONArray, timestamp: Long): IndodaxAccountSnapshot {
        val available = linkedMapOf<String, Double>()
        val held = linkedMapOf<String, Double>()
        for (index in 0 until rows.length()) {
            val row = rows.optJSONObject(index) ?: throw IllegalStateException("indodax_invalid_balance_row")
            val asset = row.optString("asset", "").trim().lowercase()
            if (asset.isBlank() || available.containsKey(asset)) {
                throw IllegalStateException("indodax_invalid_or_duplicate_asset")
            }
            available[asset] = readAmount(row, "free")
            held[asset] = readAmount(row, "locked")
        }
        val idrAvailable = available["idr"] ?: throw IllegalStateException("indodax_missing_balance_field:idr")
        val idrHold = held["idr"] ?: throw IllegalStateException("indodax_missing_locked_field:idr")
        return IndodaxAccountSnapshot(
            idrAvailable = idrAvailable,
            idrHold = idrHold,
            balances = available,
            // V2 account response does not expose server time; this is the local request timestamp.
            serverTimeMs = timestamp,
        )
    }

    private fun readAmount(source: JSONObject, field: String): Double {
        if (!source.has(field) || source.isNull(field)) {
            throw IllegalStateException("indodax_missing_balance_field:$field")
        }
        val raw = source.optString(field, "").trim()
        val amount = raw.toDoubleOrNull()
            ?: throw IllegalStateException("indodax_invalid_balance_field:$field")
        if (!amount.isFinite() || amount < 0.0) {
            throw IllegalStateException("indodax_invalid_balance_field:$field")
        }
        return amount
    }

    private fun hmacSha512(secret: String, value: String): String {
        val mac = Mac.getInstance("HmacSHA512")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA512"))
        return mac.doFinal(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private companion object {
        const val BASE_URL = "https://tapi.indodax.com"
    }
}
