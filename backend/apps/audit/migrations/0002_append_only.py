from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent is append-only (% blocked)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditevent_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_block_mutation();

CREATE TRIGGER audit_auditevent_no_truncate
    BEFORE TRUNCATE ON audit_auditevent
    FOR EACH STATEMENT EXECUTE FUNCTION audit_block_mutation();

-- The runtime role may only append and read. (Role is absent in ad-hoc databases.)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redshadow_app') THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditevent FROM redshadow_app;
    END IF;
END
$$;
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditevent_no_truncate ON audit_auditevent;
DROP TRIGGER IF EXISTS audit_auditevent_no_update_delete ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_block_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
