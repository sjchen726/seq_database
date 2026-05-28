from django.db import migrations, models
from django.db.models import Count


def remove_duplicate_sequences(apps, schema_editor):
    """保留每组 (seq, seq_type) 中 rm_code 最小的记录，删除其余。级联删除关联数据。"""
    Sequence = apps.get_model('app01', 'Sequence')

    dupes = (Sequence.objects
        .values('seq', 'seq_type')
        .annotate(cnt=Count('rm_code'))
        .filter(cnt__gt=1))

    total_deleted = 0
    for d in dupes:
        qs = list(
            Sequence.objects
            .filter(seq=d['seq'], seq_type=d['seq_type'])
            .order_by('rm_code')
        )
        to_delete = qs[1:]  # 保留第一条（rm_code 最小），删其余
        for obj in to_delete:
            print(f"[migration] 删除重复 Sequence: rm_code={obj.rm_code}, seq_type={obj.seq_type}")
            obj.delete()  # 级联删除 Delivery、DuplexRelationship、SeqInfo
            total_deleted += 1

    print(f"[migration] 共删除 {total_deleted} 条重复 Sequence 记录")


class Migration(migrations.Migration):
    dependencies = [
        ('app01', '0030_naked_length_to_integer'),
    ]
    operations = [
        # Step A: 清重
        migrations.RunPython(remove_duplicate_sequences, migrations.RunPython.noop),
        # Step B: 加唯一约束
        migrations.AddConstraint(
            model_name='sequence',
            constraint=models.UniqueConstraint(
                fields=['seq', 'seq_type'],
                name='unique_sequence_seq_seqtype',
            ),
        ),
    ]
