-- Ensure PostgREST refreshes its function schema cache after the market observation RPC exists.
-- The RPC is the canonical persistence boundary used by the paper cycle.
notify pgrst, 'reload schema';
