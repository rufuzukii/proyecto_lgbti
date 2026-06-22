BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL,
    email text NOT NULL,
    role text NOT NULL DEFAULT 'common',
    organization text,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_not_blank CHECK (btrim(email) <> ''),
    CONSTRAINT users_role_valid CHECK (role IN ('admin', 'common', 'anonymous'))
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key
    ON public.users (lower(email));

CREATE TABLE IF NOT EXISTS public.categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT categories_name_not_blank CHECK (btrim(name) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS categories_name_key
    ON public.categories (name);

CREATE TABLE IF NOT EXISTS public.indicators (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id uuid REFERENCES public.categories(id) ON DELETE SET NULL,
    code text NOT NULL,
    question text NOT NULL,
    definition text,
    answer_type text,
    specific_category text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT indicators_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT indicators_question_not_blank CHECK (btrim(question) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS indicators_code_key
    ON public.indicators (code);

CREATE INDEX IF NOT EXISTS indicators_category_id_idx
    ON public.indicators (category_id);

CREATE TABLE IF NOT EXISTS public.import_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    source_id uuid,
    file_name text NOT NULL,
    file_json jsonb,
    status text NOT NULL,
    records_inserted integer NOT NULL DEFAULT 0,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT import_logs_file_name_not_blank CHECK (btrim(file_name) <> ''),
    CONSTRAINT import_logs_status_valid CHECK (status IN ('pending', 'imported', 'failed', 'rejected')),
    CONSTRAINT import_logs_records_inserted_nonnegative CHECK (records_inserted >= 0)
);

CREATE INDEX IF NOT EXISTS import_logs_status_created_at_idx
    ON public.import_logs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS import_logs_user_id_idx
    ON public.import_logs (user_id);

COMMIT;
