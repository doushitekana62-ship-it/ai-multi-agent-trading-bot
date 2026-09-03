-- Keep the canonical paper-history writer resilient to older workers while
-- retaining the audit columns as non-null fields.
alter table public.paper_history
  alter column execution_gate set default '{}'::jsonb,
  alter column market_snapshot set default '{}'::jsonb,
  alter column persistence_status set default 'PENDING',
  alter column library_alerts set default '[]'::jsonb,
  alter column candle_analysis set default '{}'::jsonb,
  alter column knowledge_topics set default '[]'::jsonb;
