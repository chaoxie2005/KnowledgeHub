import logging
import time
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class RequestLogMiddleware:
    """
    请求日志中间件
    
    功能：
    1. 记录所有HTTP请求的详细信息
    2. 计算请求处理时间
    3. 根据状态码选择适当的日志级别
    4. 记录客户端IP地址和请求路径
    
    日志格式：
    [INFO/WARNING/ERROR] METHOD PATH | IP: xxx.xxx.xxx.xxx | Status: xxx | Time: xxxms
    """
    
    def __init__(self, get_response):
        """
        初始化中间件
        
        Args:
            get_response: Django的响应处理函数
        """
        self.get_response = get_response
    
    def __call__(self, request):
        """
        处理请求并记录日志
        
        Args:
            request: Django请求对象
            
        Returns:
            HttpResponse: Django响应对象
        """
        # 记录请求开始时间
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        path = request.path
        ip = self.get_client_ip(request)
        
        # 处理请求
        response = self.get_response(request)
        
        # 计算处理时间（毫秒）
        end_time = time.time()
        processing_time = round((end_time - start_time) * 1000, 2)
        
        # 获取响应状态码
        status_code = response.status_code
        
        # 构造日志消息
        log_message = f"{method} {path} | IP: {ip} | Status: {status_code} | Time: {processing_time}ms"
        
        # 根据状态码选择日志级别
        if 400 <= status_code < 500:
            logger.warning(log_message)  # 客户端错误用warning
        elif status_code >= 500:
            logger.error(log_message)  # 服务器错误用error
        else:
            logger.info(log_message)  # 正常请求用info
        
        return response
    
    def get_client_ip(self, request):
        """
        获取客户端真实IP地址
        
        处理X-Forwarded-For和REMOTE_ADDR头，确保获取真实IP
        
        Args:
            request: Django请求对象
            
        Returns:
            str: 客户端IP地址
        """
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                # 处理代理情况，取第一个IP
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                # 直接从REMOTE_ADDR获取
                ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
            return ip
        except Exception:
            # 异常情况下返回默认值
            return '127.0.0.1'
