# Generated migration: drop legacy type_code column from app01_seqmodule

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app01', '0028_seqmodule_base_char_maxlen'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE app01_seqmodule DROP COLUMN type_code;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
