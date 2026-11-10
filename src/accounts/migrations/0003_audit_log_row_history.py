from django.db import migrations, models
from django.db.models import F


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_audit_log")]
    operations = [
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(F("table_name"), F("row_id"), F("created_at").desc(), name="audit_log_row_history"),
        ),
    ]
