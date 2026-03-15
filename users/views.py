from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.utils.text import gettext_lazy as _
from .models import UserProfile
from django.contrib.auth.models import User


@login_required(login_url='authentication:login')
def user_center(request):
    """用户个人中心"""
    # 直接使用 request.user，它就是当前登录的 User 对象
    user = request.user
    # 使用 get_or_create 可以更简洁地处理 UserProfile 的创建
    user_profile, created = UserProfile.objects.get_or_create(user=user)

    context = {"user": user, "user_profile": user_profile}
    return render(request, "users/user_center.html", context)


# 登录保护：未登录用户无法访问
@login_required(login_url="authentication:login")
def edit_user(request):
    """编辑用户信息"""
    # 确保当前用户有对应的UserProfile（无则创建）
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == "GET":
        # GET请求：传递用户现有数据到模板
        context = {
            "profile": profile,
            "gender_choices": UserProfile.USER_GENDER_TYPE,  # 性别选项
        }
        return render(request, "users/edit_user.html", context)

    elif request.method == "POST":
        try:
            # ========== 1. 提取并校验表单数据 ==========
            # 基础信息
            nickname = request.POST.get("nickname", "").strip()
            gender = request.POST.get("gender", "unknown")
            phone = request.POST.get("phone", "").strip()
            email = request.POST.get("email", "").strip()
            bio = request.POST.get("bio", "").strip()

            # 地址信息
            address = request.POST.get("address", "").strip()
            city = request.POST.get("city", "").strip()
            state = request.POST.get("state", "").strip()

            # 头像文件（注意是FILES不是File）
            avatar_file = request.FILES.get("avatar")

            # ========== 2. 数据校验（和模型validators逻辑一致） ==========
            # 昵称校验
            if nickname:
                import re

                if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$", nickname):
                    raise ValidationError(_("昵称只能包含中文、字母、数字和下划线"))
                if len(nickname) > 50:
                    raise ValidationError(_("昵称不能超过50个字符"))

            # 性别校验
            if gender not in [choice[0] for choice in UserProfile.USER_GENDER_TYPE]:
                raise ValidationError(_("性别选择无效"))

            # 手机号校验
            if phone:
                if not re.match(r"^1[3-9]\d{9}$", phone):
                    raise ValidationError(_("请输入有效的11位手机号"))

            # 邮箱校验
            if email:
                from django.core.validators import validate_email

                validate_email(email)  # Django内置邮箱校验

            # 个人简介校验
            if bio:
                if not re.match(r"^[^<>{}$]*$", bio):
                    raise ValidationError(_("个人简介不能包含特殊字符"))
                if len(bio) > 500:
                    raise ValidationError(_("个人简介不能超过500个字符"))

            # 头像文件校验
            if avatar_file:
                # 校验文件类型
                allowed_extensions = ["jpg", "jpeg", "png", "webp"]
                file_ext = avatar_file.name.split(".")[-1].lower()
                if file_ext not in allowed_extensions:
                    raise ValidationError(_("头像仅支持jpg/jpeg/png/webp格式"))

                # 校验文件大小（2MB）
                max_size = 2 * 1024 * 1024
                if avatar_file.size > max_size:
                    raise ValidationError(_("头像大小不能超过2MB"))

            # ========== 3. 赋值并保存数据 ==========
            # 基础信息赋值
            if nickname:
                profile.nickname = nickname
            profile.gender = gender
            if phone:
                profile.phone = phone
            if email:
                profile.email = email
                # 可选：同步更新User模型的邮箱
                request.user.email = email
                request.user.save()
            if bio:
                profile.bio = bio

            # 地址信息赋值
            if address:
                profile.address = address
            if city:
                profile.city = city
            if state:
                profile.state = state

            # 头像赋值（有上传文件才更新）
            if avatar_file:
                profile.avatar = avatar_file

            # 保存Profile（触发模型的auto_now更新时间）
            profile.save()

            # ========== 4. 提示并跳转 ==========
            messages.success(request, "信息修改成功！")
            return redirect("users:user_center")  # 成功时直接返回跳转

        # ========== 异常处理 ==========
        except ValidationError as e:
            # 数据校验失败
            messages.error(request, f"修改失败：{e.message}")
        except Exception as e:
            # 其他未知错误（如数据库错误）
            messages.error(request, f"系统错误：{str(e)}")

        # ========== 关键修复：只有失败时才执行以下逻辑 ==========
        # 校验失败：返回原页面并携带用户已填数据（而不是直接跳转）
        context = {
            "profile": profile,
            "gender_choices": UserProfile.USER_GENDER_TYPE,
            "post_data": request.POST,  # 保留用户已填数据，提升体验
        }
        return render(request, "users/edit_user.html", context)  # 失败时返回编辑页


@login_required(login_url="authentication:login")
def user_center(request, user_id=None):
    """用户个人中心：支持查看自己或他人"""
    if user_id:
        # 查看他人个人中心
        user = get_object_or_404(User, id=user_id)
    else:
        # 查看自己的个人中心
        user = request.user

    user_profile, created = UserProfile.objects.get_or_create(user=user)
    context = {"user": user, "user_profile": user_profile}
    return render(request, "users/user_center.html", context)


def user_detail(request, user_id):
    """用户个人中心"""
    user = get_object_or_404(User, id=user_id)
    user_profile, created = UserProfile.objects.get_or_create(user=user)

    context = {"user": user, "user_profile": user_profile}
    return render(request, 'users/user_detail.html', context)
