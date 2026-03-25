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

        # 优化：给分类名称加唯一索引，避免重复创建相同分类
        indexes = [
            models.Index(fields=['name'], name='idx_category_name'),
        ]
        unique_together = [['name']]  # 分类名称唯一

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

        # 优化：标签名称唯一索引，避免重复
        indexes = [
            models.Index(fields=["name"], name="idx_tag_name"),
        ]
        unique_together = [["name"]]

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
    summary = models.CharField(max_length=500, blank=True, null=True, verbose_name='文章摘要')
    content = models.TextField(verbose_name='文章内容') # 富文本/Markdown内容
    cover = models.ImageField(
        upload_to="article/cover/",
        blank=True,
        null=True,
        verbose_name="封面图",
        default="avatars/default_cover.png",
    )

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

        indexes = [
            # 原：idx_article_category_status_top_time → 新：idx_art_cat_stat_top_time
            models.Index(
                fields=["category", "status", "-is_top", "-created_time"],
                name="idx_art_cat_stat_top_time",
            ),
            # 原：idx_article_author_status_time → 新：idx_art_auth_stat_time
            models.Index(
                fields=["author", "status", "-created_time"],
                name="idx_art_auth_stat_time",
            ),
            # 原：idx_article_status_top_pubtime → 新：idx_art_stat_top_pub
            models.Index(
                fields=["status", "-is_top", "-published_time"],
                name="idx_art_stat_top_pub",
            ),
            # 原：idx_article_status_readcount → 新：idx_art_stat_readcnt
            models.Index(fields=["status", "-read_count"], name="idx_art_stat_readcnt"),
            # 原：idx_article_pubtime → 新：idx_art_pub_time
            models.Index(fields=["-published_time"], name="idx_art_pub_time"),
        ]

    def __str__(self):
        return self.title  # 后台显示文章标题


# ========== 新增：评论/点赞相关模型 ==========
class Comment(models.Model):
    """评论模型（支持嵌套回复，对标掘金）"""
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='comments', verbose_name="关联文章")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments', verbose_name='评论用户')
    content = models.TextField(max_length=500, verbose_name="评论内容", help_text="最多500字")

    # 父评论（用于回复：null表示一级评论，非null表示回复）
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name='replies', verbose_name='父评论')

    # 时间字段
    created_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "评论"
        verbose_name_plural = "评论"
        ordering = ["-created_time"]  # 最新评论在前
        indexes = [
            # 原：idx_comment_article_parent_time → 新：idx_cmt_art_par_time
            models.Index(
                fields=["article", "parent", "-created_time"],
                name="idx_cmt_art_par_time",
            ),
            # 原：idx_comment_user_time → 新：idx_cmt_user_time
            models.Index(fields=["user", "-created_time"], name="idx_cmt_user_time"),
            # 原：idx_comment_parent_time → 新：idx_cmt_par_time
            models.Index(fields=["parent", "-created_time"], name="idx_cmt_par_time"),
        ]

    def __str__(self):
        return (
            f"{self.user.username} 评论《{self.article.title}》：{self.content[:20]}..."
        )

    @property
    def is_root(self):
        """判断是否是一级评论"""
        return self.parent is None

    @property
    def like_count(self):
        """获取评论点赞数"""
        return self.comment_likes.count()


class CommentLike(models.Model):
    """评论点赞模型（防止重复点赞）"""

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="comment_likes",
        verbose_name="关联评论",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_likes",
        verbose_name="点赞用户",
    )
    created_time = models.DateTimeField(auto_now_add=True, verbose_name="点赞时间")

    class Meta:
        verbose_name = "评论点赞"
        verbose_name_plural = "评论点赞"
        unique_together = ["comment", "user"]  # 一个用户只能给一个评论点一次赞

    def __str__(self):
        return f"{self.user.username} 点赞了 {self.comment.id} 号评论"


class JuejinHotArticle(models.Model):
    """掘金热榜文章模型（爬虫专用）"""
    # 掘金唯一标识（核心去重字段）
    juejin_article_id = models.CharField(
        max_length=50, unique=True, verbose_name="掘金文章ID"
    )
    # 核心信息
    title = models.CharField(max_length=200, verbose_name="文章标题")
    summary = models.CharField(
        max_length=1000, blank=True, null=True, verbose_name="文章摘要"
    )
    ai_summary = models.TextField(blank=True, verbose_name="AI 摘要") 
    original_url = models.URLField(max_length=500, verbose_name="掘金原文链接")
    author = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="掘金作者"
    )
    source = models.CharField(max_length=50, blank=True, null=True, verbose_name='文章来源')
    # 扩展信息
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="标签")
    published_time = models.DateTimeField(
        blank=True, null=True, verbose_name="掘金发布时间"
    )
    crawl_time = models.DateTimeField(
        auto_now_add=True, verbose_name="爬取时间"
    )  # 记录爬取时间

    class Meta:
        verbose_name = "掘金热榜文章"
        verbose_name_plural = "掘金热榜文章"
        ordering = ["-crawl_time"]  # 按爬取时间倒序

        # ========== 索引优化 ==========
        indexes = [
            # 1. 核心：按爬取时间排序（热榜展示）
            models.Index(fields=["-crawl_time"], name="idx_juejin_crawl_time"),
            # 2. 优化：按掘金发布时间筛选
            models.Index(fields=["-published_time"], name="idx_juejin_pub_time"),
            # 3. 优化：按作者/来源查询
            models.Index(fields=["author"], name="idx_juejin_author"),
            models.Index(fields=["source"], name="idx_juejin_source"),
        ]

    def __str__(self):
        return f"{self.title} ({self.juejin_article_id})"
