from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import FileExtensionValidator, RegexValidator
from django.core.exceptions import ValidationError


def validate_file_size(value):
    # 限制文件大小为 4MB（4 * 1024 * 1024 字节）
    max_size = 4 * 1024 * 1024
    if value.size > max_size:
        raise ValidationError(f"文件大小不能超过 {max_size//1024//1024}MB")


class UserProfile(models.Model):
    """用户扩展信息：头像、昵称、简介、手机号、地址等"""

    # 性别枚举
    USER_GENDER_TYPE = (
        ("male", "男"),
        ("female", "女"),
        ("unknown", "未知"),  # 补充未知选项，更符合实际场景
    )

    # 关联内置User模型（核心）
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name="关联用户"
    )

    # 基础信息字段
    nickname = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="昵称",
        help_text="最多50个字符",
        validators=[
            RegexValidator(
                regex=r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$",
                message="昵称只能包含中文、字母、数字和下划线",
            )
        ],
    )
    gender = models.CharField(
        verbose_name="性别",
        max_length=10,
        choices=USER_GENDER_TYPE,
        default="unknown",  # 默认改为未知更合理
    )
    # 头像：增加默认值，限制上传文件大小
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/%d",
        default="avatars/default_avatar.png",  # 默认头像路径（需提前在media/avatars下放默认图片）
        blank=True,
        null=True,
        verbose_name="头像",
        help_text="建议上传正方形图片，大小不超过4MB",
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
            validate_file_size,  # 用我们自定义的校验器
        ],
    )
    # 手机号：增加正则校验
    phone = models.CharField(
        max_length=11,
        blank=True,
        null=True,
        verbose_name="手机号",
        validators=[
            RegexValidator(
                regex=r"^1[3-9]\d{9}$",
                message="请输入有效的11位手机号",
                code="invalid_phone",
            )
        ],
    )
    # 邮箱
    email = models.EmailField(
        max_length=254, blank=True, null=True, verbose_name="邮箱"
    ) 
    
    
    bio = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="个人简介",
        help_text="最多500个字符",
        validators=[
            RegexValidator(regex=r"^[^<>{}$]*$", message="个人简介不能包含特殊字符")
        ],
    )

    # 地址相关字段
    address = models.CharField(
        max_length=200, blank=True, null=True, verbose_name="详细地址"
    )
    city = models.CharField(max_length=50, blank=True, null=True, verbose_name="城市")
    state = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="省份/州"
    )

    # 统计类字段（建议改为动态计算，这里先保留手动维护方式）
    article_count = models.IntegerField(default=0, verbose_name="发布文章数")
    follow_count = models.IntegerField(default=0, verbose_name="关注数")
    fans_count = models.IntegerField(default=0, verbose_name="粉丝数")

    # 时间字段
    created_at = models.DateTimeField(default=timezone.now, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "用户个人信息"
        verbose_name_plural = "用户个人信息"
        db_table = "user_profile"
        ordering = ["-updated_at"]  # 新增：按更新时间倒序排列

    def __str__(self):
        return self.nickname or self.user.username or f"用户{self.user.id}"  # 优先展示昵称
