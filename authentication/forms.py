from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate

class RegisterForm(forms.Form):
    username = forms.CharField(
        max_length=50,
        error_messages={
            'required': '用户名不能为空',
        }
    )
    email = forms.EmailField(
        error_messages={
            'required': '邮箱不能为空',
        }
    )
    password = forms.CharField(
        min_length=6,
        max_length=20,
        error_messages={
            'required': '密码不能为空！',
            'min_length': '密码不能少于6位！',
            'max_length': '密码不能多于20位！',
        }
    )
    re_password = forms.CharField(
        min_length=6,
        max_length=20,
        error_messages={
            "required": "密码不能为空！",
            "min_length": "密码不能少于6位！",
            "max_length": "密码不能多于20位！",
        },
    )
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).first():
            self.add_error('username', '用户已存在！')
        return username
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).first():
            self.add_error('email', '邮箱已存在！')
        return email
    
    def clean_re_password(self):
        password = self.cleaned_data.get('password')
        re_password = self.cleaned_data.get('re_password')
        if password and re_password and password != re_password:
            self.add_error('re_password', '两次密码输入不一致！')
        return re_password


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=50,
        error_messages={
            "required": "用户名不能为空",
        },
    )
    password = forms.CharField(
        min_length=6,
        max_length=20, 
        error_messages={
            'required': '密码不能为空',
        }
    )

    captcha = forms.CharField(
        max_length=10, error_messages={"required": "验证码不能为空"}
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super(LoginForm, self).__init__(*args, **kwargs)

    def clean_captcha(self):
        captcha = self.cleaned_data.get("captcha").lower()
        if not self.request:
            raise forms.ValidationError("请求对象丢失，无法验证")
        verify_code = self.request.session.get("verify_code")
        if not verify_code or captcha != verify_code:
            raise forms.ValidationError("验证码错误")
        return captcha

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if password and password:
            self.user = authenticate(username=username, password=password)
            if self.user is None:
                raise forms.ValidationError("您输入的用户名或密码不正确，请重试。")
        return self.cleaned_data
