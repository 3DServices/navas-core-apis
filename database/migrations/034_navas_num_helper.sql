-- navas_num(text) — read a number out of a text column, or NULL
-- Description: dll_user_token_accounts stores every column as text, and the
-- billing code writes English sentences into value columns:
--
--   token_hours_left / token_hours_used  → 'column deprecated use token_units_left column'
--   token_units_left / token_used_units  → 'units_unfined_waiting_for_first_use'
--
-- Any SQL that casts those to numeric raises
-- "invalid input syntax for type numeric" and takes the whole endpoint with
-- it. This function returns the number when there is one and NULL when there
-- is not, so a row with an unreadable value drops out of a comparison instead
-- of killing the query.
--
-- NULL is deliberate, not 0. COALESCE(..., 0) would turn "we cannot read this"
-- into "this account has zero", which is how a token awaiting its first use
-- ends up reported as expired.

CREATE OR REPLACE FUNCTION navas_num(value text) RETURNS numeric AS $$
BEGIN
    IF value IS NULL THEN
        RETURN NULL;
    END IF;
    IF btrim(value) ~ '^-?[0-9][0-9,]*(\.[0-9]+)?$' THEN
        RETURN replace(btrim(value), ',', '')::numeric;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION navas_num(text) IS
    'Parse a numeric value out of a text billing column; NULL when the value '
    'is a sentinel, a deprecation notice, empty, or otherwise not a number. '
    'Never returns 0 for an unreadable value.';
