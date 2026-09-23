package com.mirei.app.exchange

import com.mirei.app.security.ExchangeCredentials
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

class IndodaxAccountClient(
    private val credentials: ExchangeCredentials,
    private val timeoutMs: Int = 10_000,
) {
    fun getInfo(): IndodaxAccountSnapshot {
        require(credentials.exchangeId == "indodax") { "unsupported_exchange:" + credentials.exchangeId }

        val timestamp = System.currentTimeMillis()
        val body = "method=getInfo&timestamp=" + timestamp + "&recvWindow=5000"
        val signature = hmacSha512(credentials.apiSecret, body)

        val connection = (URL("https://indodax.com/tapi").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = timeoutMs
            readTimeout = timeoutMs
            doOutput = true
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            setRequestProperty("Key", credentials.apiKey)
            setRequestProperty("Sign", signature)
        }

        return try {
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val responseText = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
            val root = JSONObject(responseText)
            if (root.optInt("success", 0) != 1) {
                throw IllegalStateException(root.optString("error", "indodax_api_error"))
            }
            val result = root.optJSONObject("return") ?: throw IllegalStateException("indodax_missing_return")
            val balance = result.optJSONObject("balance") ?: JSONObject()
            val hold = result.optJSONObject("balance_hold") ?: JSONObject()
            val balances = linkedMapOf<String, Double>()
            balance.keys().forEach { symbol ->
                balances[symbol.lowercase()] = balance.optString(symbol).toDoubleOrNull() ?: balance.optDouble(symbol, 0.0)
            }
            IndodaxAccountSnapshot(
                idrAvailable = balance.optString("idr").toDoubleOrNull() ?: balance.optDouble("idr", 0.0),
                idrHold = hold.optString("idr").toDoubleOrNull() ?: hold.optDouble("idr", 0.0),
                balances = balances,
                serverTimeMs = result.optLong("server_time", timestamp),
            )
        } finally {
            connection.disconnect()
        }
    }

    private fun hmacSha512(secret: String, body: String): String {
        val mac = Mac.getInstance("HmacSHA512")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA512"))
        return mac.doFinal(body.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }
}
