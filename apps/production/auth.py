"""Being given a role in a proceedings production (or being a publisher) lets a person into the
back office, without also having to be put in a group."""


class ProductionRoleBackend:
    def authenticate(self, request, **credentials):
        return None  # only answers permission questions

    def has_perm(self, user, perm, obj=None):
        if perm != "wagtailadmin.access_admin" or not user.is_active:
            return False
        cached = getattr(user, "_iglc_production_access", None)
        if cached is None:
            from django.contrib.auth.models import Permission

            cached = user.production_roles.exists() or Permission.objects.filter(
                codename="publish_production", group__user=user).exists()
            user._iglc_production_access = cached
        return cached

    def has_module_perms(self, user, app_label):
        return False
