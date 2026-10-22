-- AI-003: bounded model availability counters.
-- Re-runnable. Apply after 087 (88 and 89 belong to sibling branches). Inert until the backend
-- flushes counters (AI_AVAILABILITY_ENABLED, default on); nothing else reads or writes it.
--
-- One row per hour, workload, model, outcome and route (primary or fallback) holds counts and a
-- fixed latency histogram. No patient identifier, no prompt, no response text, no exception text:
-- only the registry workload, the configured model id, a closed outcome vocabulary and numbers.
-- Cardinality is bounded three ways: CHECKed value shapes, a closed outcome set, and a cap of
-- 400 distinct keys per hour inside the write function (a new key past it is dropped, counted in
-- the 'overflow' row). Rows older than 14 days are deleted by the same function, a few at a time.
--
-- Counts are approximate by design: a flush whose acknowledgement is lost may be applied twice.
-- Rollback: stop the flag; drop the table and functions (nothing depends on them).

CREATE TABLE IF NOT EXISTS public.ai_availability_buckets (
 bucket_start timestamptz NOT NULL,
 workload text NOT NULL CHECK(workload ~ '^[a-z0-9_]{1,40}$'),
 model text NOT NULL CHECK(char_length(model) BETWEEN 1 AND 80 AND model ~ '^[A-Za-z0-9._/:-]+$'),
 outcome text NOT NULL CHECK(outcome IN ('success','timeout','rate_limited','server_error','client_error','circuit_open','cancelled','other','overflow')),
 fallback boolean NOT NULL DEFAULT false,
 attempts bigint NOT NULL DEFAULT 0 CHECK(attempts>=0),
 latency_sum_ms bigint NOT NULL DEFAULT 0 CHECK(latency_sum_ms>=0),
 latency_bins integer[] NOT NULL DEFAULT ARRAY[0,0,0,0,0,0,0,0,0,0] CHECK(array_length(latency_bins,1)=10),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(bucket_start,workload,model,outcome,fallback)
);
ALTER TABLE public.ai_availability_buckets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ai_availability_buckets FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.ai_availability_buckets TO service_role;

-- SECURITY DEFINER with a fixed empty search_path and EXECUTE for service_role only: the backend
-- can add counts through this function and cannot otherwise write or delete rows.
-- p_rows: [{"workload","model","outcome","fallback","attempts","latency_sum_ms","bins":[10 ints]}]
-- at most 200 rows per call; the hour is the database clock's, never the caller's.
CREATE OR REPLACE FUNCTION public.record_ai_availability(p_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' SET lock_timeout='2s' SET statement_timeout='5s' AS $$
DECLARE
 hour_start timestamptz:=date_trunc('hour',clock_timestamp());
 r jsonb; applied int:=0; dropped bigint:=0; keys int; b int[]; k_workload text; k_model text; k_outcome text; k_fb boolean;
BEGIN
 IF p_rows IS NULL OR jsonb_typeof(p_rows)<>'array' OR jsonb_array_length(p_rows)>200 THEN
  RETURN jsonb_build_object('accepted',false,'reason','invalid_rows');
 END IF;
 FOR r IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
  k_workload:=r->>'workload'; k_model:=r->>'model'; k_outcome:=r->>'outcome'; k_fb:=coalesce((r->>'fallback')::boolean,false);
  IF k_workload IS NULL OR k_model IS NULL OR k_outcome IS NULL
     OR k_workload !~ '^[a-z0-9_]{1,40}$' OR k_model !~ '^[A-Za-z0-9._/:-]{1,80}$'
     OR k_outcome NOT IN ('success','timeout','rate_limited','server_error','client_error','circuit_open','cancelled','other') THEN
   dropped:=dropped+coalesce((r->>'attempts')::bigint,0); CONTINUE;
  END IF;
  SELECT array_agg(least(greatest(coalesce(v::int,0),0),1000000)) INTO b FROM jsonb_array_elements_text(coalesce(r->'bins','[]'::jsonb)) AS t(v);
  IF b IS NULL OR array_length(b,1)<>10 THEN b:=ARRAY[0,0,0,0,0,0,0,0,0,0]; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.ai_availability_buckets WHERE bucket_start=hour_start AND workload=k_workload AND model=k_model AND outcome=k_outcome AND fallback=k_fb) THEN
   SELECT count(*) INTO keys FROM public.ai_availability_buckets WHERE bucket_start=hour_start;
   IF keys>=400 THEN dropped:=dropped+least(greatest(coalesce((r->>'attempts')::bigint,0),0),1000000); CONTINUE; END IF;
  END IF;
  INSERT INTO public.ai_availability_buckets AS a(bucket_start,workload,model,outcome,fallback,attempts,latency_sum_ms,latency_bins)
  VALUES(hour_start,k_workload,k_model,k_outcome,k_fb,
         least(greatest(coalesce((r->>'attempts')::bigint,0),0),1000000),
         least(greatest(coalesce((r->>'latency_sum_ms')::bigint,0),0),100000000000),b)
  ON CONFLICT(bucket_start,workload,model,outcome,fallback) DO UPDATE SET
   attempts=a.attempts+EXCLUDED.attempts,
   latency_sum_ms=a.latency_sum_ms+EXCLUDED.latency_sum_ms,
   latency_bins=ARRAY(SELECT x+y FROM unnest(a.latency_bins,EXCLUDED.latency_bins) AS u(x,y)),
   updated_at=clock_timestamp();
  applied:=applied+1;
 END LOOP;
 IF dropped>0 THEN
  INSERT INTO public.ai_availability_buckets AS a(bucket_start,workload,model,outcome,fallback,attempts)
  VALUES(hour_start,'overflow','overflow','overflow',false,dropped)
  ON CONFLICT(bucket_start,workload,model,outcome,fallback) DO UPDATE SET attempts=a.attempts+EXCLUDED.attempts,updated_at=clock_timestamp();
 END IF;
 -- Retention: a bounded batch per call; the table never grows past about 14 days of buckets.
 DELETE FROM public.ai_availability_buckets WHERE ctid IN (
  SELECT ctid FROM public.ai_availability_buckets WHERE bucket_start<hour_start-interval '14 days' LIMIT 200);
 RETURN jsonb_build_object('accepted',true,'applied',applied,'dropped',dropped);
END;
$$;
REVOKE ALL ON FUNCTION public.record_ai_availability(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_ai_availability(jsonb) TO service_role;

DO $$
BEGIN
 IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.ai_availability_buckets'::regclass) THEN
  RAISE EXCEPTION 'ai_availability_buckets must have row level security';
 END IF;
 IF has_table_privilege('anon','public.ai_availability_buckets','SELECT') OR has_table_privilege('authenticated','public.ai_availability_buckets','SELECT')
    OR has_table_privilege('service_role','public.ai_availability_buckets','INSERT') THEN
  RAISE EXCEPTION 'ai_availability_buckets grants are wider than intended';
 END IF;
 IF has_function_privilege('anon','public.record_ai_availability(jsonb)','EXECUTE') OR has_function_privilege('authenticated','public.record_ai_availability(jsonb)','EXECUTE')
    OR NOT has_function_privilege('service_role','public.record_ai_availability(jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'record_ai_availability execute grants are wrong';
 END IF;
END $$;
