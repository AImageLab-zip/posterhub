from django.conf import settings

from .access import is_group_manager, user_can_interact


def group_membership_status(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    return {
        "user_can_interact": user_can_interact(user),
        "admin_contact_email": settings.ADMIN_CONTACT_EMAIL,
        "is_group_manager": is_group_manager(user),
    }
