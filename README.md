# Compound Scalping Integration

FastAPI application layer for the Compound Scalping project.

The trading engine is Freqtrade. This repository does not reimplement exchange connectivity, candle handling, order execution, trade persistence, or the strategy engine.

Architecture:

Cloudflare -> FastAPI -> Freqtrade -> Exchange
                     -> Supabase

Run locally with Docker Compose. Configure Freqtrade separately using the official Freqtrade repository/image and point `FREQTRADE_URL` at its REST API.
