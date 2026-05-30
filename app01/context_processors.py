from app01.models import ProjectAccessRequest


def pending_approval_count(request):
    """Inject pending project-request count for superadmin sidebar badge."""
    count = 0
    if (request.user.is_authenticated and
            (request.user.is_superuser or
             getattr(request.user, 'user_type', '') == 'superadmin')):
        count = ProjectAccessRequest.objects.filter(status='pending').count()
    return {'pending_approval_count': count}
