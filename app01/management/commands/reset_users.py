from django.core.management.base import BaseCommand
from app01.models import LmsUser


class Command(BaseCommand):
    help = 'Reset to single superadmin user (password: 123456). Deletes all other users.'

    def handle(self, *args, **options):
        superadmin = (
            LmsUser.objects.filter(is_superuser=True).first()
            or LmsUser.objects.filter(user_type='superadmin').first()
        )
        if not superadmin:
            self.stderr.write('No superadmin found. Aborting.')
            return

        superadmin.set_password('123456')
        superadmin.user_type = 'superadmin'
        superadmin.module_permissions = ''
        superadmin.is_superuser = True
        superadmin.is_active = True
        superadmin.save()

        deleted_count, _ = LmsUser.objects.exclude(pk=superadmin.pk).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Kept: {superadmin.username}. Deleted: {deleted_count} users.'
            )
        )
