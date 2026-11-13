from django.apps import AppConfig
from django.db.models.signals import post_migrate


class RbacConfig(AppConfig):
    name = "apps.rbac"
    label = "rbac"

    def ready(self):
        from .seed import seed_rbac

        post_migrate.connect(
            lambda sender, **kw: seed_rbac() if sender.label == "rbac" else None,
            weak=False,
            dispatch_uid="rbac-seed",
        )
