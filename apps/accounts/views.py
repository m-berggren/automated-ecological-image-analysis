from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import datetime
from django.http import JsonResponse


# Create your views here.

# Login view
@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(
        username=request.data.get("username"),
        password=request.data.get("password")
    )

    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
    return Response({"error": "Invalid credentials"}, status=401)



# Registration view
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get("username")
    password = request.data.get("password")
    email = request.data.get("email")

    if User.objects.filter(username=username).exists():
        return Response({"error": "User exists"}, status=400)

    if not email:
        return Response({"error": "Email required"}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({"error": "email exists"}, status=400)


    user = User.objects.create_user(username=username, password=password, email=email)
    token = Token.objects.create(user=user)

    return Response({"token": token.key})


# Authetication check view
@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({
        "user": {
            "username": request.user.username
        }
    })


# Logout view
@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def logout(request):
    request.user.auth_token.delete()
    return Response({"success": "Logged out"})