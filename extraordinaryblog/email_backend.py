import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


class CustomEmailBackend(SMTPEmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 创建一个自定义的 SSL 上下文
        # "ALL" 表示接受所有支持的加密套件
        # "@SECLEVEL=1" 将安全级别从默认的 2 降至 1
        # 这允许使用一些被新标准认为不够安全但仍被广泛使用的加密算法
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.set_ciphers("ALL:@SECLEVEL=1")
        self.ssl_context.check_hostname = False # 告诉它不要检查服务器的域名是否与证书上的名称匹配。
        self.ssl_context.verify_mode = (
            ssl.CERT_NONE
        )  # 告诉它完全不要验证证书本身。CERT_NONE 意味着不进行任何证书验证。
