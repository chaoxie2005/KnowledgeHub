from django.contrib import admin
from django.contrib.auth.models import User
from .models import UserProfile
from django.contrib.auth.admin import UserAdmin

admin.site.unregister(User)


class UserProfileInline(admin.StackedInline):
    model = UserProfile  # 需要关联的模型


# 关联模型
class UserProfileAdmin(UserAdmin):
    inlines = (UserProfileInline,)  # 关联


# 关联模型
class UserProfileAdmin(UserAdmin):
    inlines = (UserProfileInline,)  # 关联

admin.site.register(User, UserProfileAdmin)
