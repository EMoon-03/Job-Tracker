-- Handy reporting queries. Run one with:  psql jobtracker -f sql/queries.sql
-- or open `psql jobtracker` and paste the one you want.

-- Pipeline right now
SELECT stage, count(*) AS n
FROM applications
GROUP BY stage
ORDER BY array_position(ARRAY['wishlist','applied','assessment','interview',
                              'offer','rejected','withdrawn','ghosted'], stage);

-- Reply and interview rates by source (does a referral beat cold applying?)
SELECT COALESCE(NULLIF(source, ''), 'Not set')                      AS source,
       count(*)                                                    AS sent,
       round(100.0 * count(*) FILTER (WHERE heard_back) / count(*)) AS heard_back_pct,
       round(100.0 * count(*) FILTER (WHERE interviewed) / count(*)) AS interview_pct
FROM application_overview
WHERE sent
GROUP BY 1
ORDER BY sent DESC;

-- Same, by sector
SELECT COALESCE(NULLIF(sector, ''), 'Not set')                      AS sector,
       count(*)                                                    AS sent,
       round(100.0 * count(*) FILTER (WHERE heard_back) / count(*)) AS heard_back_pct,
       round(100.0 * count(*) FILTER (WHERE interviewed) / count(*)) AS interview_pct
FROM application_overview
WHERE sent
GROUP BY 1
ORDER BY sent DESC;

-- How long companies take to reply
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY days_to_response) AS median_days,
       min(days_to_response) AS fastest,
       max(days_to_response) AS slowest,
       count(days_to_response) AS replies_with_dates
FROM application_overview;

-- Applications sent per week (last 12 weeks)
SELECT date_trunc('week', applied_on)::date AS week_of, count(*) AS sent
FROM applications
WHERE applied_on >= current_date - interval '12 weeks'
GROUP BY 1
ORDER BY 1;

-- Waiting on a reply for 3+ weeks with no follow-up planned
SELECT company, role, applied_on, current_date - last_activity AS days_quiet
FROM application_overview
WHERE stage = 'applied' AND follow_up_on IS NULL
  AND last_activity <= current_date - 21
ORDER BY days_quiet DESC;

-- Full timeline for one company
SELECT a.company, a.role, e.occurred_on, e.kind, e.stage, e.body
FROM applications a
JOIN application_events e ON e.application_id = a.id
WHERE a.company ILIKE '%acme%'
ORDER BY e.occurred_on, e.position;
