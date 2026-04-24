from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Embed user claims in the JWT so the frontend can decode them directly.

    Avoids a separate /me endpoint — username, email, and role are
    available client-side immediately after login without an extra request.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        return token
