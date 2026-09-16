package com.mirei.app.execution

/**
 * Live boundary only. It deliberately refuses all live operations during the
 * 6-hour paper validation milestone. Credentials remain owned by SecureCredentialStore.
 */
class LiveExchangeAdapterStub(override val exchangeId: String) : ExchangeAdapter {
    override suspend fun fetchPrice(symbol: String): Double = throw IllegalStateException("live_exchange_disabled")
    override suspend fun placeMarketBuy(symbol: String, quoteAmount: Double): ExecutionResult = ExecutionResult(false, error = "live_exchange_disabled")
    override suspend fun placeLimitBuy(symbol: String, quoteAmount: Double, limitPrice: Double): ExecutionResult = ExecutionResult(false, error = "live_exchange_disabled")
    override suspend fun closePosition(positionId: String, reason: String): ExecutionResult = ExecutionResult(false, reason = reason, error = "live_exchange_disabled")
}
