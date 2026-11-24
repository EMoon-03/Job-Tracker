-- 001_init: applications, their timeline events, and a reporting view.

CREATE TABLE applications (
    id            uuid PRIMARY KEY,
    company       text NOT NULL CHECK (btrim(company) <> ''),
    role          text NOT NULL DEFAULT '',
    stage         text NOT NULL DEFAULT 'wishlist'
                  CHECK (stage IN ('wishlist', 'applied', 'assessment', 'interview',
                                   'offer', 'rejected', 'withdrawn', 'ghosted')),
    job_type      text NOT NULL DEFAULT '',   -- Internship, Full-time, ...
    sector        text NOT NULL DEFAULT '',   -- Finance, Consulting, Defense, ...
    location      text NOT NULL DEFAULT '',
    work_mode     text NOT NULL DEFAULT '',   -- On-site, Hybrid, Remote
    salary        text NOT NULL DEFAULT '',
    applied_on    date,
    deadline      date,
    follow_up_on  date,
    source        text NOT NULL DEFAULT '',   -- LinkedIn, Referral, Handshake, ...
    referral      text NOT NULL DEFAULT '',
    contact       text NOT NULL DEFAULT '',
    url           text NOT NULL DEFAULT '',
    resume        text NOT NULL DEFAULT '',
    notes         text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX applications_stage_idx ON applications (stage);

-- Timeline: every stage change and every note, in order.
CREATE TABLE application_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id  uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    occurred_on     date NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('stage', 'note')),
    stage           text CHECK (stage IN ('wishlist', 'applied', 'assessment', 'interview',
                                          'offer', 'rejected', 'withdrawn', 'ghosted')),
    body            text NOT NULL DEFAULT '',
    position        integer NOT NULL DEFAULT 0,
    CONSTRAINT stage_events_name_a_stage CHECK (kind <> 'stage' OR stage IS NOT NULL)
);

CREATE INDEX application_events_app_idx ON application_events (application_id, occurred_on, position);

CREATE FUNCTION touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER applications_touch_updated_at
    BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- One row per application with derived fields, handy for ad-hoc queries in psql.
CREATE VIEW application_overview AS
SELECT
    a.*,
    COALESCE(GREATEST(a.applied_on, ev.last_event_on), a.created_at::date) AS last_activity,
    (a.applied_on IS NOT NULL
        OR a.stage <> 'wishlist' AND a.stage <> 'withdrawn'
        OR COALESCE(ev.reached_applied, false))                          AS sent,
    (a.stage IN ('assessment', 'interview', 'offer', 'rejected')
        OR COALESCE(ev.reached_response, false))                         AS heard_back,
    (a.stage IN ('interview', 'offer')
        OR COALESCE(ev.reached_interview, false))                        AS interviewed,
    ev.first_response_on,
    ev.first_response_on - a.applied_on                                  AS days_to_response
FROM applications a
LEFT JOIN LATERAL (
    SELECT
        max(e.occurred_on)                                                         AS last_event_on,
        bool_or(e.stage IN ('applied', 'assessment', 'interview', 'offer',
                            'rejected', 'ghosted'))                                AS reached_applied,
        bool_or(e.stage IN ('assessment', 'interview', 'offer', 'rejected'))       AS reached_response,
        bool_or(e.stage IN ('interview', 'offer'))                                 AS reached_interview,
        min(e.occurred_on) FILTER (
            WHERE e.stage IN ('assessment', 'interview', 'offer', 'rejected'))     AS first_response_on
    FROM application_events e
    WHERE e.application_id = a.id
) ev ON true;
