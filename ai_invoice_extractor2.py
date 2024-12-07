import logging
from pathlib import Path
import json
import pandas as pd
from typing import Dict, List, Optional, Union
from openai import OpenAI
import fitz
import shutil
import urllib.parse
from tiktoken import encoding_for_model
import time
from openai import RateLimitError

class AIInvoiceExtractor:
    """使用 AI 进行发票信息提取的类"""
    
    def __init__(self, openai_api_key: str, batch_size: int = 5, max_tokens_per_batch: int = 25000):
        """初始化处理器并清理blocks目录
        
        Args:
            openai_api_key: OpenAI API密钥
            batch_size: 每批处理的文件数量，默认为5
            max_tokens_per_batch: 每批次最大令牌数，默认25000（留有余量）
        """
        self.openai_api_key = openai_api_key
        self.batch_size = batch_size
        self.max_tokens_per_batch = max_tokens_per_batch
        self.encoder = encoding_for_model("gpt-4")
        self.sleep_time = 5  # Default sleep time between requests
        self.max_retries = 3  # Maximum number of retries
        self.retry_delay = 30  # Delay in seconds before retry on 429 error
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # 定义提取字段
        self.fields = [
            "发票号码",
            "开票日期",
            "购买方名称",
            "购买方纳税人识别号",
            "销售方名称",
            "销售方纳税人识别号",
            "金额",
            "税率",
            "税额",
            "价税合计"
        ]
        
        # 清理blocks目录
        self.clean_blocks_dir()

    def clean_blocks_dir(self):
        """清空blocks目录"""
        blocks_dir = Path("blocks")
        if blocks_dir.exists():
            shutil.rmtree(blocks_dir)
        blocks_dir.mkdir(exist_ok=True)
        logging.info("已清空blocks目录")

    def pdf_to_blocks(self, pdf_path: Union[str, Path]) -> Optional[tuple[str, List[Dict]]]:
        """
        将PDF转换为文本块保存
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            (文本内容, 文本块信息列表)的元组，如果失败则返回None
        """
        try:
            pdf_path = Path(pdf_path)
            
            # 创建blocks目录
            blocks_dir = Path("blocks") / pdf_path.stem
            blocks_dir.mkdir(parents=True, exist_ok=True)
            
            # 打开PDF文件
            doc = fitz.open(pdf_path)
            all_blocks = []
            
            # 处理每一页
            for page_num, page in enumerate(doc):
                # 获取文本块
                blocks = page.get_text("blocks")
                page_blocks = []
                
                # 处理每个文本块
                for i, block in enumerate(blocks):
                    block_text = block[4].strip()  # block[4] 包含文本内容
                    if block_text:  # 只保存非空文本块
                        block_info = {
                            "text": block_text,
                            "bbox": block[:4],  # 坐标信息
                            "block_no": i,
                            "page": page_num + 1
                        }
                        page_blocks.append(block_info)
                
                all_blocks.extend(page_blocks)
            
            # 保存文本块信息
            blocks_file = blocks_dir / f"{pdf_path.stem}_blocks.json"
            with open(blocks_file, 'w', encoding='utf-8') as f:
                json.dump(all_blocks, f, ensure_ascii=False, indent=2)
            
            # 生成用于AI处理的文本
            text_content = "\n".join(block["text"] for block in all_blocks)
            
            # 保存文本内容
            text_file = blocks_dir / f"{pdf_path.stem}_text.txt"
            text_file.write_text(text_content, encoding='utf-8')
            
            logging.info(f"文本块已保存到: {blocks_dir}")
            return text_content, all_blocks
            
        except Exception as e:
            logging.error(f"PDF转换失败: {str(e)}")
            return None

    def _make_openai_request(self, client, **kwargs):
        """Helper method to make OpenAI API requests with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = client.chat.completions.create(**kwargs)
                time.sleep(self.sleep_time)  # Sleep after successful request
                return response
            except RateLimitError as e:
                if attempt < self.max_retries - 1:
                    logging.warning(f"Rate limit exceeded. Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    raise e
            except Exception as e:
                logging.error(f"OpenAI API request failed: {str(e)}")
                raise e

    def extract_invoice_info(self, text_content: str, blocks_info: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        使用OpenAI API文本中提取发票信息
        
        Args:
            text_content: 原始文本内容
            blocks_info: 文本块信息列表，包含位置和内容
        """
        try:
            # 构建 prompt 和 response format
            if blocks_info:
                # 如果有JSON结构信息，只使用JSON
                prompt = """请从以下JSON结构化信息中提取发票信息。
这是一个包含文本块位置信息的JSON数组，每个文本块包含：
- text: 文本内容
- bbox: 文本块的坐标 [x0, y0, x1, y1]
- block_no: 块编号
- page: 页码

JSON结构：
{}

请提取发票信息。""".format(json.dumps(blocks_info, ensure_ascii=False, indent=2))
            else:
                # 如果没有JSON，使用纯文本
                prompt = """请从以下文本中提取发票信息。

文本内：
{}

请提取发票信息。""".format(text_content)

            # 调用OpenAI API，使用JSON mode
            client = OpenAI(api_key=self.openai_api_key)
            response = self._make_openai_request(
                client,
                model="gpt-4-turbo-preview",
                messages=[{
                    "role": "system",
                    "content": """你是一个专业的发票信息提取助手。你需要从提供的信息中提取发票信息，并以JSON格式返回。
如果提供了JSON结构，请特别注意文本块的位置信息(bbox)，这可以帮助你更准确地识别发票上的各个字段。
bbox格式为[x0, y0, x1, y1]，表示文本块的左上角和右下角坐标。
通常，发票的重要信息（如发票号码、金额等）会在特定位出现。"""
                }, {
                    "role": "user",
                    "content": prompt
                }],
                response_format={"type": "json_object"},  # 强制JSON输出
                functions=[{
                    "name": "extract_invoice_info",
                    "description": "从文本中提取发票信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "发票号码": {
                                "type": "string",
                                "description": "发票号码"
                            },
                            "开票日期": {
                                "type": "string",
                                "description": "开票日期，格式：YYYY-MM-DD"
                            },
                            "购买方名称": {
                                "type": "string",
                                "description": "购买方名称"
                            },
                            "购买方纳税人识别号": {
                                "type": "string",
                                "description": "购买方的纳税人识别号"
                            },
                            "销售方名称": {
                                "type": "string",
                                "description": "销售方名称"
                            },
                            "销售方纳税人识别号": {
                                "type": "string",
                                "description": "销售方的纳税人识别号"
                            },
                            "金额": {
                                "type": "number",
                                "description": "不含税金额"
                            },
                            "税率": {
                                "type": "number",
                                "description": "税率，例如0.13表示13%"
                            },
                            "税额": {
                                "type": "number",
                                "description": "税额"
                            },
                            "价税合计": {
                                "type": "number",
                                "description": "含税总金额"
                            }
                        },
                        "required": ["发票号码", "开票日期", "购买方名称", "销售方名称", "价税合计"]
                    }
                }],
                function_call={"name": "extract_invoice_info"},
                temperature=0.1
            )
            
            # 获取返回内容
            function_args = response.choices[0].message.function_call.arguments
            logging.info(f"OpenAI返回内容:\n{function_args}")
            
            try:
                result = json.loads(function_args)
                # 将None字符串转换为None
                result = {k: None if v == "null" or v == "" else v 
                         for k, v in result.items()}
                return result
            except json.JSONDecodeError as e:
                logging.error("OpenAI返回内容解析失败")
                logging.error(f"原始返回内容:\n{function_args}")
                logging.error(f"JSON解析错误: {str(e)}")
                return None
            
        except Exception as e:
            logging.error(f"发票信息提取失败: {str(e)}")
            if 'response' in locals():
                try:
                    logging.error(f"OpenAI原始返回内容:\n{response.choices[0].message.function_call.arguments}")
                except:
                    pass
            return None

    def batch_extract_invoice_info(self, text_contents: List[str], blocks_info_list: Optional[List[List[Dict]]] = None) -> List[Optional[Dict]]:
        """
        批量处理多个发票信息
        
        Args:
            text_contents: 原始文本内容列表
            blocks_info_list: 文本块信息列表的列表，每个元素对应一个文档的blocks信息
        
        Returns:
            包含发票信息的字典列表，与输入顺序一致
        """
        try:
            if blocks_info_list and len(text_contents) != len(blocks_info_list):
                logging.error("文本内容数量与blocks信息数量不匹配")
                return [None] * len(text_contents)
            
            # 构建批量处理的prompt
            prompts = []
            for i, text_content in enumerate(text_contents):
                if blocks_info_list:
                    # 使用JSON结构��息
                    prompt = {
                        "doc_id": i,
                        "content_type": "json",
                        "content": blocks_info_list[i]
                    }
                else:
                    # 使用纯文本
                    prompt = {
                        "doc_id": i,
                        "content_type": "text",
                        "content": text_content
                    }
                prompts.append(prompt)

            # 调用OpenAI API
            client = OpenAI(api_key=self.openai_api_key)
            response = self._make_openai_request(
                client,
                model="gpt-4-turbo-preview",
                messages=[{
                    "role": "system",
                    "content": """你是一个专业的发票信息提取助手。你需要从提供的信息中批量提取发票信息。
每个文档都有一个doc_id，你需要按顺序处理每个文档并返回结果数组。
如果提供的是JSON结构(content_type="json")，请特别注意文本块的位置信息(bbox)。
如果提供的是纯文本(content_type="text")，直接从文本中提取信息。
请确返回的数组顺序与输入文档的顺序一致"""
                }, {
                    "role": "user",
                    "content": f"请处理以下{len(prompts)}个文档：\n" + json.dumps(prompts, ensure_ascii=False, indent=2)
                }],
                response_format={"type": "json_object"},
                functions=[{
                    "name": "extract_invoice_info_batch",
                    "description": "批量提取发票信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "doc_id": {"type": "integer"},
                                        "data": {
                                            "type": "object",
                                            "properties": {
                                                "发票号码": {"type": "string"},
                                                "开票日期": {"type": "string"},
                                                "购买方名称": {"type": "string"},
                                                "购买方纳税人识别号": {"type": "string"},
                                                "销售方名称": {"type": "string"},
                                                "销售方纳税人识别号": {"type": "string"},
                                                "金额": {"type": "number"},
                                                "税率": {"type": "number"},
                                                "税额": {"type": "number"},
                                                "价税合计": {"type": "number"}
                                            },
                                            "required": ["发票号码", "开票日期", "购买方名称", "销售方名称", "价税合计"]
                                        }
                                    },
                                    "required": ["doc_id", "data"]
                                }
                            }
                        },
                        "required": ["results"]
                    }
                }],
                function_call={"name": "extract_invoice_info_batch"},
                temperature=0.1
            )
            
            # 解析返回结果
            function_args = response.choices[0].message.function_call.arguments
            logging.info(f"OpenAI返回内容:\n{function_args}")
            
            try:
                result_obj = json.loads(function_args)
                results = result_obj.get("results", [])
                
                # 确保结果顺序和数量正确
                ordered_results = [None] * len(text_contents)
                for result in results:
                    doc_id = result.get("doc_id")
                    if doc_id is not None and 0 <= doc_id < len(text_contents):
                        data = result.get("data")
                        # 将None字符串转换为None
                        if data:
                            data = {k: None if v == "null" or v == "" else v 
                                   for k, v in data.items()}
                        ordered_results[doc_id] = data
                        
                return ordered_results
                
            except json.JSONDecodeError as e:
                logging.error("OpenAI返回内容解析失败")
                logging.error(f"原始返回内容:\n{function_args}")
                logging.error(f"JSON解析错误: {str(e)}")
                return [None] * len(text_contents)
                
        except Exception as e:
            logging.error(f"批量发票信息提取失败: {str(e)}")
            return [None] * len(text_contents)

    def count_tokens(self, text: str) -> int:
        """计算文本的令牌数"""
        return len(self.encoder.encode(text))

    def _process_batch(self, pdf_files: List[Path], text_contents: List[str], blocks_info_list: List[List[Dict]]) -> List[Dict]:
        """处理一个批次的文件"""
        logging.info(f"开始处理批次，包含 {len(pdf_files)} 个文件")
        results = []
        
        # 计算总令牌数并根据需要拆分批次
        current_batch_files = []
        current_batch_texts = []
        current_batch_blocks = []
        current_tokens = 0
        
        for i, (pdf_file, text_content, blocks_info) in enumerate(zip(pdf_files, text_contents, blocks_info_list)):
            # 计算当前文档的令牌数
            doc_tokens = self.count_tokens(text_content)
            if blocks_info:
                doc_tokens += self.count_tokens(json.dumps(blocks_info, ensure_ascii=False))
            
            # 如果单个文档就超过限制，记录错误并跳过
            if doc_tokens > self.max_tokens_per_batch:
                logging.error(f"文件过大，跳过处理: {pdf_file.name} (tokens: {doc_tokens})")
                results.append(None)
                continue
            
            # 如果添加当前文档会超过批次限制，先处理当前批次
            if current_tokens + doc_tokens > self.max_tokens_per_batch:
                batch_results = self.batch_extract_invoice_info(current_batch_texts, current_batch_blocks)
                for pdf, result in zip(current_batch_files, batch_results):
                    if result:
                        result["文件名"] = pdf.name
                        results.append(result)
                    else:
                        results.append(None)
                        logging.error(f"信息提取失败: {pdf.name}")
                
                # 清空当前批次
                current_batch_files = []
                current_batch_texts = []
                current_batch_blocks = []
                current_tokens = 0
            
            # 添加到当前批次
            current_batch_files.append(pdf_file)
            current_batch_texts.append(text_content)
            current_batch_blocks.append(blocks_info)
            current_tokens += doc_tokens
        
        # 处理最后一个批次
        if current_batch_files:
            batch_results = self.batch_extract_invoice_info(current_batch_texts, current_batch_blocks)
            for pdf, result in zip(current_batch_files, batch_results):
                if result:
                    result["文件名"] = pdf.name
                    results.append(result)
                else:
                    results.append(None)
                    logging.error(f"信息提取失败: {pdf.name}")
        
        return results

    def process_pdfs(self, input_dir: Union[str, Path], output_excel: Union[str, Path]) -> None:
        """处理目录下的所有PDF文件并将结果保存到Excel"""
        input_dir = Path(input_dir)
        pdf_files = []
        text_contents = []
        blocks_info_list = []
        final_results = []
        current_batch_tokens = 0
        
        # 收集所有PDF文件的信息
        for pdf_file in input_dir.glob("*.pdf"):
            pdf_file = self.normalize_filename(pdf_file)
            logging.info(f"正在处理: {pdf_file.name}")
            
            result = self.pdf_to_blocks(pdf_file)
            if result:
                text_content, blocks_info = result
                pdf_files.append(pdf_file)
                text_contents.append(text_content)
                blocks_info_list.append(blocks_info)
                
                # 当达到批次大小或令牌制时处理当前批次
                if len(pdf_files) >= self.batch_size:
                    batch_results = self._process_batch(pdf_files, text_contents, blocks_info_list)
                    final_results.extend([r for r in batch_results if r is not None])
                    pdf_files = []
                    text_contents = []
                    blocks_info_list = []
            else:
                logging.error(f"无法处理文件: {pdf_file.name}")
        
        # 处理剩余的文件
        if pdf_files:
            batch_results = self._process_batch(pdf_files, text_contents, blocks_info_list)
            final_results.extend([r for r in batch_results if r is not None])
        
        # 保存到Excel
        if final_results:
            df = pd.DataFrame(final_results)
            df.to_excel(output_excel, index=False)
            logging.info(f"结果已保存到: {output_excel}")
        else:
            logging.warning("没有成功提取结果")

    def process_single_pdf(self, pdf_path: Union[str, Path]) -> Optional[Dict]:
        """处理单个PDF文件"""
        # 处理文件名
        pdf_path = self.normalize_filename(pdf_path)
        
        # 转换为文本块
        result = self.pdf_to_blocks(pdf_path)
        if not result:
            logging.error(f"无法处理文件: {pdf_path.name}")
            return None
            
        text_content, blocks_info = result
        # 提取信息
        invoice_info = self.extract_invoice_info(text_content, blocks_info)
        if invoice_info:
            invoice_info["文件名"] = pdf_path.name
            logging.info(f"成功提取信息: {pdf_path.name}")
            return invoice_info
        else:
            logging.error(f"信息提取失败: {pdf_path.name}")
            return None

    def normalize_filename(self, file_path: Union[str, Path]) -> Path:
        """
        处理文件名，解码URL编码的文件名
        
        Args:
            file_path: 原始文件路径
            
        Returns:
            处理后的Path对象
        """
        file_path = Path(file_path)
        decoded_name = urllib.parse.unquote(file_path.name)
        
        if decoded_name != file_path.name:
            # 如果文件名需要解码
            new_path = file_path.parent / decoded_name
            try:
                file_path.rename(new_path)
                logging.info(f"文件重命名: {file_path.name} -> {decoded_name}")
                return new_path
            except Exception as e:
                logging.error(f"文件重命名失败: {str(e)}")
                return file_path
        return file_path

def main():
    """命令行入口函数"""
    import argparse
    import sys
    import os
    
    parser = argparse.ArgumentParser(description='AI发票信息提取工具')
    parser.add_argument('--api-key', '-k',
                       help='OpenAI API密钥。也可通过环境变量 OPENAI_API_KEY 设置',
                       default=os.getenv('OPENAI_API_KEY'))
    parser.add_argument('--batch-size', '-b',
                       type=int,
                       default=5,
                       help='批处理大小，默认为5')
    parser.add_argument('--max-tokens', '-m',
                       type=int,
                       default=25000,
                       help='每批次最大令牌数，默认25000')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 单文件处命令
    single_parser = subparsers.add_parser('single', help='处理单个PDF文件')
    single_parser.add_argument('--pdf', '-p', 
                             dest='pdf_path',
                             required=True,
                             help='PDF文件路径')
    single_parser.add_argument('--output', '-o', 
                             help='输出JSON文件径（可选��')
    
    # 批量处命令
    batch_parser = subparsers.add_parser('batch', help='批量处理PDF文件')
    batch_parser.add_argument('--input', '-i',
                             dest='input_dir',
                             required=True,
                             help='输入PDF文件目录')
    batch_parser.add_argument('--output', '-o',
                             dest='output_excel',
                             required=True,
                             help='输出Excel文件路径')
    
    args = parser.parse_args()
    
    # 检查API密钥
    if not args.api_key:
        print("错误：未提供OpenAI API密钥。请通过--api-key参数或OPENAI_API_KEY环境变量提供。")
        sys.exit(1)
    
    # 创建提取器实例
    extractor = AIInvoiceExtractor(
        args.api_key, 
        batch_size=args.batch_size,
        max_tokens_per_batch=args.max_tokens
    )
    
    if args.command == 'single':
        # 处理单个文件
        result = extractor.process_single_pdf(args.pdf_path)
        if result:
            if args.output:
                # 保存到JSON文件
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"结果已保存到: {args.output}")
            else:
                # 直接打印到控制台
                print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("处理失败")
            sys.exit(1)
            
    elif args.command == 'batch':
        # 批量处理文件
        extractor.process_pdfs(args.input_dir, args.output_excel)
    
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main() 