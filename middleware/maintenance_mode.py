from django.http import HttpResponse
from django.conf import settings


class MaintenanceModeMiddleware:
    """
    维护模式中间件
    
    功能：
    1. 在网站维护时显示友好的维护页面
    2. 允许管理员正常访问网站
    3. 提供清晰的维护信息给用户
    4. 返回适当的HTTP状态码（503 Service Unavailable）
    
    配置：
    - 在settings.py中设置MAINTENANCE_MODE = True启用维护模式
    - 设置为False或不设置则禁用维护模式
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
        处理请求并检查维护模式
        
        Args:
            request: Django请求对象
            
        Returns:
            HttpResponse: Django响应对象
        """
        # 检查是否启用维护模式
        maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)
        if not maintenance_mode:
            # 维护模式未启用，正常处理请求
            return self.get_response(request)
        
        # 允许管理员访问（即使在维护模式下）
        if hasattr(request, 'user') and request.user.is_staff:
            # 管理员可以正常访问网站
            return self.get_response(request)
        
        # 显示维护页面
        html_content = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>网站维护中</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background-color: #f5f5f5;
                }
                .maintenance-container {
                    text-align: center;
                    background-color: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                    max-width: 500px;
                }
                h1 {
                    color: #333;
                    margin-bottom: 20px;
                }
                p {
                    color: #666;
                    margin-bottom: 30px;
                }
                .logo {
                    font-size: 48px;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="maintenance-container">
                <div class="logo">🔧</div>
                <h1>网站维护中</h1>
                <p>我们正在对网站进行维护和升级，敬请谅解。</p>
                <p>预计很快恢复正常访问。</p>
            </div>
        </body>
        </html>
        """
        
        # 返回503状态码，表示服务暂时不可用
        return HttpResponse(html_content, status=503)
