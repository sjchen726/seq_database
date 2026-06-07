import re
from django.db import models
from django.contrib.auth.models import AbstractUser


class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('guest', 'guest'),
        ('delivery', 'delivery'),
        ('modify', 'modify'),
        ('project', 'project'),
        ('data_admin', 'data_admin'),
        ('admin', 'admin'),
        ('superadmin', 'superadmin'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='guest')
    permissions_project = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'lms_user'


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
    """Parse BPR_3M03FN01 → project='3M03', target='FN'.
    Assumes project code is alphanumeric (digits + uppercase) and target is exactly 2 uppercase letters.
    The greedy match on project is correct as long as the project code does not end in 2+ uppercase letters.
    """
    m = re.match(r'^BPR_([A-Z0-9]+)([A-Z]{2})(\d{2,3})$', compound_id)
    if m:
        return m.group(1), m.group(2)
    return '', ''


class Compound(models.Model):
    compound_id = models.CharField(max_length=32, primary_key=True)
    project = models.CharField(max_length=32, blank=True, db_index=True)
    target = models.CharField(max_length=32, blank=True, db_index=True)
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
