# AI Multi-Agent Trading Bot — Architecture Contract

> **Purpose:** This document is the architectural source of truth for the project. It exists to prevent feature drift, duplicated responsibilities, unsafe trading logic, and uncontrolled changes to the system boundary.
>
> **Rule:** If a proposed change conflicts with this document, update the architecture first. Do not silently change the architecture through implementation.

## 1. Project Mission

The project is a **multi-agent AI-assisted trading system** that produces market analysis, forecasts, sentiment/context signals, trading decisions, risk-controlled execution instructions, and operational reporting.

The system must prioritize:

1. capital protection and explicit risk controls;
2. deterministic and auditable trading behavior;
3. separation between AI analysis and order execution;
4. paper trading before live trading;
5. modular agents with clearly bounded responsibilities;
6. reproducibility, observability, and testability.

The project is **not** intended to become a generic AI platform, unrestricted autonomous agent framework, social application, or collection of unrelated trading experiments.

## 2. Architectural Principles

### 2.1 AI advises; the trading core controls

LLM/AI agents may analyze, forecast, classify, rank, explain, and recommend. They must not bypass the deterministic risk and execution layer.

No AI agent may directly place an exchange order unless the request passes the central risk/execution pipeline.

### 2.2 One responsibility per agent

Each agent owns one analytical domain. Agents must not duplicate another agent's responsibility merely because additional logic is convenient.

### 2.3 Risk is a hard boundary

Risk controls are mandatory and cannot be overridden by an AI-generated recommendation.

At minimum, the system must respect configured limits such as:

- maximum position size;
- daily loss limit;
- maximum open positions;
- paper/live trading mode;
- exchange/account constraints.

### 2.4 Paper trading is the default development path

New trading behavior must be validated in paper/simulation mode before any live execution capability is enabled.

### 2.5 Exchange integration is an adapter

Exchange-specific code belongs behind an integration boundary. Strategy and agent code must not depend directly on exchange-specific SDK details.

### 2.6 No hidden state

Important decisions, signals, risk checks, orders, fills, and errors must be observable and persistable. Avoid business-critical state that exists only inside an AI prompt or process memory.

## 3. High-Level System

```text
                        MARKET / EXTERNAL DATA
                                 |
             +-------------------+-------------------+
             |                   |                   |
        Price/Market        News/Sentiment       Exchange Data
             |                   |                   |
             +-------------------+-------------------+
                                 |
                                 v
                       +-------------------+
                       |   DATA / CONTEXT   |
                       | normalization      |
                       | validation         |
                       | feature/context    |
                       +---------+---------+
                                 |
                                 v
              +---------------------------------------+
              |             AI AGENT LAYER            |
              |                                       |
              | Technical | Forecast | Sentiment      |
              | Decision  | Reflection | Librarian    |
              +-------------------+-------------------+
                                  |
                                  v
                       +-------------------+
                       | DECISION / SIGNAL  |
                       | aggregation        |
                       | confidence         |
                       | rationale          |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       |   RISK GATE         |
                       | position limits     |
                       | loss limits         |
                       | exposure checks     |
                       | mode checks         |
                       +---------+---------+
                                 |
                          approved only
                                 |
                                 v
                       +-------------------+
                       | EXECUTION SERVICE  |
                       | paper/live adapter  |
                       | order lifecycle    |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       | EXCHANGE ADAPTER   |
                       +-------------------+
                                 |
                                 v
                            MARKET ACCOUNT

        API / Dashboard / Reports / Monitoring
                    <---- read/control ---->
                         Backend service
```

## 4. Repository Boundaries

The current repository already separates major responsibilities into `agents`, `backend`, `core`, `data`, and `exchange_integration`. Preserve these boundaries rather than moving business logic into arbitrary files.

### `agents/`

AI/analytical agents only.

Current conceptual roles:

- `agent_technical.py` — technical market analysis;
- `agent_forecast.py` — forecasting/probabilistic market outlook;
- `agent_sentiment.py` — sentiment and external-context analysis;
- `agent_decision.py` — decision synthesis from available signals;
- `agent_reflector.py` — post-decision/self-review and consistency checks;
- `agent_trading_librarian.py` — trading knowledge/context retrieval and organization.

Agents should return structured outputs. They should not own database persistence, exchange credentials, HTTP routing, or direct order execution.

### `backend/`

Application/API boundary.

Responsibilities:

- HTTP API;
- authentication and authorization;
- dashboard-facing endpoints;
- orchestration of application operations;
- persistence access through defined services/modules;
- paper-trading controls;
- reports and operational status.

The backend is the application boundary, not the place for uncontrolled strategy experimentation.

### `core/`

Domain-level shared logic.

Responsibilities should remain reusable and independent from HTTP/UI concerns where practical.

Examples include:

- trading/domain models;
- risk rules;
- configuration;
- decision schemas;
- portfolio/order abstractions;
- deterministic validation.

If a rule is fundamental to trading correctness, prefer placing it here rather than inside a route or AI prompt.

### `exchange_integration/`

Exchange adapters and exchange-specific functionality.

Responsibilities:

- authentication to exchanges;
- market data adapters;
- account/balance queries;
- order submission/cancellation;
- exchange-specific symbol and precision handling;
- normalization into project-level models.

Do not leak exchange-specific response formats into agents or frontend code.

### `data/`

Local/runtime data only.

This directory must not become an uncontrolled source-code or business-logic dumping ground. Secrets and production credentials must never be committed here.

### `frontend/`

Dashboard/UI only.

The frontend consumes backend APIs. It must not implement authoritative risk rules, exchange credentials, or autonomous trading logic.

## 5. Agent Contract

Every agent should conceptually follow this contract:

```text
Input context
    -> validate required inputs
    -> perform domain-specific analysis
    -> produce structured result
    -> expose confidence/uncertainty
    -> expose timestamp/data freshness
    -> return to orchestrator
```

A useful agent result should contain, where applicable:

- symbol/market;
- timeframe;
- signal or assessment;
- confidence;
- supporting evidence;
- uncertainty/limitations;
- timestamp;
- data freshness;
- model/prompt/version metadata.

Free-form prose may be included for explanation, but prose must not be the sole machine-readable representation of a trading decision.

## 6. Decision Pipeline

The canonical trading flow is:

```text
Collect data
  -> validate/normalize
  -> run analytical agents
  -> aggregate agent outputs
  -> generate candidate decision
  -> deterministic risk validation
  -> execution eligibility check
  -> paper/live execution adapter
  -> record order/fill/result
  -> reflect/evaluate
  -> report/monitor
```

No new execution path should be introduced without documenting it here.

## 7. Risk Boundary

Risk management is a deterministic control plane.

The risk layer must be able to reject a candidate trade even when every AI agent recommends it.

Required conceptual checks include:

```text
candidate order
      |
      +-- trading mode allowed?
      +-- symbol allowed?
      +-- position size <= limit?
      +-- portfolio exposure <= limit?
      +-- daily loss <= limit?
      +-- open positions < limit?
      +-- sufficient balance?
      +-- exchange constraints satisfied?
      |
   ALL PASS
      |
   execution
```

Risk configuration currently includes values such as `MAX_POSITION_SIZE`, `DAILY_LOSS_LIMIT`, and `MAX_OPEN_POSITIONS`. These are guardrails, not suggestions.

## 8. Execution Safety

The system must maintain a strict distinction between:

- analysis;
- decision proposal;
- risk approval;
- order execution;
- order/fill reconciliation.

An AI response must never be treated as proof that an order was executed.

Execution should return an explicit status and an exchange/order identifier where available. Failures, partial fills, cancellations, and rejected orders must be represented explicitly.

## 9. Paper vs Live Mode

The system must make the operating mode explicit.

Recommended states:

```text
DEVELOPMENT
    -> PAPER
        -> LIVE (only after explicit operational approval)
```

A live exchange key must not implicitly switch the application into live trading.

Paper trading must remain usable without live credentials.

## 10. API Boundary

FastAPI/backend routes expose application capabilities to the dashboard and external callers.

Routes should call application/domain services rather than embedding large blocks of trading logic.

Conceptual boundary:

```text
Frontend / API Client
        |
        v
     Routes
        |
        v
 Application Services / Orchestrator
        |
        +---- Agents
        +---- Core / Risk
        +---- Data
        +---- Exchange adapters
        |
        v
 Database / External Services
```

Authentication/security code belongs at the API/security boundary. Exchange credentials must remain isolated and protected.

## 11. Persistence

PostgreSQL is the primary service database in the current containerized architecture, with Redis available for caching/runtime coordination. The repository also supports a SQLite configuration example for local development.

Persist business-critical records such as:

- market/context snapshots where required for reproducibility;
- agent outputs when needed for audit/debugging;
- candidate decisions;
- risk checks/results;
- orders;
- fills;
- positions/balances where applicable;
- trading sessions;
- errors and operational events.

Caching must not become the authoritative source of trading history.

## 12. External AI Engine

The repository includes configuration for an external FastAPI AI engine through `AI_ENGINE_URL` and a shared secret.

Treat this as an optional service boundary, not a second independent trading brain.

The external engine may perform AI computation, but the authoritative application must still enforce:

```text
AI output -> validation -> risk gate -> execution
```

The external AI engine must not create a parallel order-execution path.

## 13. Deployment Architecture

The current containerized deployment concept contains:

- backend API;
- frontend;
- PostgreSQL;
- Redis;
- Nginx/reverse proxy.

These components are already represented in `docker-compose.yml`. Deployment work should improve reliability of this architecture rather than introduce unnecessary infrastructure.

Cloudflare/VPS/deployment automation is an infrastructure concern. It must not alter trading-domain semantics.

## 14. Observability

Every production-relevant trading operation should be traceable through logs and persisted records.

At minimum, capture:

- operation/session identifier;
- symbol;
- mode (paper/live);
- decision timestamp;
- agent outputs or references;
- risk result;
- execution result;
- error details;
- latency where useful.

Never log raw secrets, API keys, private credentials, or authentication tokens.

## 15. Testing Strategy

Testing should follow the same boundaries as the architecture.

### Unit tests

Test deterministic domain logic independently:

- risk calculations;
- position sizing;
- signal normalization;
- validation;
- order state transitions;
- exchange response normalization.

### Integration tests

Test boundaries:

- backend ↔ database;
- backend ↔ Redis where applicable;
- backend ↔ exchange adapter;
- agent orchestration;
- external AI engine contract.

### Paper-trading tests

Paper trading is the principal safety environment for end-to-end trading behavior.

### Live trading tests

Do not use real capital merely to test application logic. Use mocked/sandbox/paper exchange behavior wherever possible.

## 16. Change Control — Anti-Drift Rules

Before implementing a new feature, classify it into exactly one primary architectural area:

1. Agent/AI analysis
2. Data/context
3. Decision/orchestration
4. Risk/control
5. Execution/exchange
6. Backend/API
7. Frontend/dashboard
8. Persistence
9. Infrastructure/DevOps
10. Testing/observability

If it does not fit any category, stop and review the architecture before coding.

Every substantial change must answer:

- What problem does this solve?
- Which architectural boundary owns it?
- Which existing component should own the behavior?
- Does it create a second implementation of an existing responsibility?
- Does it create a new path to exchange execution?
- Does it weaken or bypass risk controls?
- Does it require a change to this document?

## 17. Explicit Non-Goals

Unless explicitly approved and documented, do not add:

- unrelated AI assistants;
- generic chatbot features;
- social/community features;
- arbitrary blockchain/Web3 functionality;
- unrelated SaaS functionality;
- duplicate exchange clients;
- duplicate risk engines;
- direct agent-to-exchange execution;
- production live trading as the default mode;
- large rewrites solely for stylistic reasons.

## 18. Definition of Done for Trading Features

A trading-related feature is not complete merely because its code runs.

It should satisfy the following:

- belongs to a defined architectural boundary;
- has a clear input/output contract;
- does not duplicate another component;
- respects paper/live mode;
- passes deterministic risk controls;
- is observable;
- has appropriate tests;
- does not expose secrets;
- can be explained and traced from input to final outcome.

## 19. Source-of-Truth Hierarchy

When documents or implementation disagree, use this order:

1. Explicit product/safety requirements approved by the project owner;
2. `ARCHITECTURE.md`;
3. domain/core contracts and schemas;
4. backend/application behavior;
5. agent implementations;
6. deployment/configuration details;
7. ad-hoc notes or temporary experiments.

If implementation contradicts the architecture, do not silently normalize the architecture to match the implementation. First determine whether the implementation or architecture is wrong.

## 20. Final Rule

**Do not add code because it is technically interesting. Add it only when it advances the trading system's defined mission and fits an existing architectural boundary.**

When in doubt: preserve the boundary, prefer the smallest change, keep execution deterministic, keep risk centralized, and document architectural changes before implementing them.
