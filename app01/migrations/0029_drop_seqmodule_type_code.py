# Generated migration: drop legacy type_code column from app01_seqmodule

from django.db import migrations


def drop_type_code_if_exists(apps, schema_editor):
    """Drop the type_code column from app01_seqmodule only if it exists."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'app01_seqmodule' "
            "AND COLUMN_NAME = 'type_code'"
        )
        (count,) = cursor.fetchone()
        if count:
            cursor.execute('ALTER TABLE app01_seqmodule DROP COLUMN type_code')


class Migration(migrations.Migration):

    dependencies = [
        ('app01', '0028_seqmodule_base_char_maxlen'),
    ]

    operations = [
        migrations.RunPython(drop_type_code_if_exists, migrations.RunPython.noop),
    ]
