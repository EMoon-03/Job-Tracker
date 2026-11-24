-- 002_next_step: a free-text "what's next" line per application (paired with follow_up_on).

ALTER TABLE applications ADD COLUMN next_step text NOT NULL DEFAULT '';

-- application_overview selects a.*, so rebuild it to pick up the new column.
DROP VIEW application_overview;

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
