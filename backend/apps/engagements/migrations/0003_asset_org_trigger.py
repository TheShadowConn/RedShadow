from django.db import migrations

CREATE = """
CREATE FUNCTION engagements_check_asset_org() RETURNS trigger AS $$
BEGIN
    IF (SELECT organisation_id FROM organisations_asset WHERE id = NEW.asset_id)
       IS DISTINCT FROM
       (SELECT organisation_id FROM engagements_engagement WHERE id = NEW.engagement_id) THEN
        RAISE EXCEPTION 'asset organisation does not match engagement organisation'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER engagement_asset_same_org
    BEFORE INSERT OR UPDATE OF asset_id, engagement_id ON engagements_engagementasset
    FOR EACH ROW EXECUTE FUNCTION engagements_check_asset_org();
"""

DROP = """
DROP TRIGGER IF EXISTS engagement_asset_same_org ON engagements_engagementasset;
DROP FUNCTION IF EXISTS engagements_check_asset_org();
"""


class Migration(migrations.Migration):
    dependencies = [("engagements", "0002_initial")]
    operations = [migrations.RunSQL(CREATE, DROP)]
