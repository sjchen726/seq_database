import re
from django.db import models
from django.contrib.auth.models import AbstractUser


class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('user',       '普通用户'),
        ('sub_admin',  '模块管理员'),
        ('superadmin', '超级管理员'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='user')
    permissions_project = models.TextField(blank=True, default='')
    module_permissions = models.CharField(
        max_length=64, blank=True, default='',
        help_text="逗号分隔，可选值: upload,data,compound,batch",
    )

    class Meta:
        db_table = 'lms_user'


class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    ]
    user         = models.ForeignKey(LmsUser, on_delete=models.CASCADE,
                                     related_name='project_requests')
    project_code = models.CharField(max_length=64)
    status       = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    note         = models.TextField(blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    reviewed_by  = models.ForeignKey(LmsUser, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name='reviewed_requests')

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('register',          '注册'),
        ('project_request',   '申请项目'),
        ('project_approved',  '项目批准'),
        ('project_rejected',  '项目拒绝'),
        ('user_role_changed', '角色变更'),
        ('user_deleted',      '用户删除'),
    ]
    actor       = models.ForeignKey(LmsUser, on_delete=models.SET_NULL,
                                    null=True, related_name='audit_actions')
    action      = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(LmsUser, on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name='audit_events')
    detail      = models.TextField(default='')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SeqModule(models.Model):
    keyword = models.CharField(max_length=64, blank=False, db_index=True)
    base_char = models.CharField(max_length=8, blank=True)
    linker_connector = models.CharField(max_length=4, blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'seq_module'

    def __str__(self):
        return self.keyword or ''


class LinkerModule(models.Model):
    keyword = models.CharField(max_length=64, blank=False, db_index=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'linker_module'

    def __str__(self):
        return self.keyword or ''


class DeliveryModule(models.Model):
    keyword = models.CharField(max_length=64, blank=False, db_index=True)
    type_code = models.CharField(max_length=32, blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'delivery_module'

    def __str__(self):
        return self.keyword or ''


def _parse_compound_id(compound_id):
    """Parse compound ID → (project_code, target_prefix).

    Handles new canonical format BPR3M03-FN01 and legacy BPR_3M03FN01.
    """
    m = re.match(r'^BPR([A-Z0-9]+)-([A-Z]{2})\d', compound_id)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r'^BPR([A-Z0-9]+)-\d', compound_id)
    if m:
        return m.group(1), ''
    m = re.match(r'^BPR_([A-Z0-9]+)([A-Z]{2})(\d{2,3})$', compound_id)
    if m:
        return m.group(1), m.group(2)
    return '', ''


class Compound(models.Model):
    compound_id = models.CharField(max_length=32, primary_key=True)
    project = models.CharField(max_length=32, blank=True, db_index=True)
    target = models.CharField(max_length=32, blank=True, db_index=True)
    target_name = models.CharField(max_length=128, blank=True, db_index=True)
    transcript_ref = models.CharField(max_length=64, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compound'
        ordering = ['compound_id']

    def __str__(self):
        return self.compound_id

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if (not update_fields or 'compound_id' in update_fields) and self.compound_id and not self.project:
            self.project, self.target = _parse_compound_id(self.compound_id)
        super().save(*args, **kwargs)


class Strand(models.Model):
    STRAND_TYPE_CHOICES = [('SS', 'Sense'), ('AS', 'Antisense')]

    compound = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                  related_name='strands')
    strand_type = models.CharField(max_length=4, choices=STRAND_TYPE_CHOICES)
    sequence_id = models.CharField(max_length=64, blank=True, db_index=True)
    modify_seq = models.TextField(blank=True)

    class Meta:
        db_table = 'strand'
        unique_together = [('compound', 'strand_type')]

    def __str__(self):
        return f"{self.compound_id}_{self.strand_type}"


class Experiment(models.Model):
    EXP_TYPE_CHOICES = [('in_vitro', '体外'), ('in_vivo', '体内')]

    compound = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                  related_name='experiments')
    exp_type = models.CharField(max_length=16, choices=EXP_TYPE_CHOICES)
    assay_name = models.CharField(max_length=128)
    cell_line = models.CharField(max_length=64, blank=True)
    batch_label = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    animal_species = models.CharField(max_length=32, blank=True, default='')
    animal_strain = models.CharField(max_length=64, blank=True, default='')
    route = models.CharField(max_length=32, blank=True, default='')
    gender = models.CharField(max_length=16, blank=True, default='')
    time_unit = models.CharField(max_length=16, blank=True, default='')
    dose_info = models.CharField(max_length=64, blank=True, default='')
    schedule = models.CharField(max_length=64, blank=True, default='')
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'experiment'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.compound_id} | {self.exp_type} | {self.batch_label}"


class DataPoint(models.Model):
    X_TYPE_CHOICES = [('concentration', '浓度 nM'), ('timepoint', '时间点 天')]
    READOUT_CHOICES = [
        ('mRNA_remaining', 'mRNA 残余%'),
        ('knockdown_pct', 'KD%'),
        ('body_weight', '体重 g'),
    ]

    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE,
                                    related_name='datapoints')
    x_value = models.FloatField()
    x_type = models.CharField(max_length=16, choices=X_TYPE_CHOICES)
    replicate = models.CharField(max_length=8)   # A/B/1/2/3/Mean
    value = models.FloatField()
    readout_type = models.CharField(max_length=32)
    is_control = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    flag_note = models.CharField(max_length=128, blank=True)
    raw_cp = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'data_point'

    def __str__(self):
        return f"{self.experiment_id} | x={self.x_value} rep={self.replicate}"


class ExperimentSummary(models.Model):
    experiment = models.OneToOneField(Experiment, on_delete=models.CASCADE,
                                       related_name='summary')
    max_kd_pct = models.FloatField(null=True, blank=True)
    ic50_nm = models.FloatField(null=True, blank=True)
    rank = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'experiment_summary'

    def __str__(self):
        return f"{self.experiment_id} | IC50={self.ic50_nm}"


class ExperimentAttachment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE,
                                   related_name='attachments')
    file = models.FileField(upload_to='experiment_attachments/%Y/%m/', blank=True)
    label = models.CharField(max_length=128, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'experiment_attachment'

    def __str__(self):
        return f"{self.experiment_id} | {self.label}"


class UploadVocabulary(models.Model):
    """
    Extensible dropdown vocabulary for the smart upload page.

    Two categories drive two dropdowns: file_type and invivo_readout.
    Built-in entries are seeded by migration; user-added entries have
    is_builtin=False and appear in the dropdown for future uploads.
    """

    CATEGORY_CHOICES = [
        ('file_type', '文件类型'),
        ('invivo_readout', '体内 readout'),
    ]

    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, db_index=True)
    code = models.SlugField(max_length=64, allow_unicode=True)
    label = models.CharField(max_length=128)
    is_builtin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'upload_vocabulary'
        unique_together = [['category', 'code']]
        ordering = ['category', '-is_builtin', 'label']

    def __str__(self):
        return f'{self.category}:{self.label}'


class ProjectAttachment(models.Model):
    """
    Landing pad for files that the user marks as custom / "其他附件" — stored
    on disk and recorded here, no parsing. Not linked to any Experiment.
    """

    project = models.CharField(max_length=32, db_index=True)
    label = models.CharField(max_length=128)
    vocab_code = models.CharField(max_length=64, blank=True, default='')
    file = models.FileField(upload_to='project_attachments/%Y%m%d/')
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        'LmsUser', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='project_attachments',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'project_attachment'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.project} / {self.label} / {self.original_filename}'
