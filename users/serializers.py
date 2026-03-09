from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["user_name", "email", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "user_name",
            "email",
            "password",
            "is_active",
            "is_staff",
        ]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    two_factor_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "user_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "two_factor_enabled",
        ]
        read_only_fields = ["is_active", "is_staff", "is_superuser", "two_factor_enabled"]

    def get_two_factor_enabled(self, obj):
        return obj.requires_two_factor()


class UserAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "user_name",
            "email",
            "is_active",
            "is_staff",
        ]


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)


class ChangeMyPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, min_length=8)
    new_password = serializers.CharField(write_only=True, min_length=8)


class LoginSerializer(serializers.Serializer):
    user_name = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class LoginTwoFactorSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=6)


class LoginTwoFactorResendSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()


class TwoFactorEnableSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)


class TwoFactorDisableSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
