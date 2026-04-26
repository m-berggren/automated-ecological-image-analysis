from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request) -> Response:
    """Create a new user and return a JWT access + refresh pair.

    Expects: {username, password, email}
    Returns: {access, refresh}
    """
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')

    if not username or not password:
        return Response({'error': 'Username and password required'}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({'error': 'User exists'}, status=400)

    if not email:
        return Response({'error': 'Email required'}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email exists'}, status=400)

    user = User.objects.create_user(
        username=username, password=password, email=email,
    )

    refresh = RefreshToken.for_user(user)
    # Embed the same custom claims the login serializer adds
    refresh['username'] = user.username
    refresh['email'] = user.email
    refresh['is_staff'] = user.is_staff

    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    })
