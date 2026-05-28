from django.db import migrations, models


def convert_naked_length_to_int(apps, schema_editor):
    """将 naked_length 字符串值转为整数（无法转换的设为 NULL）。"""
    Delivery = apps.get_model('app01', 'Delivery')
    for d in Delivery.objects.filter(naked_length__isnull=False).exclude(naked_length=''):
        try:
            int_val = int(float(d.naked_length))
            # 用 queryset update 避免触发信号
            Delivery.objects.filter(pk=d.pk).update(naked_length=str(int_val))
        except (ValueError, TypeError):
            Delivery.objects.filter(pk=d.pk).update(naked_length=None)


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0029_drop_seqmodule_type_code'),
    ]
    operations = [
        # Step A: 数据迁移（字符串 → 整数字符串，清除非法值）
        migrations.RunPython(convert_naked_length_to_int, migrations.RunPython.noop),
        # Step B: 字段类型变更
        migrations.AlterField(
            model_name='delivery',
            name='naked_length',
            field=models.IntegerField(verbose_name='Naked Length', null=True, blank=True),
        ),
    ]
