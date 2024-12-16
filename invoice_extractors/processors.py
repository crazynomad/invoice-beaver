from enum import Enum
from typing import Dict, Optional, List, Union
import logging
import json
from .base import InvoiceProcessor
from openai import OpenAI
from pydantic import BaseModel
import cn2an

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
    价税合计大写: str

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
        return """请解析以下发票信息，特别注意：
1. 对于普通发票：
   - 提取"价税合计"的大写金额（例如"叁佰玖拾伍圆整"、"玖拾叁圆零壹分"等）并填入"价税合计大写"字段
   - 必须将大写金额转换为对应的数字金额（如"叁佰玖拾伍圆整"转为"395.00"）
   - 将转换后的数字金额作为"价税合计"字段的值
   - 即使发票上显示的数字金额不同，也必须使用从大写转换而来的数字金额
   - 例如：发现大写"叁佰玖拾伍圆整"时，不管发票上显示的数字是多少，"价税合计"都应该填写"395.00"
2. 对于铁路电子客票：
   - 识别关键字"铁路电子客票"判断是否为高铁票
   - 高铁票的价税合计即为票面显示的票价金额
   - 高铁票无需提取大写金额，价税合计大写字段填写"高铁票"

发票信息如下：
""" + json.dumps(files_json, ensure_ascii=False, indent=2)

    def _convert_chinese_amount_to_number(self, chinese_amount: str) -> Optional[float]:
        """将中文大写金额转换为数字"""
        if chinese_amount == "高铁票":
            return None
        
        # 移除"整"、"正"等后缀
        chinese_amount = chinese_amount.rstrip("整正")
        
        # 处理货币单位
        chinese_amount = (chinese_amount
            .replace('圆', '点')
            .replace('元', '点')
            .replace('角', '')
            .replace('分', ''))
        
        try:
            # 使用 cn2an 库进行转换
            result = cn2an.cn2an(chinese_amount, "smart")
            return round(float(result), 2)
        except Exception as e:
            logging.error(f"转换中文金额失败: {chinese_amount}, 错误: {str(e)}")
            return None

    def process(self, fileList: List[Dict[str, str]]) -> List[Dict[str, Union[str, Dict]]]:
        try:
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的发票信息提取助手。请从文本中提取发票关键信息。
特别注意：
1. 对于普通发票：
   - 必须提取"价税合计"的中文大写金额（如"叁佰玖拾伍圆整"）
   - 大写金额通常出现在"价税合计"附近，常见格式为"价税合计（大写）：叁佰玖拾伍圆整"
   - 必须将大写金额转换为对应的数字金额
   - 将转换后的数字金额作为最终的"价税合计"值
   - 例如：找到"叁佰玖拾伍圆整"后，应将"395.00"作为价税合计
   - 注意处理"零"、"整"、"正"等后缀，确保金额转换准确
2. 对于铁路电子客票：
   - 通过"铁路电子客票"关键字识别
   - 直接使用票面票价作为价税合计
   - 价税合计大写字段统一填写"高铁票"
   - 无需寻找大写金额"""
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
            
            for invoice in parsed_invoices:
                invoice_dict = invoice.model_dump()
                
                # 如果不是高铁票，检查价税合计
                if invoice_dict['价税合计大写'] != "高铁票":
                    # 将大写金额转换为��字
                    chinese_amount = self._convert_chinese_amount_to_number(invoice_dict['价税合计大写'])
                    if chinese_amount is not None:
                        # 将价税合计转换为浮点数进行比较
                        try:
                            numeric_amount = float(invoice_dict['价税合计'])
                            if abs(chinese_amount - numeric_amount) > 0.01:  # 允许0.01的误差
                                logging.warning(
                                    f"发票金额不匹配 - 文件名: {invoice_dict['文件名']}\n"
                                    f"大写金额: {invoice_dict['价税合计大写']}\n"
                                    f"转换后数值: {chinese_amount:.2f}\n"
                                    f"原始数值: {numeric_amount:.2f}"
                                )
                                # 如果不相等，使用从大写转换来的金额
                                invoice_dict['价税合计'] = f"{chinese_amount:.2f}"
                        except ValueError:
                            # 如果价税合计不是有效数字，直接使用从大写转换来的金额
                            logging.warning(
                                f"发票金额格式无效 - 文件名: {invoice_dict['文件��']}\n"
                                f"大写金额: {invoice_dict['价税合计大写']}\n"
                                f"转换后数值: {chinese_amount:.2f}\n"
                                f"原始无效数值: {invoice_dict['价税合计']}"
                            )
                            invoice_dict['价税合计'] = f"{chinese_amount:.2f}"
                
                results.append(invoice_dict)
            
            return results
            
        except Exception as e:
            logging.error(f"发票信息处理失败: {str(e)}")
            return [{"文件名": item['filename']} for item in fileList] 