from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.http import HttpResponseForbidden

def get_client_ip(request):
    try:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip
    except:
        return '127.0.0.1'


class IPRateLimitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        try:
            # 不限制静态文件和后台
            if request.path.startswith('/static/') or request.path.startswith('/media/'):
                return None
            if request.path.startswith('/admin/'):
                return None

            ip = get_client_ip(request)
            key = f'ip_limit:{ip}'

            count = cache.get(key, 0)
            if count >= 30:
                return HttpResponseForbidden("访问过于频繁")

            cache.set(key, count + 1, 60)
            return None

        except Exception as e:
            # 出错也直接放行，绝对不报错
            return None