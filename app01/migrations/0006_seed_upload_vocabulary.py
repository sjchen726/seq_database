from django.db import migrations


BUILTIN_VOCABULARY = [
    # file types
    ('file_type', 'vitro_summary',       '体外汇总（IC50/MaxKD）'),
    ('file_type', 'vitro_seq',           '体外序列文件'),
    ('file_type', 'vitro_cp',            'Cp 原始文件 (RT-qPCR)'),
    ('file_type', 'vitro_transfection',  '转染方案'),
    ('file_type', 'invivo_summary',      '体内数据汇总'),
    ('file_type', 'custom_attachment',   '其他（附件,不解析）'),
    # invivo readouts
    ('invivo_readout', 'knockdown_pct', 'KD%'),
    ('invivo_readout', 'body_weight',   '体重'),
    ('invivo_readout', 'tumor_volume',  '肿瘤体积'),
    ('invivo_readout', 'alt_value',     'ALT'),
    ('invivo_readout', 'custom',        '其他...'),
]


def seed_vocab(apps, schema_editor):
    UploadVocabulary = apps.get_model('app01', 'UploadVocabulary')
    for category, code, label in BUILTIN_VOCABULARY:
        UploadVocabulary.objects.update_or_create(
            category=category, code=code,
            defaults={'label': label, 'is_builtin': True},
        )


def unseed_vocab(apps, schema_editor):
    UploadVocabulary = apps.get_model('app01', 'UploadVocabulary')
    for category, code, _label in BUILTIN_VOCABULARY:
        UploadVocabulary.objects.filter(category=category, code=code, is_builtin=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0005_upload_vocabulary_project_attachment'),
    ]
    operations = [
        migrations.RunPython(seed_vocab, unseed_vocab),
    ]
