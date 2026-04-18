from django.db import models
from django.contrib.auth.models import AbstractUser
import random
import hashlib

# Create your models here.


# 生成6位随机编号（含碰撞检测）
def generate_random_code():
    while True:
        code = str(random.randint(100000, 999999))
        if not Sequence.objects.filter(rm_code=code).exists():
            return code

# 存储序列信息
class Sequence(models.Model):
    SEQUENCE_TYPE_CHOICES = (
        ('duplex', 'Duplex'),
        ('AS', 'AS'),
        ('SS', 'SS'),
    )

    rm_code = models.CharField('RM_Code', max_length=6, primary_key=True, unique=True, default=generate_random_code)  # RM_6编号
    seq = models.CharField('Sequence', max_length=100, null=True)  # 存储序列（如 AUGC）
    seq_type = models.CharField('Sequence Type', max_length=10, choices=SEQUENCE_TYPE_CHOICES)  # duplex, AS, SS
    created_at = models.DateTimeField('Created At',  blank=True, null=True)  # 创建时间

    class Meta:
        indexes = [
            models.Index(fields=['seq']),  # 加快查询速度
            models.Index(fields=['seq_type']),
            models.Index(fields=['seq', 'seq_type'], name='idx_sequence_seq_seqtype'),
        ]

    def __str__(self):
        return f"{self.seq_type} ({self.rm_code})"
    
# 储存AS和SS之间的对应关系，并关联到Duplex
class DuplexRelationship(models.Model):
    as_seq = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="as_sequences", limit_choices_to={'seq_type': 'AS'})
    ss_seq = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="ss_sequences", limit_choices_to={'seq_type': 'SS'})
    duplex_seq = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="duplex_sequences", limit_choices_to={'seq_type': 'duplex'})

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('as_seq', 'ss_seq') #限制AS-SS唯一的组合

    def __str__(self):
        return f"AS: {self.as_seq.seq} <-> SS: {self.ss_seq.seq} <-> Duplex: {self.duplex_seq.seq}"

# 存储目标信息
class SeqInfo(models.Model):
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name='target_info')  # 外键关联到Sequence
  #  Target = models.CharField('Target', max_length=64, null=True)
    Pos = models.CharField('Pos', max_length=512, null=True)
    project = models.CharField('项目', max_length=128, null=True)  # 项目号
   # Strand_MWs = models.CharField('Strand_MWs', max_length=64, null=True)
    Transcript = models.CharField('Transcription', max_length=512, null=True)
   # parents = models.CharField('parents', max_length=200, null=True)
    Remark = models.CharField('Remark', max_length=512, null=True, blank=True, default='') #备注

    created_at = models.DateTimeField('Created At',  blank=True, null=True)  # 创建时间

    def __str__(self):
        return f"Seq: {self.sequence.seq if self.sequence_id else ''}, Pos: {self.Pos}"
    



class Delivery(models.Model):
    id = models.AutoField(primary_key=True)  # 默认自增主键
    delivery_id = models.CharField('Delivery ID', max_length=20, null=True)  # 可重复  # 原始 delivery ID（如 SEQ001.1）
    duplex_id = models.CharField('duplex_id', max_length=24, null=True)  # duplex_id编号
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name='deliveries')  # 外键关联到Sequence表，裸序列的相关ID
    modify_seq = models.CharField('modify_seq', max_length=500, null=True)  # 存储序列（如 AUGC）
    linker_seq = models.CharField('linker_seq', max_length=500, null=True)  # 存储序列（如 AoUoGo）
    naked_length = models.CharField('Naked Length', max_length=100, null=True)  # Naked Length
    delivery5 = models.CharField('Delivery5', max_length=100, null=True)  # 递送内容 5
    delivery3 = models.CharField('Delivery3', max_length=100, null=True)  # 递送内容 3
    Strand_MWs = models.CharField('Strand_MWs', max_length=64, null=True) # 分子量
    project = models.CharField('项目', max_length=64, null=True)  # 项目号
    created_at = models.DateTimeField('Created At',  blank=True, null=True)  # 创建时间
    parents = models.CharField('parents', max_length=200, null=True)  # parents
    seq_type = models.CharField('seq_type', max_length=6, null=True)  # seq_type
    Target = models.CharField('Target', max_length=64, null=True)

    Remark = models.CharField('Remark', max_length=512, null=True, blank=True, default='') #备注

    class Meta:
        indexes = [
            # 主列表视图：按项目+双链ID分组（build_duplex_groups 核心查询）
            models.Index(fields=['project', 'duplex_id'], name='idx_delivery_project_duplex'),
            # 权限过滤（get_permitted_delivery_qs）
            models.Index(fields=['project'], name='idx_delivery_project'),
            # 序列+链型联合查询（blast_seq、cor_seq）
            models.Index(fields=['sequence', 'seq_type'], name='idx_delivery_seq_seqtype'),
            # 重复检测（save_deliveries 中的 duplicate 查询）
            models.Index(fields=['delivery5', 'delivery3', 'linker_seq'], name='idx_delivery_dedup'),
            # Blast 查询
            models.Index(fields=['duplex_id'], name='idx_delivery_duplex_id'),
        ]

    def __str__(self):
        return f"Delivery for {self.sequence.rm_code}"


class LmsUser(AbstractUser):
    # 用户类别常量
    PROJECT_MANAGEMENT = 'project'
    DELIVERY = 'delivery'
    MODIFY = 'modify'
    GUEST = 'guest'
    superadmin = 'superadmin'
    admin = 'admin'
    data_admin = 'data_admin'

    USER_TYPE_CHOICES = [
        (PROJECT_MANAGEMENT, '项目管理'),
        (DELIVERY, '递送'),
        (MODIFY, '修饰'),
        (GUEST, '访客'),
        (superadmin, '超级管理员'),
        (admin, '管理员'),
        (data_admin, '数据库管理员'),
        # 其他用户类型可以在这里添加
    ]

    # 用户类型字段
    user_type = models.CharField(
        '用户类型',
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default=GUEST,
    )

    is_admin = models.BooleanField('是否为管理员', default=False)

    # 添加权限项目字段
    permissions_project = models.CharField(
        '可查看的项目号',
        max_length=256,
        null=True,
        blank=True
    )


    class Meta:
        verbose_name = '用户'
        verbose_name_plural = '用户'

    def get_allowed_projects(self):
        """返回该用户有权限查看的项目列表"""
        if not self.permissions_project:
            return []
        return [p.strip() for p in self.permissions_project.split(',') if p.strip()]

    def can_manage_modules(self):
        """判断该用户是否有权限管理模块"""
        return self.is_superuser or self.user_type in ('data_admin', 'admin', 'superadmin')

    def __str__(self):
        return f"{self.username} ({self.user_type})"
    


#注册模块分类
class DeliveryModule(models.Model):
    keyword = models.CharField(max_length=100, unique=True)
    type_code = models.CharField(max_length=10, blank=True)
    Strand_MWs = models.CharField('Strand_MWs', max_length=64, null=True) # 分子量

    def __str__(self):
        return self.keyword


# 存储序列规范化修饰模块（用于 save_deliveries 和 add_o_to_all_rules）
class SeqModule(models.Model):
    keyword = models.CharField(max_length=100, unique=True)          # 修饰码，如 "VP25A", "GU02", "T(MOE)"
    base_char = models.CharField(max_length=10, null=True, blank=True)  # 对应裸碱基（A/U/G/C/INVAB），纯连接符留空
    linker_connector = models.CharField(max_length=2, default='o')   # linker_seq 中当后一位不是 's' 且非末尾时追加的字符
    description = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return self.keyword
