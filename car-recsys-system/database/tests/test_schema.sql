-- Fails (raises) if expected columns / tables are missing.
DO $$
BEGIN
  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='crawl_date';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.crawl_date missing'; END IF;

  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='source';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.source missing'; END IF;

  PERFORM 1 FROM information_schema.columns
    WHERE table_schema='bronze' AND table_name='raw_listings' AND column_name='run_id';
  IF NOT FOUND THEN RAISE EXCEPTION 'bronze.raw_listings.run_id missing'; END IF;

  PERFORM 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='gold' AND c.relname='vehicle_price_history';
  IF NOT FOUND THEN RAISE EXCEPTION 'gold.vehicle_price_history not partitioned'; END IF;

  PERFORM 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='gold' AND p.proname='ensure_price_history_partition';
  IF NOT FOUND THEN RAISE EXCEPTION 'gold.ensure_price_history_partition missing'; END IF;

  RAISE NOTICE 'schema test passed';
END $$;
