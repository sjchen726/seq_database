from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0027_linkermodule'),
    ]
    operations = [
        migrations.AlterField(
            model_name='seqmodule',
            name='base_char',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
