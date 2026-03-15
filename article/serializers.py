# article/serializers.py
from rest_framework import serializers
from .models import Article, Category, Tag, Comment
from django.contrib.auth.models import User


# 1. 用户序列化器（返回简单用户信息）
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


# 2. 分类序列化器
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "created_time"]


# 3. 标签序列化器
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


# 4. 评论序列化器
class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)  # 嵌套用户信息
    created_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "content", "created_time", "parent"]
        read_only_fields = ["author"]  # 作者自动关联登录用户，不允许手动改

    def create(self, validated_data):
        # 自动把评论作者设为当前登录用户
        validated_data["author"] = self.context["request"].user
        return super().create(validated_data)


# 5. 文章序列化器（核心）
class ArticleSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)  # 嵌套作者信息
    category = CategorySerializer(read_only=True)  # 嵌套分类
    tags = TagSerializer(many=True, read_only=True)  # 嵌套标签（多对多）
    created_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "content",
            "cover",
            "author",
            "category",
            "tags",
            "created_time",
            "read_count",
        ]
        read_only_fields = ["author", "read_count"]  # 作者、阅读量自动生成

    def create(self, validated_data):
        # 自动把文章作者设为当前登录用户
        validated_data["author"] = self.context["request"].user
        return super().create(validated_data)
