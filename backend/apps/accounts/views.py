import logging
from django.conf import settings
from django.contrib.auth import logout
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponseRedirect
from apps.tenants.serializers import TenantSerializer
from .serializers import UserSerializer
from .services import DevAuthService

logger = logging.getLogger("resolveai.accounts")

class SessionView(APIView):
    """
    GET /api/v1/session
    Returns the active user profile, tenant metadata, permissions list, and session details.
    Injects the active CSRF token into the response headers.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"message": "Sign in to continue."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        user = request.user
        tenant = user.tenant

        # In case user has no tenant assigned, provide fallback dummy tenant structure
        tenant_data = None
        if tenant:
            tenant_data = TenantSerializer(tenant).data
        else:
            tenant_data = {
                "id": "unassigned",
                "name": "Unassigned Institution",
                "timeZone": "Africa/Lagos",
                "support": {
                    "label": "Operations Desk",
                    "contact": "support@resolveai.bank",
                    "hours": "Mon–Fri 08:00–18:00",
                },
            }

        signed_in_at = request.session.get("signed_in_at", timezone.now().isoformat())
        idp = request.session.get("identity_provider", "ResolveAI Enterprise SSO")

        payload = {
            "user": UserSerializer(user).data,
            "tenant": tenant_data,
            "permissions": user.permissions_list,
            "session": {
                "identityProvider": idp,
                "signedInAt": signed_in_at,
                "expiresAt": None,
                "signOutAffectsOtherSessions": False,
            },
        }

        response = Response(payload, status=status.HTTP_200_OK)
        # Ensure CSRF cookie is set and token is communicated
        response["X-CSRFToken"] = get_token(request)
        return response


class SignOutView(APIView):
    """
    POST /api/v1/session/sign-out
    Terminates the active Django session and returns the post-sign-out redirection path.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_name = request.user.username
        logout(request)
        logger.info(f"User {user_name} signed out successfully.")
        return Response({"redirectUrl": "/signed-out"}, status=status.HTTP_200_OK)


class DevLoginView(APIView):
    """
    POST /api/v1/auth/dev-login
    Development-only endpoint enabling instant persona switching.
    Guarded strictly: returns 404 in production.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not (settings.DEBUG and getattr(settings, "ALLOW_DEV_AUTH", False)):
            logger.warning(
                f"Attempted access to dev-login in non-development mode from IP: {request.META.get('REMOTE_ADDR')}"
            )
            return Response(
                {"message": "Development authentication is disabled."},
                status=status.HTTP_404_NOT_FOUND
            )

        persona = request.data.get("persona", "operator")
        dev_auth = DevAuthService()
        user = dev_auth.authenticate(request, persona=persona)

        # Trigger SessionView logic
        tenant = user.tenant
        signed_in_at = request.session.get("signed_in_at", timezone.now().isoformat())
        idp = request.session.get("identity_provider", "ResolveAI Development Authenticator")

        payload = {
            "user": UserSerializer(user).data,
            "tenant": TenantSerializer(tenant).data if tenant else None,
            "permissions": user.permissions_list,
            "session": {
                "identityProvider": idp,
                "signedInAt": signed_in_at,
                "expiresAt": None,
                "signOutAffectsOtherSessions": False,
            },
        }

        response = Response(payload, status=status.HTTP_200_OK)
        response["X-CSRFToken"] = get_token(request)
        return response


class SignInView(APIView):
    """
    GET /api/v1/session/sign-in
    Development sign-in handler for browser navigation.
    In development mode (DEBUG=True and ALLOW_DEV_AUTH=True), authenticates the synthetic
    operator persona and redirects back to returnTo with session and CSRF cookies.
    In production, returns 501.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return_to = request.GET.get("returnTo", "/")
        # Ensure return_to is a safe relative path to prevent open redirect vulnerabilities
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/"

        if settings.DEBUG and getattr(settings, "ALLOW_DEV_AUTH", False):
            persona = request.GET.get("persona", "operator")
            dev_auth = DevAuthService()
            dev_auth.authenticate(request, persona=persona)
            response = HttpResponseRedirect(return_to)
            # Ensure CSRF token cookie is set
            get_token(request)
            logger.info(f"Dev browser sign-in succeeded for persona '{persona}', redirecting to {return_to}")
            return response

        return Response(
            {"message": "Enterprise SSO sign-in is not configured in this environment."},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
