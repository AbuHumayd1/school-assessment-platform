from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication

from candidates.models import Candidate
from institutions.models import Institution
from tenants.models import InstitutionMembership
from .registration import RegistrationSerializer


class SafeUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    is_candidate = serializers.SerializerMethodField()

    def get_is_candidate(self, user):
        return Candidate.objects.filter(user_id=user.pk).exists()


class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class CsrfTokenView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = SignInSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=HTTP_400_BAD_REQUEST)

        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Email or password is incorrect."},
                status=HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        return Response(
            {"user": SafeUserSerializer(user).data, "csrfToken": get_token(request)},
            status=HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth_register"

    def post(self, request):
        if request.user.is_authenticated:
            return Response({"detail": "Sign out before creating another account."}, status=400)
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            return Response({"email": ["An account with this email already exists."]}, status=400)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response({"user": SafeUserSerializer(user).data, "csrfToken": get_token(request)}, status=201)


class CurrentUserView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (AllowAny,)

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"authenticated": False}, status=HTTP_401_UNAUTHORIZED)
        return Response(SafeUserSerializer(request.user).data)


class WorkspaceContextView(APIView):
    """Expose only the authenticated user's active workspace relationships."""
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    workspace_roles = (
        InstitutionMembership.Role.INSTITUTION_ADMIN,
        InstitutionMembership.Role.TEACHER,
        InstitutionMembership.Role.EXAMINER,
    )

    def get(self, request):
        user = request.user
        is_platform_admin = user.is_superuser or InstitutionMembership.objects.filter(
            user=user,
            is_active=True,
            institution__is_active=True,
            role=InstitutionMembership.Role.PLATFORM_ADMIN,
        ).exists()

        if is_platform_admin:
            # Match the existing platform-admin authorization semantics: platform
            # administrators can select any active institution.
            workspaces = [
                {"institution": institution, "role": InstitutionMembership.Role.PLATFORM_ADMIN}
                for institution in Institution.objects.filter(is_active=True).order_by("name", "pk")
            ]
        else:
            workspaces = [
                {"institution": membership.institution, "role": membership.role}
                for membership in InstitutionMembership.objects.filter(
                    user=user,
                    is_active=True,
                    institution__is_active=True,
                    role__in=self.workspace_roles,
                ).select_related("institution").order_by("institution__name", "institution_id")
            ]

        return Response({
            "user": {
                "id": user.pk,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "is_platform_admin": is_platform_admin,
            "workspaces": [
                {
                    "institution": {
                        "id": item["institution"].pk,
                        "name": item["institution"].name,
                        "slug": item["institution"].slug,
                        "institution_type": item["institution"].institution_type,
                        "workspace_mode": item["institution"].workspace_mode,
                        "can_release_candidate_results": item["institution"].can_release_candidate_results,
                    },
                    "role": item["role"],
                }
                for item in workspaces
            ],
        })


class LogoutView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        logout(request)
        return Response(status=HTTP_204_NO_CONTENT)
