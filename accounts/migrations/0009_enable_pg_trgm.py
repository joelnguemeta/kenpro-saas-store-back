"""
Active l'extension PostgreSQL pg_trgm (recherche par similarité trigram,
utilisée par UserSearchView). No-op sur SQLite — la vue retombe alors sur
une recherche icontains.
"""
from django.db import migrations


def enable_pg_trgm(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_must_change_password"),
    ]

    operations = [
        migrations.RunPython(enable_pg_trgm, migrations.RunPython.noop),
    ]
