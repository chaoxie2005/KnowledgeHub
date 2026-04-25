from django.http import HttpResponse


class CORSMiddleware:
    """
    CORS（跨域资源共享）中间件
    
    功能：
    1. 处理跨域请求，设置适当的CORS头
    2. 支持预检请求（OPTIONS方法）
    3. 允许跨域资源访问
    4. 缓存预检请求结果，减少重复请求
    
    注意：
    - 生产环境应将Access-Control-Allow-Origin设置为具体域名
    - 当前配置允许所有源访问，适合开发环境
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
        处理请求并设置CORS头
        
        Args:
            request: Django请求对象
            
        Returns:
            HttpResponse: Django响应对象
        """
        # 处理预检请求（OPTIONS方法）
        if request.method == 'OPTIONS':
            # 对于预检请求，直接返回空响应
            response = HttpResponse()
        else:
            # 处理正常请求
            response = self.get_response(request)
        
        # 设置CORS头
        response['Access-Control-Allow-Origin'] = '*'  # 允许所有源，生产环境应设置为具体域名
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'  # 允许的HTTP方法
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'  # 允许的请求头
        response['Access-Control-Max-Age'] = '86400'  # 预检请求结果缓存时间（秒），24小时
        
        return response
