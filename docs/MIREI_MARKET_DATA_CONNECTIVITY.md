# Mirei market-data connectivity boundary

Indodax paper trading currently consumes real public market data through REST polling. This is sufficient for the planned 6-hour paper validation and must not be described as a WebSocket connection.

The live execution adapter remains a stub that rejects live order operations. A future WebSocket market-data adapter can be added behind the existing exchange/data boundary without enabling live order execution.

The intended separation is:

- public market data: REST now, WebSocket later where useful;
- paper execution: Android paper execution engine;
- live order execution: disabled until the paper validation is complete and a separate approval/configuration boundary is implemented.
