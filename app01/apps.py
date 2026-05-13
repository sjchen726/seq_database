from django.apps import AppConfig


class App01Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app01'

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver
        from .models import Delivery, DeliveryProject

        @receiver(post_save, sender=Delivery)
        def create_delivery_project(sender, instance, created, **kwargs):
            if created and instance.project:
                DeliveryProject.objects.get_or_create(
                    delivery=instance,
                    project_code=instance.project,
                )
