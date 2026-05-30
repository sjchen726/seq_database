from app01.models import ProjectAccessRequest, ModulePermissionRequest


def pending_approval_count(request):
    """Inject total pending request count (project + module) for superadmin sidebar badge."""
    count = 0
    if (request.user.is_authenticated and
            (request.user.is_superuser or
             getattr(request.user, 'user_type', '') == 'superadmin')):
        count = (ProjectAccessRequest.objects.filter(status='pending').count()
               + ModulePermissionRequest.objects.filter(status='pending').count())
    return {'pending_approval_count': count}
