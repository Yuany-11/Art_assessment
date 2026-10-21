"""认证接口 AUTH-01 ~ AUTH-07。"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from common.permissions import IsAuthenticatedActive
from common.response import success
from common.schema import api_response

from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    LogoutResultSerializer,
    LogoutSerializer,
    MenuItemSerializer,
    PasswordChangeResultSerializer,
    PasswordChangeSerializer,
    ProfileUpdateSerializer,
    RefreshSerializer,
    TokenPairSerializer,
    UserProfileSerializer,
)
from .services.auth import (
    change_password,
    login,
    logout,
    refresh,
    update_profile,
)
from .services.menu import build_menu_tree

TOKEN_KEYS = ("token", "refreshToken", "tokenType", "expiresIn", "refreshExpiresIn")


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-01 用户登录",
        request=LoginSerializer,
        responses={200: api_response("ApiLoginResponse", LoginResponseSerializer())},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = login(data["username"], data["password"], data.get("role"))
        payload = {key: result[key] for key in TOKEN_KEYS}
        payload["user"] = UserProfileSerializer(result["user"]).data
        return success(payload)


class RefreshView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-02 刷新访问令牌",
        request=RefreshSerializer,
        responses={200: api_response("ApiRefreshResponse", TokenPairSerializer())},
    )
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success(refresh(serializer.validated_data["refreshToken"]))


class LogoutView(APIView):
    permission_classes = [IsAuthenticatedActive]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-03 退出登录",
        request=LogoutSerializer,
        responses={200: api_response("ApiLogoutResponse", LogoutResultSerializer())},
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success(logout(request.auth, serializer.validated_data.get("refreshToken")))


class MeView(APIView):
    permission_classes = [IsAuthenticatedActive]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-04 获取当前用户信息",
        responses={200: api_response("ApiUserProfileResponse", UserProfileSerializer())},
    )
    def get(self, request):
        return success(UserProfileSerializer(request.user).data)

    @extend_schema(
        tags=["认证"],
        summary="AUTH-05 修改个人信息",
        request=ProfileUpdateSerializer,
        responses={200: api_response("ApiUserProfileUpdateResponse", UserProfileSerializer())},
    )
    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_profile(request.user, serializer.validated_data)
        return success(UserProfileSerializer(user).data)


class PasswordView(APIView):
    permission_classes = [IsAuthenticatedActive]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-06 修改本人密码",
        request=PasswordChangeSerializer,
        responses={200: api_response("ApiPasswordChangeResponse", PasswordChangeResultSerializer())},
    )
    def patch(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success(
            change_password(
                request.user,
                serializer.validated_data["oldPassword"],
                serializer.validated_data["newPassword"],
            )
        )


class MenusView(APIView):
    permission_classes = [IsAuthenticatedActive]

    @extend_schema(
        tags=["认证"],
        summary="AUTH-07 查询当前角色菜单",
        responses={200: api_response("ApiMenuListResponse", MenuItemSerializer(many=True))},
    )
    def get(self, request):
        tree = build_menu_tree(request.user.role)
        return success(MenuItemSerializer(tree, many=True).data)
