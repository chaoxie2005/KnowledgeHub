from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import UserProfile


@login_required(login_url='authentication:login')
def user_center(request):
    """用户个人中心"""
    # 直接使用 request.user，它就是当前登录的 User 对象
    user = request.user
    # 使用 get_or_create 可以更简洁地处理 UserProfile 的创建
    user_profile, created = UserProfile.objects.get_or_create(user=user)

    context = {"user": user, "user_profile": user_profile}
    return render(request, "users/user_center.html", context)
