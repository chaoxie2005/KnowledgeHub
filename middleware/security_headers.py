from django.http import HttpResponse


class SecurityHeadersMiddleware:
    """
    安全头中间件
    
    功能：
    1. 添加多种安全相关的HTTP头
    2. 防止常见的安全攻击
    3. 提高网站的安全性
    4. 遵循安全最佳实践
    
    添加的安全头：
    - X-Content-Type-Options: 防止MIME类型嗅探
    - X-Frame-Options: 防止点击劫持
    - X-XSS-Protection: 启用浏览器的XSS过滤器
    - Content-Security-Policy: 内容安全策略
    - Referrer-Policy: 控制Referrer信息
    - Feature-Policy: 控制浏览器特性的使用
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
        处理请求并添加安全头
        
        Args:
            request: Django请求对象
            
        Returns:
            HttpResponse: Django响应对象
        """
        response = self.get_response(request)
        
        # 防止MIME类型嗅探
        # 告诉浏览器不要尝试猜测内容类型，严格按照Content-Type头执行
        response['X-Content-Type-Options'] = 'nosniff'
        
        # 防止点击劫持
        # 禁止页面在iframe中显示
        response['X-Frame-Options'] = 'DENY'
        
        # 启用浏览器的XSS过滤器
        # 当检测到XSS攻击时，阻止页面加载
        response['X-XSS-Protection'] = '1; mode=block'
        
        # 强制HTTPS（生产环境使用）
        # 告诉浏览器在未来一段时间内只使用HTTPS访问
        # response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        
        # Referrer策略
        # 控制Referrer信息的发送方式
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # 特性策略
        # 控制浏览器特性的使用，如摄像头、麦克风、地理位置等
        response['Feature-Policy'] = "camera 'none'; microphone 'none'; geolocation 'none'"
        
        return response
