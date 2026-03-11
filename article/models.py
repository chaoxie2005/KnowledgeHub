from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    """分类模型(一对一：一篇文章对应一个分类)"""
    name = models.CharField(max_length=50, verbose_name='分类名称')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '分类'
        verbose_name_plural = '分类'
        ordering = ['-created_time'] # 按创建时间排序
 
    def __str__(self):
        return self.name # 后台显示分类名称


class Tag(models.Model):
    """标签模型(多对多：一篇文章对应多个标签)"""
    name = models.CharField(max_length=50, verbose_name="分类名称")
    created_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        ordering = ['-created_time']
    
    def __str__(self):
        return self.name


class Article(models.Model):
    """文章模型"""
    # 文章状态选项（草稿/已发布/回收站）
    STATUS_CHOICES = (
        ("draft", "草稿"),
        ("published", "已发布"),
        ("recycle", "回收站"),
    )

    # 基础字段
    title = models.CharField(max_length=200, verbose_name='文章标题')
    summary = models.CharField(max_length=200, blank=True, null=True, verbose_name='文章摘要')
    content = models.TextField(verbose_name='文章内容') # 富文本/Markdown内容
    cover = models.ImageField(upload_to='article/cover/', blank=True, null=True, verbose_name='封面图')

    # 关联字段
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='作者') # 关联用户，用户删除则文章删除
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='分类') # 分类删除则置空
    tags = models.ManyToManyField(Tag, blank=True, verbose_name='标签') # 多对多，可选

    # 状态/统计字段
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='文章状态')
    read_count = models.PositiveBigIntegerField(default=0, verbose_name='阅读量')
    is_top = models.BooleanField(default=False, verbose_name='是否置顶')

    # 时间字段
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    published_time = models.DateTimeField(blank=True, null=True, verbose_name='发布时间')

    class Meta:
        verbose_name = "文章"
        verbose_name_plural = "文章"
        ordering = ["-is_top", "-created_time"]  # 先按置顶、再按创建时间倒序

    def __str__(self):
        return self.title  # 后台显示文章标题
