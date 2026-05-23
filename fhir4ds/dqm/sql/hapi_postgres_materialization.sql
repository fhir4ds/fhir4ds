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
    measure_path TEXT,
    cql_path TEXT,
    artifact_source TEXT NOT NULL DEFAULT 'files'
        CHECK (artifact_source IN ('files', 'hapi')),
    artifact_ref TEXT,
    library_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    valueset_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    audit_mode TEXT NOT NULL DEFAULT 'none',
    persist_audit BOOLEAN NOT NULL DEFAULT false,
    persist_measure_report BOOLEAN NOT NULL DEFAULT false,
    publish_measure_report_to_hapi BOOLEAN NOT NULL DEFAULT false,
    generate_narratives BOOLEAN NOT NULL DEFAULT false,
    include_supporting_evidence BOOLEAN NOT NULL DEFAULT false,
    filter_to_ip BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE fhir4ds_measure_config
    ADD COLUMN IF NOT EXISTS persist_measure_report BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS publish_measure_report_to_hapi BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS artifact_source TEXT NOT NULL DEFAULT 'files',
    ADD COLUMN IF NOT EXISTS artifact_ref TEXT;

ALTER TABLE fhir4ds_measure_config
    ALTER COLUMN measure_path DROP NOT NULL;

CREATE TABLE IF NOT EXISTS fhir4ds_measure_run (
    run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'ok', 'partial', 'error')),
    trigger_reason TEXT,
    patient_count INTEGER NOT NULL DEFAULT 0,
    measure_count INTEGER NOT NULL DEFAULT 0,
    compile_cache_hits INTEGER NOT NULL DEFAULT 0,
    compile_cache_misses INTEGER NOT NULL DEFAULT 0,
    compile_count INTEGER NOT NULL DEFAULT 0,
    compile_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    execute_count INTEGER NOT NULL DEFAULT 0,
    execute_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    prepared_count INTEGER NOT NULL DEFAULT 0,
    prepared_fallback_count INTEGER NOT NULL DEFAULT 0,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT
);

ALTER TABLE fhir4ds_measure_run
    ADD COLUMN IF NOT EXISTS compile_cache_hits INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS compile_cache_misses INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS compile_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS compile_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS execute_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS execute_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS prepared_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS prepared_fallback_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS fhir4ds_measure_run_started_idx
ON fhir4ds_measure_run(started_at DESC);

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
    measure_report_json JSONB,
    input_watermark TIMESTAMPTZ,
    config_hash TEXT,
    error TEXT
);

ALTER TABLE fhir4ds_measure_result
    ADD COLUMN IF NOT EXISTS measure_report_json JSONB;

CREATE TABLE IF NOT EXISTS fhir4ds_measure_report (
    measure_report_row_id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES fhir4ds_measure_result(result_id) ON DELETE CASCADE,
    run_id BIGINT REFERENCES fhir4ds_measure_run(run_id),
    patient_id TEXT NOT NULL,
    measure_id TEXT NOT NULL,
    measure_version TEXT,
    measure_report_id TEXT NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT true,
    resource_json JSONB NOT NULL,
    published_to_hapi BOOLEAN NOT NULL DEFAULT false,
    config_hash TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS fhir4ds_measure_result_active_idx
ON fhir4ds_measure_result(patient_id, measure_id)
WHERE active;

CREATE INDEX IF NOT EXISTS fhir4ds_measure_result_lookup_idx
ON fhir4ds_measure_result(patient_id, measure_id, calculated_at DESC);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_result_run_idx
ON fhir4ds_measure_result(run_id);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_result_inactive_calculated_idx
ON fhir4ds_measure_result(calculated_at)
WHERE active = false;

CREATE UNIQUE INDEX IF NOT EXISTS fhir4ds_measure_report_active_idx
ON fhir4ds_measure_report(patient_id, measure_id)
WHERE active;

CREATE INDEX IF NOT EXISTS fhir4ds_measure_report_lookup_idx
ON fhir4ds_measure_report(patient_id, measure_id, calculated_at DESC);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_report_result_idx
ON fhir4ds_measure_report(result_id);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_report_run_idx
ON fhir4ds_measure_report(run_id);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_report_fhir_id_idx
ON fhir4ds_measure_report(measure_report_id);

CREATE TABLE IF NOT EXISTS fhir4ds_measure_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL REFERENCES fhir4ds_measure_result(result_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_json JSONB,
    artifact_uri TEXT,
    size_bytes BIGINT,
    compression TEXT
);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_audit_result_idx
ON fhir4ds_measure_audit(result_id);

CREATE INDEX IF NOT EXISTS fhir4ds_measure_audit_created_idx
ON fhir4ds_measure_audit(created_at);

CREATE OR REPLACE FUNCTION fhir4ds_hapi_resource_json(
    p_encoding TEXT,
    p_text_vc TEXT,
    p_text_oid OID
) RETURNS JSONB
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_encoding IS DISTINCT FROM 'JSON' THEN
        RETURN NULL;
    END IF;

    IF p_text_vc IS NOT NULL THEN
        RETURN p_text_vc::JSONB;
    END IF;

    IF p_text_oid IS NOT NULL THEN
        RETURN convert_from(lo_get(p_text_oid), 'UTF8')::JSONB;
    END IF;

    RETURN NULL;
END;
$$;

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

CREATE OR REPLACE FUNCTION fhir4ds_is_generated_measure_report(
    p_resource JSONB
) RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(p_resource->>'resourceType', '') = 'MeasureReport'
       AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(p_resource #> '{meta,tag}') = 'array'
                        THEN p_resource #> '{meta,tag}'
                    ELSE '[]'::jsonb
                END
            ) AS tag
            WHERE tag->>'system' = 'https://fhir4ds.com/materialization'
              AND tag->>'code' = 'measure-report'
       );
$$;

CREATE OR REPLACE VIEW {{DECODED_VIEW_RELATION}} AS
SELECT
    {{FHIR_ID_SELECT}}::TEXT AS id,
    {{RESOURCE_TYPE_SELECT}}::TEXT AS "resourceType",
    decoded.resource AS resource,
    fhir4ds_extract_patient_id(
        {{RESOURCE_TYPE_SELECT}}::TEXT,
        {{FHIR_ID_SELECT}}::TEXT,
        decoded.resource
    ) AS patient_ref,
    {{UPDATED_AT_SELECT}} AS updated_at
FROM {{RESOURCE_RELATION}} r
JOIN {{VERSION_RELATION}} v
  ON {{VERSION_FK_SELECT}} = {{RESOURCE_PK_SELECT}}
 AND {{VERSION_NUMBER_SELECT}} = {{CURRENT_VERSION_SELECT}}
CROSS JOIN LATERAL (
    SELECT fhir4ds_hapi_resource_json(
        {{ENCODING_SELECT}}::TEXT,
        {{TEXT_VC_SELECT}},
        {{TEXT_LOB_SELECT}}
    ) AS resource
) decoded
WHERE {{DELETED_AT_SELECT}} IS NULL
  AND decoded.resource IS NOT NULL;

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
        {{NOTIFICATION_CHANNEL_LITERAL}},
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
    IF TG_TABLE_NAME = {{RESOURCE_TABLE_NAME_LITERAL}} THEN
        SELECT *
        INTO r
        FROM {{RESOURCE_RELATION}}
        WHERE {{RESOURCE_PK_COLUMN}} = NEW.{{RESOURCE_PK_COLUMN}};
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        SELECT *
        INTO v
        FROM {{VERSION_RELATION}}
        WHERE {{VERSION_FK_COLUMN}} = NEW.{{RESOURCE_PK_COLUMN}}
          AND {{VERSION_NUMBER_COLUMN}} = NEW.{{CURRENT_VERSION_COLUMN}};
        IF NOT FOUND THEN
            IF r.{{RESOURCE_TYPE_COLUMN}} = 'Patient' THEN
                PERFORM fhir4ds_enqueue_patient_change(
                    r.{{FHIR_ID_COLUMN}},
                    r.{{RESOURCE_TYPE_COLUMN}},
                    r.{{FHIR_ID_COLUMN}}
                );
            END IF;
            RETURN NEW;
        END IF;
    ELSE
        SELECT *
        INTO v
        FROM {{VERSION_RELATION}}
        WHERE {{VERSION_FK_COLUMN}} = NEW.{{VERSION_FK_COLUMN}}
          AND {{VERSION_NUMBER_COLUMN}} = NEW.{{VERSION_NUMBER_COLUMN}};
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        SELECT *
        INTO r
        FROM {{RESOURCE_RELATION}}
        WHERE {{RESOURCE_PK_COLUMN}} = NEW.{{VERSION_FK_COLUMN}};
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;

        IF r.{{CURRENT_VERSION_COLUMN}} IS DISTINCT FROM NEW.{{VERSION_NUMBER_COLUMN}} THEN
            RETURN NEW;
        END IF;
    END IF;

    body := fhir4ds_hapi_resource_json(
        v.{{ENCODING_COLUMN}}::TEXT,
        v.{{TEXT_VC_COLUMN}},
        v.{{TEXT_LOB_COLUMN}}
    );

    IF r.{{RESOURCE_TYPE_COLUMN}} = 'MeasureReport'
       AND (
            r.{{FHIR_ID_COLUMN}} LIKE 'fhir4ds-%'
            OR (body IS NOT NULL AND fhir4ds_is_generated_measure_report(body))
       ) THEN
        RETURN NEW;
    END IF;

    IF r.{{RESOURCE_TYPE_COLUMN}} = 'Patient' THEN
        patient_id := r.{{FHIR_ID_COLUMN}};
    ELSIF body IS NOT NULL THEN
        patient_id := fhir4ds_extract_patient_id(
            r.{{RESOURCE_TYPE_COLUMN}},
            r.{{FHIR_ID_COLUMN}},
            body
        );
    ELSE
        patient_id := NULL;
    END IF;

    PERFORM fhir4ds_enqueue_patient_change(
        patient_id,
        r.{{RESOURCE_TYPE_COLUMN}},
        r.{{FHIR_ID_COLUMN}}
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS fhir4ds_hfj_resource_change ON {{RESOURCE_RELATION}};
CREATE TRIGGER fhir4ds_hfj_resource_change
AFTER INSERT OR UPDATE ON {{RESOURCE_RELATION}}
FOR EACH ROW
EXECUTE FUNCTION fhir4ds_queue_hapi_resource_change();

DROP TRIGGER IF EXISTS fhir4ds_hfj_res_ver_change ON {{VERSION_RELATION}};
CREATE TRIGGER fhir4ds_hfj_res_ver_change
AFTER INSERT OR UPDATE ON {{VERSION_RELATION}}
FOR EACH ROW
EXECUTE FUNCTION fhir4ds_queue_hapi_resource_change();
