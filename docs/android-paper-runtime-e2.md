# Android Paper Runtime E2

This milestone validates the paper runtime pipeline at the domain/runtime layer:

- real market-data adapter feeds `MireiPaperTradingRuntime`
- four baseline agents evaluate each fresh snapshot
- orchestrator resolves the agent decision
- decision engine applies risk and entry gates
- paper execution opens positions without live orders
- TP/SL closes positions
- realized PnL becomes available capital
- a new entry may reuse released capital
- the configured maximum of three active positions is preserved
- conflicting agent decisions remain blocked in Suggestion mode

Physical Android validation remains separate from these deterministic runtime tests.
