from enum import Enum
from typing import Dict, Optional, List, Union
import logging
import json
from .base import InvoiceProcessor
from openai import OpenAI
from pydantic import BaseModel

class OpenAIModel(str, Enum):
    """OpenAI 模型枚举"""
    GPT4_MINI = "gpt-4o-mini"  # 默认使用最新版本
    GPT4_MINI_20240718 = "gpt-4o-mini-2024-07-18"  # 特定版本
    GPT4_PREVIEW = "gpt-4-0125-preview"  # 完整版 GPT-4 预览版
    GPT4_VISION_PREVIEW = "gpt-4-vision-preview"  # 支持图像的 GPT-4

class Invoice(BaseModel):
    """发票数据模型"""
    文件名: str
    发票号码: str
    开票日期: str
    购买方名称: str
    购买方纳税人识别号: str
    销售方名称: str
    销售方纳税人识别号: str
    金额: str
    税率: str
    税额: str
    价税合计: str

class InvoiceResponse(BaseModel):
    """发票响应模型"""
    invoices: list[Invoice]

class OpenAIProcessor(InvoiceProcessor):
    """使用OpenAI处理发票信息"""
    
    DEFAULT_MODEL = OpenAIModel.GPT4_MINI
    
    def __init__(self, api_key: str, model: Optional[str] = None, debug: bool = False):
        self.client = OpenAI(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL
        self.debug = debug

    def _build_user_message(self, contents: List[Dict[str, str]]) -> str:
        """构建用户消息内容"""
        files_json = [{"文件名": item['filename'], "内容": item['content']} for item in contents]
        return "请解析以下发票信息：\n" + json.dumps(files_json, ensure_ascii=False, indent=2)

    def process(self, fileList: List[Dict[str, str]]) -> List[Dict[str, Union[str, Dict]]]:
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的发票信息提取助手。请从文本中提取发票关键信息。"
                },
                {
                    "role": "user",
                    "content": self._build_user_message(fileList)
                }
            ]
            
            if self.debug:
                logging.info("OpenAI API 请求内容:")
                logging.info(json.dumps(messages, ensure_ascii=False, indent=2))
            
            # 使用结构化输出
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=InvoiceResponse,
                temperature=0.1,
            )
            
            if self.debug:
                logging.info("OpenAI API 响应内容:")
                logging.info(json.dumps(completion.model_dump(), ensure_ascii=False, indent=2))
            
            results = []
            parsed_invoices = completion.choices[0].message.parsed.invoices
            
            # 直接返回解析后的发票数据，因为文件名已经包含在内
            return [invoice.model_dump() for invoice in parsed_invoices]
            
        except Exception as e:
            logging.error(f"发票信息处理失败: {str(e)}")
            return [{"文件名": item['filename']} for item in fileList] 