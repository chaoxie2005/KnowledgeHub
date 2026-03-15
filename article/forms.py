from django import forms
from .models import Comment


class CommentForm(forms.ModelForm):
    """评论表单"""
    class Meta:
        model = Comment
        fields = ["content", "parent"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "写下你的看法...",
                    "style": "resize: none;",
                }
            ),
            "parent": forms.HiddenInput(),  # 隐藏父评论ID，用于回复
        }
        labels = {"content": ""}  # 隐藏标签名

    def clean_content(self):
        """验证评论内容"""
        content = self.cleaned_data.get("content")
        if not content or content.strip() == "":
            raise forms.ValidationError("评论内容不能为空！")
        return content
