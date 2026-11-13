from django.db import migrations

CREATE = """
CREATE FUNCTION findings_note_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'finding notes are append-only' USING ERRCODE = 'integrity_constraint_violation';
END;
$$;
CREATE TRIGGER findings_note_no_update_delete
    BEFORE UPDATE OR DELETE ON findings_findingnote
    FOR EACH ROW EXECUTE FUNCTION findings_note_immutable();
"""
DROP = """
DROP TRIGGER IF EXISTS findings_note_no_update_delete ON findings_findingnote;
DROP FUNCTION IF EXISTS findings_note_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("findings", "0003_alter_finding_source_findingtemplate_findingnote")]
    operations = [migrations.RunSQL(CREATE, DROP)]
