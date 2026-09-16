from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.backends import BaseBackend


User = get_user_model()


SHIBBOLETH_SESSION_ONLY_PATH_PREFIXES = (
    "/dashboard/live-status",
    "/task-status",
    "/api/",
    "/media/",
    "/static/",
    "/telegram-webhook",
    "/whatsapp-webhook",
    "/Shibboleth.sso",
)


class ShibbolethBackend(BaseBackend):
    def authenticate(self, request, shib_uid=None, **kwargs):
        if not shib_uid:
            return None

        user, _ = User.objects.get_or_create(
            username=shib_uid,
            defaults={
                "is_active": True,
            },
        )

        return user if user.is_active else None

    def get_user(self, user_id):
        try:
            return User.objects.get(
                pk=user_id,
                is_active=True,
            )
        except User.DoesNotExist:
            return None


class ShibbolethMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # -------------------------------------------------------------
        # DEV AUTO LOGIN
        #
        # This mode works ONLY when:
        #
        #   DEBUG=True
        #   DEV_AUTO_LOGIN=true
        #   SHIBBOLETH_AUTH=false
        #
        # Therefore it cannot activate in production when DEBUG=False.
        # -------------------------------------------------------------
        if (
            settings.DEBUG
            and getattr(settings, "DEV_AUTO_LOGIN", False)
            and not getattr(settings, "SHIBBOLETH_AUTH", False)
        ):
            self._dev_auto_login(request)
            return self.get_response(request)

        # -------------------------------------------------------------
        # Normal non-Shibboleth mode
        # -------------------------------------------------------------
        if not getattr(settings, "SHIBBOLETH_AUTH", False):
            return self.get_response(request)

        # -------------------------------------------------------------
        # Production Shibboleth mode
        # -------------------------------------------------------------
        if request.path_info.startswith(
            SHIBBOLETH_SESSION_ONLY_PATH_PREFIXES
        ):
            return self.get_response(request)

        uid = request.META.get(
            "HTTP_X_SHIB_UID",
            "",
        ).strip()

        if uid and not request.user.is_authenticated:
            user = (
                User.objects.filter(username=uid).first()
                or self._create_from_shib(request, uid)
            )

            if user.is_active:
                login(
                    request,
                    user,
                    backend=(
                        "bot_engine.middleware."
                        "ShibbolethBackend"
                    ),
                )

        return self.get_response(request)

    @staticmethod
    def _dev_auto_login(request):
        """
        Automatically creates and logs in a development superuser.

        This function is reachable only when DEBUG=True,
        DEV_AUTO_LOGIN=True and SHIBBOLETH_AUTH=False.
        """

        if request.user.is_authenticated:
            return

        username = getattr(
            settings,
            "DEV_AUTO_LOGIN_USERNAME",
            "dev-user",
        ).strip()

        if not username:
            username = "dev-user"

        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        fields_to_update = []

        if not user.is_active:
            user.is_active = True
            fields_to_update.append("is_active")

        if not user.is_staff:
            user.is_staff = True
            fields_to_update.append("is_staff")

        if not user.is_superuser:
            user.is_superuser = True
            fields_to_update.append("is_superuser")

        if fields_to_update:
            user.save(
                update_fields=fields_to_update
            )

        login(
            request,
            user,
            backend=(
                "django.contrib.auth.backends."
                "ModelBackend"
            ),
        )

    @staticmethod
    def _create_from_shib(request, uid):
        meta = request.META

        full_name = meta.get(
            "HTTP_X_SHIB_CN",
            "",
        ).strip()

        first = meta.get(
            "HTTP_X_SHIB_GIVENNAME",
            "",
        ).strip()

        last = meta.get(
            "HTTP_X_SHIB_SN",
            "",
        ).strip()

        parts = full_name.split() if full_name else []

        first = first or (
            parts[0]
            if parts
            else ""
        )

        last = last or (
            " ".join(parts[1:])
            if len(parts) > 1
            else ""
        )

        return User.objects.create_user(
            username=uid,
            email=meta.get(
                "HTTP_X_SHIB_MAIL",
                "",
            ).strip(),
            first_name=first,
            last_name=last,
        )