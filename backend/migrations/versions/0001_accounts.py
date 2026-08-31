"""Accounts: orgs, users, sign-in codes and sessions

Revision ID: 0001
Revises:
Create Date: 2026-08-31

The first schema this database carries. Everything sign-in needs, and the
`org` table that parla's `parla_machine.org_id` will point at in 0002.

Design notes:

- **Credentials are stored as digests, never in plaintext.** A sign-in
  code is an HMAC keyed with `LOGIN_CODE_SECRET` (a bare digest of six
  digits is worth nothing — the whole space walks in microseconds), and a
  session token a plain sha256. Whoever holds such a string is the
  caller, so a leaked table must yield nothing replayable.
- **No passwords**, so there is nothing to hash, rotate, reset or leak.
- **`login_tokens.email` is deliberately not a foreign key.** The
  request-code endpoint answers identically for every address; an FK
  would leak, through a constraint violation, whether an account exists.
- **`used` rather than a delete** keeps single-use enforceable in one
  guarded statement (`UPDATE … WHERE used = false AND expires_at >= now()
  … RETURNING`), so a double-submitted code is consumed exactly once even
  under a race.
- **`users.email` is unique over `lower(email)`**, not over the raw
  column. The route layer lowercases before writing; the functional index
  is what makes one address one account no matter how it was typed.
- **One org per user**, created at first sign-in. `parla_machine.org_id`
  needs a real target with a real `ON DELETE CASCADE`; multi-user orgs are
  a later decision that this schema does not block.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE org (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            -- Stored lowercased by the route layer; the index below is what
            -- enforces it as a one-account-per-identity rule.
            email text NOT NULL,
            org_id uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE UNIQUE INDEX users_email_lower_idx ON users (lower(email));
        CREATE INDEX users_org_idx ON users (org_id);

        CREATE TABLE login_tokens (
            -- No FK on email: see the module docstring.
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email text NOT NULL,
            -- HMAC-sha256 of the six-digit code, keyed with LOGIN_CODE_SECRET.
            code_hash text NOT NULL,
            code_attempts int NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            used boolean NOT NULL DEFAULT false
        );

        -- Carries the per-address cooldown lookup ("newest row for this
        -- address"), which is the cross-worker half of the mail-bombing
        -- defense; Caddy caps the same endpoint per IP.
        CREATE INDEX login_tokens_email_created_idx
            ON login_tokens (email, created_at);
        -- The opportunistic sweep of spent rows on the public endpoint.
        CREATE INDEX login_tokens_expires_idx ON login_tokens (expires_at);

        CREATE TABLE sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            -- sha256 hex of the token carried by the session cookie.
            token_hash text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL
        );

        CREATE INDEX sessions_user_idx ON sessions (user_id);
        CREATE INDEX sessions_expires_idx ON sessions (expires_at);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE sessions;
        DROP TABLE login_tokens;
        DROP TABLE users;
        DROP TABLE org;
    """)
