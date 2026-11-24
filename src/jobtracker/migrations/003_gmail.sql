-- 003_gmail: Gmail sync bookkeeping and stage-change suggestions waiting for review.

-- Every email the sync has looked at, so it is never processed twice.
CREATE TABLE gmail_messages (
    gm_msgid        text PRIMARY KEY,          -- Gmail's X-GM-MSGID
    received_at     timestamptz NOT NULL,
    sender          text NOT NULL DEFAULT '',
    subject         text NOT NULL DEFAULT '',
    kind            text NOT NULL,             -- applied / assessment / interview / rejected / offer / viewed / other
    outcome         text NOT NULL,             -- created / suggested / noted / skipped
    application_id  uuid REFERENCES applications (id) ON DELETE SET NULL,
    processed_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gmail_suggestions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gm_msgid        text NOT NULL REFERENCES gmail_messages (gm_msgid) ON DELETE CASCADE,
    application_id  uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    proposed_stage  text NOT NULL
                    CHECK (proposed_stage IN ('applied', 'assessment', 'interview', 'offer', 'rejected')),
    occurred_on     date NOT NULL,
    subject         text NOT NULL DEFAULT '',
    snippet         text NOT NULL DEFAULT '',
    gmail_url       text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'dismissed')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    resolved_at     timestamptz
);

CREATE INDEX gmail_suggestions_pending_idx ON gmail_suggestions (status) WHERE status = 'pending';

CREATE TABLE gmail_sync_state (
    id            integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_sync_at  timestamptz,
    last_result   jsonb
);
