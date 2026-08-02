"""
内容审核服务模块
利用大模型对用户提交的内容进行自动审核
"""
import os
import json
from dotenv import load_dotenv
from langchain_community.chat_models.tongyi import ChatTongyi

# 加载环境变量
load_dotenv()

class ContentAuditService:
    """内容审核服务类"""
    
    def __init__(self):
        """初始化审核服务，连接大模型"""
        self.llm = None
        try:
            from langchain_community.chat_models.tongyi import ChatTongyi
            api_key = os.getenv("QWEN_API_KEY")
            if not api_key:
                print("警告：QWEN_API_KEY 环境变量未设置")
                return
            
            try:
                self.llm = ChatTongyi(
                    temperature=0.1,  # 低温度，确保审核结果稳定
                    api_key=api_key, 
                    model="deepseek-r1-distill-qwen-7b",
                    streaming=False,
                )
            except TypeError:
                self.llm = ChatTongyi(
                    temperature=0.1,  # 低温度，确保审核结果稳定
                    api_key=api_key, 
                    model="deepseek-r1-distill-qwen-7b",
                )
        except Exception as e:
            print(f"警告：大模型初始化失败：{str(e)}")
            self.llm = None
    
    def audit_content(self, content: str, content_type: str = "comment") -> dict:
        """
        审核内容，返回审核结果
        
        Args:
            content: 待审核的内容文本
            content_type: 内容类型，如 "comment"(评论) 或 "article"(文章)
            
        Returns:
            审核结果字典，包含是否通过、风险等级、违规原因等
        """
        # 先进行简单的规则过滤
        violation_reasons = []
        
        # 检查是否包含违规内容
        if "赌博" in content or "博彩" in content:
            violation_reasons.append("包含赌博内容")
        if "色情" in content or "成人" in content:
            violation_reasons.append("包含色情内容")
        if "广告" in content or "推广" in content or "联系方式" in content:
            violation_reasons.append("包含广告内容")
        if "敏感" in content or "政治" in content:
            violation_reasons.append("包含敏感内容")
        
        # 如果规则过滤发现违规，直接返回
        if violation_reasons:
            return {
                "passed": False,
                "risk_level": "high",
                "violation_reasons": violation_reasons,
                "suggestion": "禁止发布，建议删除"
            }
        
        # 如果大模型初始化失败，返回默认通过
        if not self.llm:
            print("警告：大模型未初始化，使用规则过滤结果")
            return {
                "passed": True,
                "risk_level": "low",
                "violation_reasons": [],
                "suggestion": "通过审核"
            }
        
        # 构建审核提示词
        prompt = f"""
        请作为专业的内容审核专家，严格按照以下标准对{content_type}内容进行审核：
        
        【审核内容】
        {content}
        
        【审核标准】
        1. 违法违规：是否包含违反法律法规的内容
        2. 敏感信息：是否包含政治、宗教等敏感话题
        3. 垃圾广告：是否包含推广、营销等广告内容
        4. 不良信息：是否包含暴力、色情、赌博等不良内容
        5. 人身攻击：是否包含侮辱、诽谤等攻击他人的内容
        
        【返回格式】
        请以JSON格式返回审核结果，包含以下字段：
        - passed: 布尔值，表示是否通过审核
        - risk_level: 字符串，风险等级，可选值为 "low"(低)、"medium"(中)、"high"(高)
        - violation_reasons: 数组，违规原因列表
        - suggestion: 字符串，处理建议
        
        示例：
        {{
            "passed": false,
            "risk_level": "high",
            "violation_reasons": ["包含垃圾广告", "包含敏感信息"],
            "suggestion": "禁止发布，建议删除"
        }}
        """
        
        # 调用大模型进行审核
        try:
            response = self.llm.invoke(prompt)
            
            # 解析审核结果
            try:
                # 提取JSON部分
                result_str = response.content
                # 处理可能的格式问题
                if result_str.startswith("```json"):
                    result_str = result_str[7:-3]
                result = json.loads(result_str)
                return result
            except Exception as e:
                # 如果解析失败，返回默认错误结果
                return {
                    "passed": False,
                    "risk_level": "medium",
                    "violation_reasons": [f"审核结果解析失败: {str(e)}"],
                    "suggestion": "请人工审核"
                }
        except Exception as e:
            # 如果大模型调用失败，返回默认通过
            print(f"警告：大模型调用失败：{str(e)}")
            return {
                "passed": True,
                "risk_level": "low",
                "violation_reasons": [],
                "suggestion": "通过审核"
            }