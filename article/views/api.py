# DRF 文章/分类/评论 REST API ViewSets
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from ..models import Article, Category, Comment
from ..serializers import ArticleSerializer, CategorySerializer, CommentSerializer


# 1. 文章 API 视图（支持增删改查、过滤、排序）
class ArticleViewSet(viewsets.ModelViewSet):
    """
    博客文章 API：
    - GET: 查看文章列表/详情（所有人可看）
    - POST/PUT/DELETE: 增删改文章（仅登录用户）
    """

    queryset = Article.objects.all().select_related("author", "category").prefetch_related("tags").order_by("-created_time")
    serializer_class = ArticleSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    # 过滤：按分类、标签、作者过滤
    filterset_fields = ["category", "tags", "author"]
    # 搜索：按标题、内容搜索
    search_fields = ["title", "summary", "content", "author__username", "tags__name"]
    # 排序：按创建时间、阅读量排序
    ordering_fields = ["created_time", "read_count"]
    # DRF 权限控制，实现"只读公开，修改需登录"
    permission_classes = [IsAuthenticatedOrReadOnly]


# 2. 分类 API 视图
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


# 3. 评论 API 视图
class CommentViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all().select_related("user", "article", "parent").order_by("-created_time")
    serializer_class = CommentSerializer
    filterset_fields = ["article", "parent"]  # 按文章、父评论过滤
