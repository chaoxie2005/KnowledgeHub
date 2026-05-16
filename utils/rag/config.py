# RAG 配置常量：向量库路径、分块大小、检索参数
import os

# 向量库存储路径
CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chroma_blog")
DEFAULT_CHUNK_SIZE = 700
DEFAULT_CHUNK_OVERLAP = 120
VECTOR_SEARCH_K_DEFAULT = 10
RETRIEVAL_MAX_LEN = 12000
FALLBACK_MAX_LEN = 25000
