from django.apps import AppConfig


class EngagementsConfig(AppConfig):
    name = "apps.engagements"
    label = "engagements"

    def ready(self):
        from apps.rbac import authz

        from . import selectors

        authz.register_membership_provider(selectors.membership_role)
        authz.register_membership_role_lister(selectors.membership_roles)
