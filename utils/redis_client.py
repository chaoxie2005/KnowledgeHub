import redis
from django.conf import settings


# 单例模式：整个项目只创建一个 Redis 连接，避免频繁创建连接耗资源
class RedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            # 读取 settings 中的 Redis 配置
            cls._instance = redis.Redis(**settings.REDIS_CONFIG)
        return cls._instance


# 创建全局可用的 Redis 客户端对象，其他文件直接导入即可使用
redis_client = RedisClient()
