-- Keep the production paper-history reader compatible with the canonical pair-based ledger.
-- The Cloudflare history reader still requests legacy compatibility fields, so expose
-- deterministic aliases without changing pair as the canonical identifier.
ALTER TABLE public.paper_history
  ADD COLUMN IF NOT EXISTS symbol text GENERATED ALWAYS AS (pair) STORED,
  ADD COLUMN IF NOT EXISTS pnl numeric GENERATED ALWAYS AS (realized_pnl) STORED,
  ADD COLUMN IF NOT EXISTS risk_exit_reason text GENERATED ALWAYS AS ((execution_result->'trade'->>'exit_reason')) STORED,
  ADD COLUMN IF NOT EXISTS exit_reason text GENERATED ALWAYS AS ((execution_result->'trade'->>'exit_reason')) STORED;

-- The shared trigger is installed on both decisions and paper_history. Do not
-- reference a field that belongs only to the other table when repairing a cycle.
CREATE OR REPLACE FUNCTION public.normalize_paper_cycle_number()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  existing_max bigint;
  linked_cycle bigint;
  requested_cycle bigint;
  event_symbol text;
BEGIN
  IF NEW.cycle_id IS NOT NULL AND TG_TABLE_NAME = 'paper_history' THEN
    SELECT d.cycle_number
      INTO linked_cycle
      FROM public.decisions d
     WHERE d.cycle_id = NEW.cycle_id
     ORDER BY d.id DESC
     LIMIT 1;

    IF linked_cycle IS NOT NULL THEN
      NEW.cycle_number := linked_cycle;
      RETURN NEW;
    END IF;
  END IF;

  IF NEW.session_id IS NOT NULL AND NEW.cycle_number IS NOT NULL THEN
    requested_cycle := NEW.cycle_number;

    SELECT max(cycle_number)
      INTO existing_max
      FROM public.decisions d
     WHERE d.session_id = NEW.session_id
       AND d.cycle_number IS NOT NULL;

    SELECT greatest(existing_max, max(ph.cycle_number))
      INTO existing_max
      FROM public.paper_history ph
     WHERE ph.session_id = NEW.session_id
       AND ph.cycle_number IS NOT NULL;

    IF existing_max IS NOT NULL AND requested_cycle <= existing_max THEN
      NEW.cycle_number := existing_max + 1;

      IF TG_TABLE_NAME = 'paper_history' THEN
        event_symbol := NEW.pair;
      ELSE
        event_symbol := NEW.symbol;
      END IF;

      INSERT INTO public.paper_integrity_events(
        severity, event_type, cycle_id, session_id, symbol, details
      )
      VALUES (
        'WARN',
        'DUPLICATE_CYCLE_NUMBER_REPAIRED',
        NEW.cycle_id,
        NEW.session_id,
        event_symbol,
        jsonb_build_object(
          'requested', requested_cycle,
          'assigned', NEW.cycle_number,
          'previous_max', existing_max
        )
      );
    END IF;
  END IF;

  RETURN NEW;
END;
$$;
