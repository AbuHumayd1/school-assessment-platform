from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication

from candidates.models import Candidate


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


class CurrentUserView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (AllowAny,)

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"authenticated": False}, status=HTTP_401_UNAUTHORIZED)
        return Response(SafeUserSerializer(request.user).data)


class LogoutView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        logout(request)
        return Response(status=HTTP_204_NO_CONTENT)
