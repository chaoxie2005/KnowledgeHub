import gzip
from io import BytesIO
from django.http import HttpResponse


class GzipMiddleware:
    """
    Gzip压缩中间件
    
    功能：
    1. 对响应内容进行Gzip压缩，提高传输速度
    2. 减少带宽使用，提升网站性能
    3. 智能判断是否需要压缩（根据内容类型和大小）
    4. 只对支持Gzip的客户端进行压缩
    
    压缩条件：
    - 客户端支持Gzip（通过Accept-Encoding头判断）
    - 响应未被压缩
    - 内容类型适合压缩（文本类内容）
    - 内容大小大于1KB（避免小文件压缩反而增大）
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
        处理请求并对响应进行压缩
        
        Args:
            request: Django请求对象
            
        Returns:
            HttpResponse: Django响应对象
        """
        # 检查客户端是否支持Gzip
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        if 'gzip' not in accept_encoding.lower():
            # 客户端不支持Gzip，直接返回原响应
            return self.get_response(request)
        
        # 处理请求
        response = self.get_response(request)
        
        # 检查响应是否已经被压缩
        if response.has_header('Content-Encoding'):
            # 响应已被压缩，直接返回
            return response

        # 检查响应内容类型是否适合压缩
        content_type = response.get('Content-Type', '')
        if not any(content_type.startswith(ct) for ct in [
            'text/',  # 文本类型
            'application/json',  # JSON
            'application/javascript',  # JavaScript
            'application/xml'  # XML
        ]):
            # 内容类型不适合压缩，直接返回
            return response

        # 检查是否是流式响应（StreamingHttpResponse）
        if hasattr(response, 'streaming_content'):
            # 流式响应不压缩，避免破坏流式传输
            return response

        # 检查响应内容长度
        content = response.content
        if len(content) < 1024:  # 小于1KB的内容不压缩
            # 小文件压缩可能反而增大，直接返回
            return response

        # 压缩内容
        gzip_buffer = BytesIO()
        with gzip.GzipFile(mode='w', fileobj=gzip_buffer) as f:
            f.write(content)

        # 替换响应内容
        gzip_content = gzip_buffer.getvalue()
        response.content = gzip_content

        # 更新响应头
        response['Content-Encoding'] = 'gzip'  # 标记为Gzip压缩
        response['Content-Length'] = str(len(gzip_content))  # 更新内容长度

        return response
