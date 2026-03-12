from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserProfile(models.Model):
    """用户扩展信息：头像、昵称、简介、手机号等"""
    USER_GENDER_TYPE = (
        ('male', '男'), # 第一个值是实际存储值，第二个是友好显示名
        ('female', '女')
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='关联用户')
    nickname = models.CharField(max_length=50, blank=True, null=True, verbose_name='昵称')
    gender = models.CharField(verbose_name="性别", max_length=6, choices=USER_GENDER_TYPE, default="male")
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/%d",  # 头像上传路径：media/avatars/年/月/日/
        blank=True,
        null=True,
        verbose_name="头像",
        help_text="建议上传正方形图片，大小不超过2MB",
    )
    phone = models.CharField(max_length=11, blank=True, null=True, verbose_name='手机号')
    email = models.CharField(max_length=11, blank=True, null=True, verbose_name='邮箱')
    bio = models.TextField(max_length=500, blank=True, null=True, verbose_name='个人简介')

    # 统计类字段
    article_count = models.IntegerField(default=0, verbose_name="发布文章数")
    follow_count = models.IntegerField(default=0, verbose_name="关注数")
    fans_count = models.IntegerField(default=0, verbose_name="粉丝数")

    # 时间字段
    created_at = models.DateTimeField(default=timezone.now, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "用户个人信息"
        verbose_name_plural = "用户个人信息"
        db_table = "user_profile"  # 数据库表名（可选，默认是 app名_userprofile）

    def __str__(self):
        return self.nickname or self.user.username  # 优先显示昵称，否则显示用户名
