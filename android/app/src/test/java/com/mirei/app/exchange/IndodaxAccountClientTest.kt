package com.mirei.app.exchange

import com.mirei.app.security.ExchangeCredentials
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class IndodaxAccountClientTest {
    private val client = IndodaxAccountClient(
        ExchangeCredentials("indodax", "test-key", "test-secret")
    )

    @Test
    fun parsesAvailableAndLockedIdrFromV2AccountResponse() {
        val rows = JSONArray(
            """[
                {"asset":"IDR","free":"125000.50","locked":"5000"},
                {"asset":"BTC","free":"0.001","locked":"0.0002"}
            ]"""
        )

        val snapshot = client.parseAccountSnapshot(rows, 123L)

        assertEquals(125000.50, snapshot.idrAvailable, 0.000001)
        assertEquals(5000.0, snapshot.idrHold, 0.000001)
        assertEquals(0.001, snapshot.balances["btc"]!!, 0.0000001)
        assertEquals(123L, snapshot.serverTimeMs)
    }

    @Test
    fun missingIdrBalanceFailsClosed() {
        val rows = JSONArray("""[{"asset":"BTC","free":"0.001","locked":"0"}]""")
        assertThrows(IllegalStateException::class.java) {
            client.parseAccountSnapshot(rows, 123L)
        }
    }

    @Test
    fun malformedOrNegativeBalanceFailsClosed() {
        val malformed = JSONArray("""[{"asset":"IDR","free":"NaN","locked":"0"}]""")
        assertThrows(IllegalStateException::class.java) {
            client.parseAccountSnapshot(malformed, 123L)
        }

        val negative = JSONArray("""[{"asset":"IDR","free":"-1","locked":"0"}]""")
        assertThrows(IllegalStateException::class.java) {
            client.parseAccountSnapshot(negative, 123L)
        }
    }

    @Test
    fun duplicateAssetsFailClosed() {
        val rows = JSONArray(
            """[
                {"asset":"IDR","free":"10","locked":"0"},
                {"asset":"idr","free":"20","locked":"0"}
            ]"""
        )
        assertThrows(IllegalStateException::class.java) {
            client.parseAccountSnapshot(rows, 123L)
        }
    }
}
