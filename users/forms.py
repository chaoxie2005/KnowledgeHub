from django import forms
from .models import UserProfile
import re

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'nickname', 'gender', 'phone', 'email',
            'bio', 'address', 'city', 'state', 'avatar'
        ]
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}, choices=UserProfile.USER_GENDER_TYPE),
        }

    # 手机号校验
    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            if not re.match(r'^1[3-9]\d{9}$', phone):
                raise forms.ValidationError("请输入有效的11位手机号")
        return phone

    # 昵称校验
    def clean_nickname(self):
        nickname = self.cleaned_data.get('nickname', '').strip()
        if nickname:
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', nickname):
                raise forms.ValidationError("昵称只能包含中文、字母、数字和下划线")
            if len(nickname) > 50:
                raise forms.ValidationError("昵称不能超过50个字符")
        return nickname

    # 简介校验
    def clean_bio(self):
        bio = self.cleaned_data.get('bio', '').strip()
        if len(bio) > 500:
            raise forms.ValidationError("个人简介最多500字")
        return bio