from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from article.views import ArticleViewSet, CategoryViewSet, CommentViewSet
from rest_framework_simplejwt.views import (
    TokenObtainPairView,  # 获取 access_token + refresh_token
    TokenRefreshView,  # 用 refresh_token 刷新 access_token
)

# 1. 注册 DRF 路由
router = DefaultRouter()
router.register(r"articles", ArticleViewSet)  # 文章 API
router.register(r"categories", CategoryViewSet)  # 分类 API
router.register(r"comments", CommentViewSet)  # 评论 API

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("authentication/", include("authentication.urls")),  # 登录模块
    path("article/", include("article.urls")),  # 文章模块
    path("users/", include("users.urls")),  # 用户个人信息模块
    # 2. DRF API 根路由
    path("api/", include(router.urls)),
    # 3. DRF 可视化 API 文档（可选，超实用）
    # 4. DRF 登录/注销（用于 API 页面登录）
    path("api-auth/", include("rest_framework.urls")),
    # JWT令牌接口
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]


urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
