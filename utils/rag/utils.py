# RAG 工具函数：UTC→北京时间格式化、作者显示名称解析
from datetime import datetime
import pytz


def _format_time(utc_time):
    """
    将UTC时间格式化为北京时间字符串

    Args:
        utc_time: UTC时间（字符串或datetime对象）

    Returns:
        str: 格式化后的北京时间字符串，格式为"YYYY年MM月DD日 HH:MM"
    """
    if not utc_time:
        return "未知"
    try:
        local_tz = pytz.timezone('Asia/Shanghai')
        if isinstance(utc_time, str):
            utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
        if utc_time.tzinfo is None:
            utc_time = pytz.UTC.localize(utc_time)
        local_time = utc_time.astimezone(local_tz)
        return local_time.strftime('%Y年%m月%d日 %H:%M')
    except Exception:
        return str(utc_time)


def get_author_display_name(author):
    """获取作者显示名称，优先使用 profile.nickname，其次是 username。

    支持两种类型：
    - Django Model 对象（有 author.profile.nickname 属性）
    - dict（来自 .values() 查询，有 author__profile__nickname 键）
    """
    # Model 对象
    if hasattr(author, 'profile') and hasattr(author.profile, 'nickname') and author.profile.nickname:
        return author.profile.nickname
    if hasattr(author, 'username'):
        return author.username

    # dict 对象（来自 .values() 查询）
    if isinstance(author, dict):
        nickname = author.get('author__profile__nickname')
        username = author.get('author__username')
        return nickname or username or '未知'

    return '未知'
