import json
from threading import Thread
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.contrib.auth.models import User
from django.contrib.auth import login as login_auth, logout as logout_auth
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm, LoginForm
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, FileResponse
from django.views.decorators.csrf import (
    csrf_exempt,
)  # 这个库可以禁用csrf保护机制，方便我们在前端通过ajax进行异步请求
from email_validator import (
    validate_email as ValidateEmail,
    EmailNotValidError,
    EmailSyntaxError,
    EmailUndeliverableError,
)
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator  
from django.contrib.sites.shortcuts import get_current_site     


def register(request):
    """注册视图"""
    if request.method == "GET":
        return render(request, "authentication/register.html")

    elif request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            email = form.cleaned_data.get("email")
            password = form.cleaned_data.get("password")
            user = User.objects.create(
                username=username,
                email=email,
            )
            user.set_password(password)
            user.is_active = False
            user.save()

            current_site = get_current_site(request)  # 动态获取域名
            content = f"""
            请点击下方链接，激活账号：
            http://{current_site}/authentication/verify_account/{user.username}
            """

            t = Thread(
                target=send_mail,
                args=[
                    "激活账号【超凡博客】",
                    content,
                    settings.EMAIL_HOST_USER,
                    [user.email],
                ],
            )
            t.start()
            return HttpResponse("请查收邮件，激活账号！")

        context = {"form": form, "values": request.POST}
        return render(request, "authentication/register.html", context)


@csrf_exempt
def validate_username(request):
    """
    验证注册时用户名
    数据格式：{'': ''}
    """
    data = json.loads(request.body)
    username = data.get("username")

    if not username.strip():
        return JsonResponse({"status": "error", "msg": "用户名为空"}, status=400)

    if not username.isalnum():
        return JsonResponse(
            {"status": "error", "msg": "用户名不合法，不能使用特殊符号"}, status=400
        )

    if User.objects.filter(username=username.strip()).exists():
        return JsonResponse({"status": "error", "msg": "用户名已存在"}, status=400)

    else:
        return JsonResponse({"status": "success", "msg": "ok"})


@csrf_exempt
def validate_email(request):
    """
    检验注册时邮箱
    数据格式：{'':''}
    """
    data = json.loads(request.body)
    email = data.get("email")

    if not email.strip():
        return JsonResponse(
            {
                "status": "error",
                "msg": "邮箱为空",
            },
            status=400,
        )

    try:
        ValidateEmail(email, check_deliverability=False)
    except EmailSyntaxError as e:
        return JsonResponse(
            {
                "status": "error",
                "msg": "邮箱格式不正确",
            },
            status=400,
        )
    except EmailUndeliverableError as e:
        return JsonResponse(
            {"status": "error", "msg": "该邮箱域名无法接收邮件"}, status=400
        )
    except EmailNotValidError as e:
        return JsonResponse(
            {
                "status": "error",
                "msg": "邮箱地址无效",
            },
            status=400,
        )

    if User.objects.filter(email=email).exists():
        return JsonResponse(
            {
                "status": "error",
                "msg": "该邮箱已被注册",
            },
            status=400,
        )
    else:
        return JsonResponse({"status": "success", "msg": "ok"})


def login(request):
    if request.method == "GET":
        return render(request, "authentication/login.html")
    elif request.method == "POST":
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            login_auth(request, form.user)
            messages.success(request, f"欢迎回来")
            return redirect(to="core:index")
        context = {"form": form, "value": request.POST}
        return render(request, "authentication/login.html", context)


def verify_account(request, username):
    """激活账号视图"""
    user = get_object_or_404(User, username=username)
    user.is_active = True
    user.save()
    messages.success(request, "账号激活成功，请登录！")
    return redirect(to="authentication:login")


def forget_password(request):
    """忘记密码视图"""
    if request.method == "GET":
        return render(request, "authentication/forget_password.html")
    elif request.method == "POST":
        email = request.POST.get("email")
        if not User.objects.filter(email=email).exists():
            context = {
                "error": "邮箱不存在",
                "email": email,
            }
            return render(request, "authentication/forget_password.html", context)

        user = User.objects.get(email=email)
        current_site = get_current_site(request)  # 动态获取域名
        token = default_token_generator.make_token(user)

        link = (
            "http://"
            + current_site.domain
            + resolve_url("authentication:reset_password", user.pk, token)
        )

        content = f"""
            请点击下方链接，找回密码：
            {link}
            """

        t = Thread(
            target=send_mail,
            args=[
                "找回密码【超凡博客】",
                content,
                settings.EMAIL_HOST_USER,
                [user.email],
            ],
        )
        t.start()
        return HttpResponse("请查收邮件，找回密码！")


def reset_password(request, pk, token):
    """重置密码视图"""
    if request.method == "GET":
        user = get_object_or_404(User, pk=pk)
        if not default_token_generator.check_token(user, token):
            return HttpResponseBadRequest("Invalid Token")

        messages.info(request, f"{user.username}，请设置你的新密码")
        return render(request, "authentication/reset_password.html")
    elif request.method == "POST":
        password = request.POST.get("password")
        re_password = request.POST.get("re_password")

        user = get_object_or_404(User, pk=pk)
        if not default_token_generator.check_token(user, token):
            return HttpResponseBadRequest("Invalid Token")

        if password and re_password and password != re_password:
            messages.error(request, "两次密码输入不一致")
            return render(request, "authentication/reset_password.html")

        if len(password) < 6:
            messages.error(request, "密码不能少于6位")
            return render(request, "authentication/reset_password.html")

        else:
            user.set_password(password)
            user.save()
            messages.success(request, "密码修改成功，请使用新密码进行登录！")
            return redirect(to="authentication:login")


def change_password(request):
    """修改密码"""
    if request.method == "GET":
        return render(request, "authentication/change_password.html")
    elif request.method == "POST":
        # 1. 取值
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        re_password = request.POST.get("re_password")

        
        if not all([old_password, new_password, re_password]):
            messages.error(request, "所有密码字段都不能为空！")
            return render(request, "authentication/change_password.html")


        if not request.user.check_password(old_password):
            messages.error(request, "旧密码错误！")
            return render(request, "authentication/change_password.html")


        if old_password == new_password:
            messages.error(request, "旧密码不能与新密码相同！")
            return render(request, "authentication/change_password.html")

        # 5. 第四步：新密码长度校验
        if len(new_password) < 6:
            messages.error(request, "密码不能少于6位")
            return render(request, "authentication/change_password.html")

        # 6. 第五步：两次新密码一致校验
        if new_password != re_password:
            messages.error(request, "两次密码输入不一致！")
            return render(request, "authentication/change_password.html")

        # 7. 所有校验通过，修改密码
        request.user.set_password(new_password)
        request.user.save()
        messages.success(request, "密码修改成功，请重新登录")
        return redirect("authentication:login")


def logout(request):
    logout_auth(request)
    messages.success(request, '退出成功！')
    return redirect(to='core:index')




from .utils import generate_verify_code


def captcha(request):
    verify_code, buff = generate_verify_code()  # 生成验证码图片和验证码字符串
    request.session["verify_code"] = (
        verify_code.lower()
    )  # 将验证码字符串存入session，方便 后续校验
    return FileResponse(
        buff, filename="verify.gif", headers={"Content-Type": "image/gif"}
    )
