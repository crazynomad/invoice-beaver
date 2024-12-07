from typing import Dict, Optional
import logging
import json
from .base import InvoiceProcessor
from openai_helper import OpenAIHelper

class OpenAIProcessor(InvoiceProcessor):
    """使用OpenAI处理发票信息"""
    
    def __init__(self, api_key: str):
        self.openai_helper = OpenAIHelper(api_key=api_key)
        self.fields = [
            "发票号码", "开票日期", "购买方名称", "购买方纳税人识别号",
            "销售方名称", "销售方纳税人识别号", "金额", "税率", "税额", "价税合计"
        ]

    def process(self, content: str) -> Optional[Dict]:
        try:
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的发票信息提取助手。请从文本中提取以下字段信息：
- 发票号码
- 开票日期
- 购买方名称
- 购买方纳税人识别号
- 销售方名称
- 销售方纳税人识别号
- 金额
- 税率
- 税额
- 价税合计

请以JSON格式返回，确保所有字段都包含在响应中。如果某个字段未找到，将其值设为null。
例如：
{
    "发票号码": "123456",
    "开票日期": "2024-01-01",
    "购买方名称": "XX公司",
    "购买方纳税人识别号": "123456789",
    "销售方名称": "YY公司",
    "销售方纳税人识别号": "987654321",
    "金额": "100.00",
    "税率": "13%",
    "税额": "13.00",
    "价税合计": "113.00"
}"""
                },
                {
                    "role": "user",
                    "content": f"请从以下文本中提取发票信息：\n{content}"
                }
            ]
            
            # 使用OpenAIHelper发送请求
            response = self.openai_helper.make_request(
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            # 直接从响应中获取内容
            if response and hasattr(response, 'choices') and response.choices:
                try:
                    content = response.choices[0].message.content
                    result = json.loads(content)
                    
                    # 验证所有必需字段是否存在
                    for field in self.fields:
                        if field not in result:
                            result[field] = None
                            
                    return result
                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析失败: {str(e)}")
                    logging.error(f"原始响应内容: {content}")
                    return None
            else:
                logging.error("无效的API响应")
                logging.error(f"响应内容: {response}")
                return None
            
        except Exception as e:
            logging.error(f"发票信息处理失败: {str(e)}")
            return None 