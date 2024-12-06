import logging
from pathlib import Path
import json
import pandas as pd
from typing import Dict, List, Optional, Union
from openai import OpenAI
import fitz
import shutil

class AIInvoiceExtractor:
    """使用 AI 进行发票信息提取的类"""
    
    def __init__(self, openai_api_key: str):
        """初始化处理器并清理blocks目录"""
        self.openai_api_key = openai_api_key
        
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

    def pdf_to_blocks(self, pdf_path: Union[str, Path]) -> Optional[str]:
        """
        将PDF转换为文本块并保存
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            转换后的文本内容，如果失败则返回None
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
            return text_content
            
        except Exception as e:
            logging.error(f"PDF转换失败: {str(e)}")
            return None

    def extract_invoice_info(self, text_content: str) -> Optional[Dict]:
        """使用OpenAI API从文本中提取发票信息"""
        try:
            # 构建 prompt 和 response format
            prompt = """请从以下文本中提取发票信息。

文本内容：
{}

请提取以上文本中的发票信息。""".format(text_content)

            # 调用OpenAI API，使用JSON mode
            client = OpenAI(api_key=self.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{
                    "role": "system",
                    "content": "你是一个专业的发票信息提取助手。你需要从文本中提取发票信息，并以JSON格式返回。"
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
                function_call={"name": "extract_invoice_info"},  # 强制调用函数
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

    def process_pdfs(self, 
                    input_dir: Union[str, Path], 
                    output_excel: Union[str, Path]) -> None:
        """处理目录下的所有PDF文件并将结果保存到Excel"""
        input_dir = Path(input_dir)
        results = []
        
        # 处理所有PDF文件
        for pdf_file in input_dir.glob("*.pdf"):
            logging.info(f"正在处理: {pdf_file.name}")
            
            # 转换为文本块
            text_content = self.pdf_to_blocks(pdf_file)
            if not text_content:
                logging.error(f"无法处理文件: {pdf_file.name}")
                continue
                
            # 提取信息
            invoice_info = self.extract_invoice_info(text_content)
            if invoice_info:
                invoice_info["文件名"] = pdf_file.name
                results.append(invoice_info)
                logging.info(f"成功提取信息: {pdf_file.name}")
            else:
                logging.error(f"信息提取失败: {pdf_file.name}")
        
        # 保存到Excel
        if results:
            df = pd.DataFrame(results)
            df.to_excel(output_excel, index=False)
            logging.info(f"结果已保存到: {output_excel}")
        else:
            logging.warning("没有成功提取结果")

    def process_single_pdf(self, 
                         pdf_path: Union[str, Path]) -> Optional[Dict]:
        """处理单个PDF文件"""
        pdf_path = Path(pdf_path)
        
        # 转换为文本块
        text_content = self.pdf_to_blocks(pdf_path)
        if not text_content:
            logging.error(f"无法处理文件: {pdf_path.name}")
            return None
            
        # 提取信息
        invoice_info = self.extract_invoice_info(text_content)
        if invoice_info:
            invoice_info["文件名"] = pdf_path.name
            logging.info(f"成功提取信息: {pdf_path.name}")
            return invoice_info
        else:
            logging.error(f"信息提取失败: {pdf_path.name}")
            return None

def main():
    """命令行入口函数"""
    import argparse
    import sys
    import os
    
    parser = argparse.ArgumentParser(description='AI发票信息提取工具')
    parser.add_argument('--api-key', '-k',
                       help='OpenAI API密钥。也可通过环境变量 OPENAI_API_KEY 设置',
                       default=os.getenv('OPENAI_API_KEY'))
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 单文件处理命令
    single_parser = subparsers.add_parser('single', help='处理单个PDF文件')
    single_parser.add_argument('--pdf', '-p', 
                             dest='pdf_path',
                             required=True,
                             help='PDF文件路径')
    single_parser.add_argument('--output', '-o', 
                             help='输出JSON文件路径（可选）')
    
    # 批量处理命令
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
    extractor = AIInvoiceExtractor(args.api_key)
    
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