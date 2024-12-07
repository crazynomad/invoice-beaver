import logging
import json
import time
from typing import Dict, List, Optional, Any, Callable
from openai import OpenAI, RateLimitError
from tiktoken import encoding_for_model

class OpenAIHelper:
    """OpenAI API调用的辅助类，提供批次控制和重试机制"""
    
    def __init__(self, 
                 api_key: str,
                 model: str = "gpt-4-turbo-preview",
                 batch_size: int = 5,
                 max_tokens_per_batch: int = 25000,
                 max_retries: int = 3,
                 retry_delay: int = 30,
                 sleep_time: int = 5):
        """
        初始化OpenAI辅助类
        
        Args:
            api_key: OpenAI API密钥
            model: 使用的模型名称
            batch_size: 每批处理的最大数量
            max_tokens_per_batch: 每批次最大令牌数
            max_retries: 最大重试次数
            retry_delay: 重试延迟时间(秒)
            sleep_time: 请求间隔时间(秒)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.batch_size = batch_size
        self.max_tokens_per_batch = max_tokens_per_batch
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.sleep_time = sleep_time
        self.encoder = encoding_for_model("gpt-4")  # 使用gpt-4的分词器
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def count_tokens(self, text: str) -> int:
        """计算文本的令牌数"""
        return len(self.encoder.encode(text))

    def make_request(self, 
                    messages: List[Dict[str, str]], 
                    functions: Optional[List[Dict]] = None,
                    function_call: Optional[Dict[str, str]] = None,
                    response_format: Optional[Dict[str, str]] = None) -> Any:
        """
        发送请求到OpenAI API，包含重试逻辑
        
        Args:
            messages: 消息列表
            functions: 函数定义列表
            function_call: 函数调用配置
            response_format: 响应格式配置
        
        Returns:
            API响应对象
        """
        for attempt in range(self.max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1
                }
                
                if functions:
                    kwargs["functions"] = functions
                if function_call:
                    kwargs["function_call"] = function_call
                if response_format:
                    kwargs["response_format"] = response_format
                
                response = self.client.chat.completions.create(**kwargs)
                time.sleep(self.sleep_time)
                return response
                
            except RateLimitError as e:
                if attempt < self.max_retries - 1:
                    logging.warning(f"速率限制，{self.retry_delay}秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    raise e
            except Exception as e:
                logging.error(f"OpenAI API请求失败: {str(e)}")
                raise e

    def process_batch(self, 
                     items: List[Any],
                     process_func: Callable[[List[Any]], List[Optional[Dict]]],
                     token_func: Callable[[Any], int]) -> List[Optional[Dict]]:
        """
        批量处理项目
        
        Args:
            items: 要处理的项目列表
            process_func: 处理批次的函数
            token_func: 计算���目令牌数的函数
            
        Returns:
            处理结果列表
        """
        results = []
        current_batch = []
        current_tokens = 0
        
        for item in items:
            item_tokens = token_func(item)
            
            # 如果单个项目超过限制，记录错误并跳过
            if item_tokens > self.max_tokens_per_batch:
                logging.error(f"项目过大，跳过处理 (tokens: {item_tokens})")
                results.append(None)
                continue
            
            # 如果添加当前项目会超过批次限制，先处理当前批次
            if (len(current_batch) >= self.batch_size or 
                current_tokens + item_tokens > self.max_tokens_per_batch):
                batch_results = process_func(current_batch)
                results.extend(batch_results)
                current_batch = []
                current_tokens = 0
            
            # 添加到当前批次
            current_batch.append(item)
            current_tokens += item_tokens
        
        # 处理最后一个批次
        if current_batch:
            batch_results = process_func(current_batch)
            results.extend(batch_results)
        
        return results

    def extract_json_from_response(self, response: Any) -> Optional[Dict]:
        """
        从API响应中提取JSON内容
        
        Args:
            response: API响应对象
            
        Returns:
            解析后的JSON字典，失败则返回None
        """
        try:
            if hasattr(response.choices[0].message, 'function_call'):
                content = response.choices[0].message.function_call.arguments
            else:
                content = response.choices[0].message.content
                
            logging.info(f"OpenAI返回内容:\n{content}")
            
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError as e:
                logging.error("OpenAI返回内容解析失败")
                logging.error(f"原始返回内容:\n{content}")
                logging.error(f"JSON解析错误: {str(e)}")
                return None
                
        except Exception as e:
            logging.error(f"响应处理失败: {str(e)}")
            return None 