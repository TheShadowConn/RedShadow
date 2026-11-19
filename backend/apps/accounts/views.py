from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import service as audit

from . import services, user_services
from .permissions import IsAuthenticatedSession
from .serializers import LoginSerializer, MfaCodeSerializer, PasswordChangeSerializer, me_payload
from .session import (
    RESTRICTION_MFA_SETUP,
    RESTRICTION_MFA_VERIFY,
    RESTRICTION_PASSWORD_CHANGE,
    SessionState,
)


class AnySignedIn(BasePermission):
    """Signed in, whatever restriction is pending (used by me and logout)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class CsrfView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request._request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.login(request, **serializer.validated_data)
        state = SessionState(mfa_verified=False)
        return Response(me_payload(user, state))


class LogoutView(APIView):
    permission_classes = [AnySignedIn]

    def post(self, request):
        audit.record("auth.logout", request=request)
        services.end_session(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [AnySignedIn]

    def get(self, request):
        return Response(me_payload(request.user, request.auth))


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticatedSession]
    allowed_restrictions = (RESTRICTION_PASSWORD_CHANGE, RESTRICTION_MFA_SETUP)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password"

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.change_password(request, request.user, data["current_password"], data["new_password"])
        request.user.refresh_from_db()
        state = SessionState(mfa_verified=bool(request._request.session.get("mfa_ok")))
        return Response(me_payload(request.user, state))


class MfaSetupView(APIView):
    """Enrolment is mandatory when the role requires MFA and voluntary otherwise."""

    permission_classes = [IsAuthenticatedSession]
    allowed_restrictions = (RESTRICTION_MFA_SETUP,)

    def post(self, request):
        return Response(services.begin_mfa_setup(request, request.user))


class MfaConfirmView(APIView):
    permission_classes = [IsAuthenticatedSession]
    allowed_restrictions = (RESTRICTION_MFA_SETUP,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = services.confirm_mfa_setup(request, request.user, serializer.validated_data.get("code", ""))
        return Response({"recovery_codes": codes})


class MfaVerifyView(APIView):
    permission_classes = [IsAuthenticatedSession]
    allowed_restrictions = (RESTRICTION_MFA_VERIFY,)
    requires_restriction = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"

    def post(self, request):
        serializer = MfaCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_mfa(
            request, request.user,
            serializer.validated_data.get("code"), serializer.validated_data.get("recovery_code"),
        )  # fmt: skip
        user = request.user
        state = SessionState(mfa_verified=True)
        return Response(me_payload(user, state))


class SessionsRevokeView(APIView):
    """Sign out everywhere: every session of the caller ends, this one included."""

    permission_classes = [IsAuthenticatedSession]

    def post(self, request):
        user_services.revoke_sessions(request, request.user, request.user)
        services.end_session(request)
        return Response(status=204)
