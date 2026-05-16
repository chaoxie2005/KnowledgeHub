# 视图装饰器：性能计时工具 time_it
import time


def time_it(func):
    """测试项目时间性能函数"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        # 加上明显的星星和 flush，确保 Gunicorn 立即输出日志
        print(f"\n★★★ PERF: {func.__name__} 耗时: {duration:.4f}s ★★★\n", flush=True)
        return result
    return wrapper
