CREATE TYPE account_status AS ENUM ('PERMITTED', 'PROHIBITED');

CREATE TYPE transaction_status AS ENUM ('approved', 'rejected', 'two_factor_required');

CREATE TYPE decision_reason AS ENUM (
    'ACCOUNT_BLOCKED',
    'DEST_FRAUD_MARKED',
    'DEST_RECEIVING_VELOCITY',
    'DEST_NEW_ACCOUNT',
    'DEST_HIGH_AMOUNT',
    'SRC_HIGH_AMOUNT',
    'SRC_SENDING_VELOCITY',
    'SRC_NEW_DEVICE',
    'SRC_LOCATION_MISMATCH'
);

CREATE TYPE account_event_reason AS ENUM (
    'REPEATED_RISK_REJECTIONS_DEST',
    'REPEATED_RISK_REJECTIONS_SRC',
    'MANUAL_UNBLOCK'
);

CREATE TABLE account(
    id                              SERIAL PRIMARY KEY,
    participant                     VARCHAR(8) NOT NULL,
    branch                          VARCHAR(10) NOT NULL,
    account_number                  VARCHAR(20) NOT NULL,
    opening_date                    TIMESTAMPTZ NOT NULL,
    document_number                 VARCHAR(14) NOT NULL,
    status                          account_status NOT NULL DEFAULT 'PERMITTED',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    UNIQUE(participant, branch, account_number)
);

CREATE INDEX account_document_number_idx ON account(document_number);

CREATE TABLE transaction(
    id                              SERIAL PRIMARY KEY,
    pix_id                          VARCHAR(16) NOT NULL,
    transaction_key                 UUID NOT NULL,
    amount                          BIGINT NOT NULL,
    transaction_date                TIMESTAMPTZ NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    source_account_id               INTEGER NOT NULL REFERENCES account(id),
    destination_account_id          INTEGER NOT NULL REFERENCES account(id),
    device_id                       VARCHAR NOT NULL,
    channel                         VARCHAR NOT NULL,
    ip                              INET NOT NULL,
    latitude                        DOUBLE PRECISION,
    longitude                       DOUBLE PRECISION,
    status                          transaction_status NOT NULL,
    decision_reasons                decision_reason[] NOT NULL DEFAULT '{}',
    UNIQUE(pix_id),
    UNIQUE(transaction_key),
    CHECK ((status = 'approved') = (cardinality(decision_reasons) = 0))
);

CREATE INDEX transaction_source_created_idx ON transaction(source_account_id, created_at);
CREATE INDEX transaction_destination_created_idx ON transaction(destination_account_id, created_at);

CREATE INDEX transaction_source_status_created_idx ON transaction(source_account_id, status, created_at);
CREATE INDEX transaction_destination_status_created_idx ON transaction(destination_account_id, status, created_at);

CREATE TABLE events(
    id                              SERIAL PRIMARY KEY,
    account_id                      INTEGER NOT NULL REFERENCES account(id),
    transaction_id                  INTEGER REFERENCES transaction(id),
    from_status                     account_status NOT NULL,
    to_status                       account_status NOT NULL,
    reason                          account_event_reason NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT(NOW()),
    CHECK (from_status <> to_status)
);

CREATE INDEX events_account_created_idx ON events(account_id, created_at);
