from django import forms
from .models import Article


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "content", "category", "cover"]  # 按需调整字段
        # 可添加字段样式/验证规则
        widgets = {
            "content": forms.Textarea(attrs={"class": "editor", "rows": 10}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
        }
