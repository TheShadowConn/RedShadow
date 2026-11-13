from django.db import migrations

CREATE = """
CREATE FUNCTION findings_activity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'remediation activities are append-only' USING ERRCODE = 'integrity_constraint_violation';
END;
$$;
CREATE TRIGGER findings_activity_no_update_delete
    BEFORE UPDATE OR DELETE ON findings_remediationactivity
    FOR EACH ROW EXECUTE FUNCTION findings_activity_immutable();
"""
DROP = """
DROP TRIGGER IF EXISTS findings_activity_no_update_delete ON findings_remediationactivity;
DROP FUNCTION IF EXISTS findings_activity_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("findings", "0005_remediation_lifecycle")]
    operations = [migrations.RunSQL(CREATE, DROP)]
