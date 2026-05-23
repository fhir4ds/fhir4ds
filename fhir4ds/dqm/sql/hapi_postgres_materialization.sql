-- FHIR4DS HAPI PostgreSQL materialization support.
--
-- The queue table is the durable contract. LISTEN/NOTIFY is only a wake-up
-- signal for online workers.

CREATE TABLE IF NOT EXISTS fhir4ds_patient_change_queue (
    patient_id TEXT PRIMARY KEY,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'complete', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    processing_started_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    last_error TEXT,
    last_resource_type TEXT,
    last_resource_id TEXT,
    notify_count INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS fhir4ds_patient_change_queue_status_idx
ON fhir4ds_patient_change_queue(status, last_seen_at);

CREATE TABLE IF NOT EXISTS fhir4ds_measure_config (
    measure_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT true,
    measure_version TEXT,
    measure_path TEXT NOT NULL,
    cql_path TEXT,
    library_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    valueset_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    audit_mode TEXT NOT NULL DEFAULT 'none',
    persist_audit BOOLEAN NOT NULL DEFAULT false,
    generate_narratives BOOLEAN NOT NULL DEFAULT false,
    include_supporting_evidence BOOLEAN NOT NULL DEFAULT false,
    filter_to_ip BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fhir4ds_measure_run (
    run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'ok', 'partial', 'error')),
    trigger_reason TEXT,
    patient_count INTEGER NOT NULL DEFAULT 0,
    measure_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS fhir4ds_measure_result (
    result_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES fhir4ds_measure_run(run_id),
    patient_id TEXT NOT NULL,
    measure_id TEXT NOT NULL,
    measure_version TEXT,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT true,
    status TEXT NOT NULL
        CHECK (status IN ('ok', 'no_result', 'error')),
    result_json JSONB,
    summary_json JSONB,
    input_watermark TIMESTAMPTZ,
    config_hash TEXT,
    error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS fhir4ds_measure_result_active_idx
ON fhir4ds_measure_result(patient_id, measure_id)
WHERE active;

CREATE INDEX IF NOT EXISTS fhir4ds_measure_result_lookup_idx
ON fhir4ds_measure_result(patient_id, measure_id, calculated_at DESC);

CREATE TABLE IF NOT EXISTS fhir4ds_measure_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES fhir4ds_measure_result(result_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_json JSONB,
    artifact_uri TEXT,
    size_bytes BIGINT,
    compression TEXT
);

CREATE OR REPLACE FUNCTION fhir4ds_extract_patient_id(
    p_resource_type TEXT,
    p_fhir_id TEXT,
    p_resource JSONB
) RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    ref TEXT;
BEGIN
    IF p_resource_type = 'Patient' THEN
        RETURN p_fhir_id;
    END IF;

    ref := COALESCE(
        p_resource #>> '{subject,reference}',
        p_resource #>> '{patient,reference}',
        p_resource #>> '{beneficiary,reference}'
    );

    IF ref IS NULL THEN
        RETURN NULL;
    END IF;

    IF ref ~ '^Patient/[^/]+$' THEN
        RETURN substring(ref from '^Patient/(.+)$');
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fhir4ds_enqueue_patient_change(
    p_patient_id TEXT,
    p_resource_type TEXT,
    p_resource_id TEXT
) RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_patient_id IS NULL OR p_patient_id = '' THEN
        RETURN;
    END IF;

    INSERT INTO fhir4ds_patient_change_queue (
        patient_id,
        first_seen_at,
        last_seen_at,
        status,
        attempts,
        processed_at,
        last_error,
        last_resource_type,
        last_resource_id,
        notify_count
    )
    VALUES (
        p_patient_id,
        now(),
        now(),
        'pending',
        0,
        NULL,
        NULL,
        p_resource_type,
        p_resource_id,
        1
    )
    ON CONFLICT (patient_id)
    DO UPDATE SET
        last_seen_at = now(),
        status = 'pending',
        processed_at = NULL,
        last_error = NULL,
        last_resource_type = EXCLUDED.last_resource_type,
        last_resource_id = EXCLUDED.last_resource_id,
        notify_count = fhir4ds_patient_change_queue.notify_count + 1;

    PERFORM pg_notify(
        'fhir4ds_patient_changed',
        json_build_object('patient_id', p_patient_id)::TEXT
    );
END;
$$;

CREATE OR REPLACE FUNCTION fhir4ds_queue_hapi_resource_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    r RECORD;
    v RECORD;
    body JSONB;
    patient_id TEXT;
BEGIN
    IF TG_TABLE_NAME = 'hfj_resource' THEN
        SELECT *
        INTO r
        FROM hfj_resource
        WHERE res_id = NEW.res_id;
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        SELECT *
        INTO v
        FROM hfj_res_ver
        WHERE res_id = NEW.res_id
          AND res_ver = NEW.res_ver;
        IF NOT FOUND THEN
            IF r.res_type = 'Patient' THEN
                PERFORM fhir4ds_enqueue_patient_change(r.fhir_id, r.res_type, r.fhir_id);
            END IF;
            RETURN NEW;
        END IF;
    ELSE
        SELECT *
        INTO v
        FROM hfj_res_ver
        WHERE pid = NEW.pid;
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        SELECT *
        INTO r
        FROM hfj_resource
        WHERE res_id = NEW.res_id;
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        IF r.res_ver IS DISTINCT FROM NEW.res_ver THEN
            RETURN NEW;
        END IF;
    END IF;

    IF r.res_type = 'Patient' THEN
        patient_id := r.fhir_id;
    ELSIF v.res_encoding = 'JSON' AND v.res_text_vc IS NOT NULL THEN
        body := v.res_text_vc::JSONB;
        patient_id := fhir4ds_extract_patient_id(r.res_type, r.fhir_id, body);
    ELSE
        patient_id := NULL;
    END IF;

    PERFORM fhir4ds_enqueue_patient_change(patient_id, r.res_type, r.fhir_id);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS fhir4ds_hfj_resource_change ON hfj_resource;
CREATE TRIGGER fhir4ds_hfj_resource_change
AFTER INSERT OR UPDATE ON hfj_resource
FOR EACH ROW
EXECUTE FUNCTION fhir4ds_queue_hapi_resource_change();

DROP TRIGGER IF EXISTS fhir4ds_hfj_res_ver_change ON hfj_res_ver;
CREATE TRIGGER fhir4ds_hfj_res_ver_change
AFTER INSERT OR UPDATE ON hfj_res_ver
FOR EACH ROW
EXECUTE FUNCTION fhir4ds_queue_hapi_resource_change();
