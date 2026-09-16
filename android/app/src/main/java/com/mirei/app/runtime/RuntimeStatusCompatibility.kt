package com.mirei.app.runtime

import com.mirei.app.agents.AgentAction
import com.mirei.app.execution.PaperPosition

// Compatibility aliases keep the foreground-service status contract stable while
// PaperRuntimeStatus uses explicit market-prefixed field names.
private val PaperRuntimeStatus.latestDecisionAction: AgentAction
    get() = lastDecision?.action ?: AgentAction.HOLD

val PaperRuntimeStatus.bidPrice: Double get() = marketBidPrice
val PaperRuntimeStatus.askPrice: Double get() = marketAskPrice
val PaperRuntimeStatus.high24h: Double get() = marketHigh24h
val PaperRuntimeStatus.low24h: Double get() = marketLow24h
val PaperRuntimeStatus.volume24h: Double get() = marketVolume24h
val PaperRuntimeStatus.decisionConfidence: Double get() = lastDecision?.confidence ?: 0.0
val PaperRuntimeStatus.decisionAction: AgentAction get() = latestDecisionAction
val PaperRuntimeStatus.decisionRationale: String get() = lastDecision?.rationale ?: ""
val PaperRuntimeStatus.agentSummary: String get() = lastDecision?.observations?.joinToString(" | ") { "${it.agent.name}:${it.action.name}" } ?: ""
val PaperRuntimeStatus.entryReasons: List<String> get() = entryPlanReasons
val PaperRuntimeStatus.momentumPercent: Double get() = marketMomentumPercent
val PaperRuntimeStatus.volatilityPercent: Double get() = marketVolatilityPercent
val PaperRuntimeStatus.sentimentScore: Double get() = marketSentimentScore
val PaperRuntimeStatus.spreadPercent: Double get() = marketSpreadPercent
val PaperRuntimeStatus.changeTickPercent: Double get() = changeSinceLastTickPercent
val PaperRuntimeStatus.flowScore: Double get() = tradeFlowPercent
val PaperRuntimeStatus.marketFresh: Boolean get() = marketDataFresh

// PaperPosition deliberately has no continuously marked price field. These aliases
// preserve the existing UI payload shape without inventing a market price.
val PaperPosition.quantity: Double get() = if (entryPrice > 0.0) stakeIdr / entryPrice else 0.0
val PaperPosition.currentPrice: Double get() = entryPrice
val PaperPosition.unrealizedPnlIdr: Double get() = 0.0
