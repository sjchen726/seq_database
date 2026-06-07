from django.contrib import admin
from .models import (
    LmsUser, SeqModule, LinkerModule, DeliveryModule,
    Compound, Strand, Experiment, DataPoint, ExperimentSummary,
)


@admin.register(LmsUser)
class LmsUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'user_type', 'is_superuser', 'permissions_project')
    list_filter = ('user_type', 'is_superuser')
    search_fields = ('username', 'email', 'permissions_project')


@admin.register(SeqModule)
class SeqModuleAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'base_char', 'linker_connector', 'description')
    search_fields = ('keyword', 'base_char')


@admin.register(LinkerModule)
class LinkerModuleAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'description')
    search_fields = ('keyword',)


@admin.register(DeliveryModule)
class DeliveryModuleAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'type_code', 'description')
    search_fields = ('keyword', 'type_code')


@admin.register(Compound)
class CompoundAdmin(admin.ModelAdmin):
    list_display = ('compound_id', 'project', 'target', 'transcript_ref', 'created_at')
    list_filter = ('project', 'target')
    search_fields = ('compound_id', 'project', 'target', 'transcript_ref')


@admin.register(Strand)
class StrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'compound', 'strand_type', 'sequence_id')
    list_filter = ('strand_type',)
    search_fields = ('compound__compound_id', 'sequence_id', 'modify_seq')
    raw_id_fields = ('compound',)


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ('id', 'compound', 'exp_type', 'assay_name', 'batch_label', 'date', 'created_at')
    list_filter = ('exp_type',)
    search_fields = ('compound__compound_id', 'assay_name', 'batch_label')
    raw_id_fields = ('compound',)


@admin.register(DataPoint)
class DataPointAdmin(admin.ModelAdmin):
    list_display = ('id', 'experiment', 'x_value', 'x_type', 'replicate', 'value', 'readout_type')
    list_filter = ('x_type', 'readout_type', 'is_control', 'is_flagged')
    raw_id_fields = ('experiment',)


@admin.register(ExperimentSummary)
class ExperimentSummaryAdmin(admin.ModelAdmin):
    list_display = ('experiment', 'max_kd_pct', 'ic50_nm', 'rank')
    raw_id_fields = ('experiment',)
