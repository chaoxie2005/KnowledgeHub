import json
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login as login_auth
from django.contrib import messages
from .forms import RegisterForm, LoginForm
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt # 这个库可以禁用csrf保护机制，方便我们在前端通过ajax进行异步请求
from email_validator import validate_email as ValidateEmail,EmailNotValidError,EmailSyntaxError,EmailUndeliverableError


def register(request):
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
            user.save()
            return redirect(to='login')

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

    if User.objects.filter(username__iexact=username.strip()).exists():
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
    if request.method == 'GET':
        return render(request, 'authentication/login.html')
    elif request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            login_auth(request, form.user)
            messages.success(request, f'欢迎回来')
            return redirect(to='/')
    context = {
        'form': form, 
        'value': request.POST
    }
    return render(request, 'authentication/login.html', context)           