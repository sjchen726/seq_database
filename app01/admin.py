from django.contrib import admin
from .models import Sequence, Delivery, SeqInfo, DuplexRelationship, DeliveryModule, SeqModule, LmsUser


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ('rm_code', 'seq', 'seq_type', 'created_at')
    list_filter = ('seq_type',)
    search_fields = ('rm_code', 'seq')


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'delivery_id', 'duplex_id', 'sequence', 'project', 'seq_type', 'Strand_MWs', 'created_at')
    list_filter = ('seq_type', 'project')
    search_fields = ('delivery_id', 'duplex_id', 'modify_seq', 'project', 'Target')
    raw_id_fields = ('sequence',)


@admin.register(SeqInfo)
class SeqInfoAdmin(admin.ModelAdmin):
    list_display = ('id', 'sequence', 'Pos', 'project', 'Transcript', 'Remark')
    search_fields = ('sequence__rm_code', 'Transcript', 'Pos', 'project')
    raw_id_fields = ('sequence',)


@admin.register(DuplexRelationship)
class DuplexRelationshipAdmin(admin.ModelAdmin):
    list_display = ('id', 'as_seq', 'ss_seq', 'duplex_seq', 'created_at')
    raw_id_fields = ('as_seq', 'ss_seq', 'duplex_seq')


@admin.register(DeliveryModule)
class DeliveryModuleAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'type_code', 'Strand_MWs')
    search_fields = ('keyword', 'type_code')


@admin.register(SeqModule)
class SeqModuleAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'base_char', 'linker_connector', 'description')
    search_fields = ('keyword', 'base_char')
    list_filter = ('linker_connector',)


@admin.register(LmsUser)
class LmsUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'user_type', 'is_admin', 'is_superuser', 'permissions_project')
    list_filter = ('user_type', 'is_admin', 'is_superuser')
    search_fields = ('username', 'email', 'permissions_project')
