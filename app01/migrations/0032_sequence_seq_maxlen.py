from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0031_sequence_unique_seq_seqtype'),
    ]
    operations = [
        migrations.AlterField(
            model_name='sequence',
            name='seq',
            field=models.CharField('Sequence', max_length=500, null=True),
        ),
    ]
