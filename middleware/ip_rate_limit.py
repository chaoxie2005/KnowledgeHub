import logging
from django.http import JsonResponse
from django.conf import settings
from django.core.cache import cache
import time

logger = logging.getLogger(__name__)


def get_client_ip(request):
    try:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        if not ip or ip == '127.0.0.1':
            ip = request.META.get('HTTP_X_REAL_IP', '127.0.0.1')
        return ip.split(',')[0].strip() if ',' in ip else ip
    except Exception:
        return '127.0.0.1'


class IPRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._load_config()

    def _load_config(self):
        self.enabled = getattr(settings, 'IP_RATE_LIMIT_ENABLED', True)
        self.max_requests = getattr(settings, 'IP_RATE_LIMIT_MAX_REQUESTS', 30)
        self.window_seconds = getattr(settings, 'IP_RATE_LIMIT_WINDOW', 60)
        self.exclude_paths = getattr(settings, 'IP_RATE_LIMIT_EXCLUDE_PATHS', [
            '/static/',
            '/media/',
            '/admin/',
        ])
        self.exclude_ips = getattr(settings, 'IP_RATE_LIMIT_EXCLUDE_IPS', [])

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        try:
            ip = get_client_ip(request)
            if not ip:
                return self.get_response(request)

            if ip in self.exclude_ips:
                return self.get_response(request)

            for exclude_path in self.exclude_paths:
                if request.path.startswith(exclude_path):
                    return self.get_response(request)

            key = f'ip_rate:{ip}'
            now = time.time()
            window_start = now - self.window_seconds

            try:
                redis_conn = cache.client.get_client()
                if redis_conn:
                    pipe = redis_conn.pipeline()
                    pipe.zremrangebyscore(key, 0, window_start)
                    pipe.zcard(key)
                    pipe.zadd(key, {str(now): now})
                    pipe.expire(key, self.window_seconds + 1)
                    results = pipe.execute()
                    request_count = results[1]
                else:
                    request_count = self._fallback_count(key)
            except Exception as e:
                logger.warning(f"IP限流Redis操作失败，降级处理: {e}")
                request_count = self._fallback_count(key)

            if request_count >= self.max_requests:
                logger.warning(
                    f"IP限流触发 | IP: {ip} | 路径: {request.path} | "
                    f"请求数: {request_count} | 限制: {self.max_requests}"
                )
                response = JsonResponse({
                    'code': 429,
                    'msg': '访问过于频繁，请稍后再试',
                    'retry_after': self.window_seconds
                }, status=429)
                response['Content-Type'] = 'application/json'
                return response

            request.ip_request_count = request_count + 1
            return self.get_response(request)

        except Exception as e:
            logger.error(f"IP限流中间件异常: {e}")
            return self.get_response(request)

    def _fallback_count(self, key):
        count = cache.get(key, 0)
        cache.set(key, count + 1, self.window_seconds)
        return count
