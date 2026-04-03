from django.db import models
from django.contrib.auth.models import AbstractUser
import random
import hashlib

# Create your models here.


# 生成6位随机编号
def generate_random_code():
    return str(random.randint(100000, 999999))  # 返回一个6位数字的随机编码

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
    seq = models.CharField('Sequence', max_length=100, null=True)  # 存储序列（如 AUGC）
  #  Target = models.CharField('Target', max_length=64, null=True)
    Pos = models.CharField('Pos', max_length=64, null=True)
    project = models.CharField('项目', max_length=64, null=True)  # 项目号
   # Strand_MWs = models.CharField('Strand_MWs', max_length=64, null=True)
    Transcript = models.CharField('Transcription', max_length=64, null=True)
   # parents = models.CharField('parents', max_length=200, null=True)  
    Remark = models.CharField('Remark', max_length=64, null=True, blank=True, default='') #备注

    created_at = models.DateTimeField('Created At',  blank=True, null=True)  # 创建时间

    def __str__(self):
        return f"Target: {self.target}, Pos: {self.pos}"
    


# 作者的类
class Author(models.Model):
    id = models.AutoField('序号', primary_key=True)
    name = models.CharField('姓名', max_length=64)
    sex = models.CharField('性别', max_length=4)
    age = models.IntegerField('年龄', default=0)
    tel = models.CharField('联系方式', max_length=64)
# 允许查看的项目号
    permissions_project = models.CharField('available_pro', max_length=256, null=True, blank=True)  


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

    Remark = models.CharField('Remark', max_length=64, null=True, blank=True, default='') #备注
    

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

    def __str__(self):
        return f"{self.username} ({self.user_type})"
    


#注册模块分类
class DeliveryModule(models.Model):
    keyword = models.CharField(max_length=100, unique=True)
    type_code = models.CharField(max_length=10, blank=True)
    Strand_MWs = models.CharField('Strand_MWs', max_length=64, null=True) # 分子量

    def __str__(self):
        return self.keyword
