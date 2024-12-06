import logging
from pathlib import Path
import json
import pandas as pd
from typing import Dict, List, Optional, Union
import openai
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import save_output, text_from_rendered
import argparse
import sys
import os
from openai import OpenAI
import urllib.parse
import shutil

class AIInvoiceExtractor:
    """使用 AI 进行发票信息提取的类"""
    
    def __init__(self, openai_api_key: str):
        """初始化处理器并清理markdown目录"""
        self.openai_api_key = openai_api_key
        openai.api_key = openai_api_key
        
        # 初始化 marker PDF转换器
        self.pdf_converter = PdfConverter(
            artifact_dict=create_model_dict(),
        )
        
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
        
        # 清理markdown目录
        self.clean_markdown_dir()

    def clean_markdown_dir(self):
        """清空markdown目录"""
        markdown_dir = Path("markdown")
        if markdown_dir.exists():
            shutil.rmtree(markdown_dir)
        markdown_dir.mkdir(exist_ok=True)
        logging.info("已清空markdown目录")

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

    def pdf_to_markdown(self, pdf_path: Union[str, Path]) -> Optional[str]:
        """
        将PDF转换为Markdown文本，并保存到对应目录
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            转换后的Markdown文本，如果失败则返回None
        """
        try:
            pdf_path = Path(pdf_path)
            
            # 创建markdown目录
            markdown_dir = Path("markdown") / pdf_path.stem
            markdown_dir.mkdir(parents=True, exist_ok=True)
            
            # 转换PDF
            rendered = self.pdf_converter(str(pdf_path))
            
            # 使用marker的save_output函数保存结果
            save_output(
                rendered,
                str(markdown_dir),  # 输出目录
                pdf_path.stem  # 基础文件名
            )
            
            # 获取文本内容用于后续处理
            text, _, _ = text_from_rendered(rendered)
            
            logging.info(f"Markdown和图片已保存到: {markdown_dir}")
            return text
            
        except Exception as e:
            logging.error(f"PDF转换失败: {str(e)}")
            return None

    def extract_invoice_info(self, markdown_text: str) -> Optional[Dict]:
        """
        使用OpenAI API从Markdown文本中提取发票信息
        
        Args:
            markdown_text: Markdown格式的文本
            
        Returns:
            包含发票信息的字典，如果失败则返回None
        """
        try:
            # 构建 prompt，使用原始字符串避免格式化问题
            prompt = r"""请从以下文本中提取发票信息，并以JSON格式返回。
需要提取的字段包括：发票号码、开票日期、购买方名称、购买方纳税人识别号、
销售名称、销售方纳税人识别号、金额、税率、税额、价税合计。
如果某个字段未找到，将其值设为null。

文本内容：
{}

请以下面的格式返回（仅返回JSON，不要其他说明）：
{{
    "发票号码": null,
    "开票日期": null,
    "购买方名称": null,
    "购买方纳税人识别号": null,
    "销售方名称": null,
    "销售方纳税人识别号": null,
    "金额": null,
    "税率": null,
    "税额": null,
    "价税合计": null
}}""".format(markdown_text)

            # 调用OpenAI API
            client = OpenAI(api_key=self.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # 获取原始返回内容
            raw_content = response.choices[0].message.content
            logging.info(f"OpenAI返回内容:\n{raw_content}")  # 添加这行来查看返回内容
            
            try:
                result = json.loads(raw_content)
                return result
            except json.JSONDecodeError as e:
                logging.error("OpenAI返回内容解析失败")
                logging.error(f"原始返回内容:\n{raw_content}")
                logging.error(f"JSON解析错误: {str(e)}")
                return None
            
        except Exception as e:
            logging.error(f"发票信息提取失败: {str(e)}")
            if 'response' in locals():
                try:
                    logging.error(f"OpenAI原始返回内容:\n{response.choices[0].message.content}")
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
            # 处理文件名
            pdf_file = self.normalize_filename(pdf_file)
            logging.info(f"正在处理: {pdf_file.name}")
            
            # 转换为Markdown
            markdown_text = self.pdf_to_markdown(pdf_file)
            if not markdown_text:
                logging.error(f"无法处理文件: {pdf_file.name}")
                continue
                
            # 提取信息
            invoice_info = self.extract_invoice_info(markdown_text)
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
        # 处理文件名
        pdf_path = self.normalize_filename(pdf_path)
        
        # 转换为Markdown
        markdown_text = self.pdf_to_markdown(pdf_path)
        if not markdown_text:
            logging.error(f"无法处理文件: {pdf_path.name}")
            return None
            
        # 提取信息
        invoice_info = self.extract_invoice_info(markdown_text)
        if invoice_info:
            invoice_info["文件名"] = pdf_path.name
            logging.info(f"成功提取信息: {pdf_path.name}")
            return invoice_info
        else:
            logging.error(f"信息提取失败: {pdf_path.name}")
            return None

def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description='AI发票信息提取工具')
    parser.add_argument('--api-key', '-k',
                       help='OpenAI API密钥。也可通过环境变量 OPENAI_API_KEY 设置',
                       default=os.getenv('OPENAI_API_KEY'))
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 单文件处理命令
    single_parser = subparsers.add_parser('single', help='处单个PDF文件')
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