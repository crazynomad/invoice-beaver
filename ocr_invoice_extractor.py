#!/usr/bin python3
# -*- coding:UTF-8 -*-
import easyocr
import fitz
import pandas as pd
import logging
import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Union
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from urllib.parse import unquote
import argparse
import sys

class OCRInvoiceExtractor:
    """使用 OCR 进行发票信息提取的类"""
    
    def __init__(self):
        """初始化 OCR 处理器"""
        # 初始化 OCR reader
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('process.log'),
                logging.StreamHandler()
            ]
        )
        
        # 初始化发票字段
        self.current_invoice = {
            '路径': None,
            '购买方': None,
            '购买方纳税人识别号': None,
            '销售方': None,
            '销售方纳税人识别号': None,
            '发票代码': None,
            '发票号': None,
            '校验码': None,
            '日期': None,
            '总金额': None,
            '销售金额': None,
            '税率': None
        }
        
        # 初始化正则表达式模式
        self.retry_patterns = {
            '发票号码': [
                r'发票号码:?\s*(\d+)',
                r'^\d{20}$'
            ],
            '总金额': [
                r'价税合计.*小写.*[¥￥]?\s*(\d+\.?\d*)',
                r'价税合计.*小写.*芈\s*(\d+\.?\d*)',
                r'芈\s*(\d+\.?\d*)',
                r'[¥￥]?\s*(\d+\.?\d*)',
            ],
            '日期': [
                r'(\d{4})年(\d{1,2})月(\d{1,2})日?',
                r'开票日期:?\s*(\d{4})年(\d{1,2})月(\d{1,2})'
            ],
            '购买方': [
                r'购.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'
            ],
            '销售方': [
                r'销.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'
            ],
            '税率': [
                r'(\d+)%',
                r'税率.*?(\d+)%'
            ]
        }

    def ensure_directory(self, directory: Union[str, Path], clear_contents: bool = False) -> None:
        """确保目录存在，可选择是否清空内容"""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        
        if clear_contents:
            for item in directory.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    def normalize_filename(self, file_path: Union[str, Path]) -> Path:
        """处理文件名，解码URL编码的文件名"""
        file_path = Path(file_path)
        decoded_name = unquote(file_path.name)
        
        if decoded_name != file_path.name:
            new_path = file_path.parent / decoded_name
            try:
                file_path.rename(new_path)
                logging.info(f"文件重命名: {file_path.name} -> {decoded_name}")
                return new_path
            except Exception as e:
                logging.error(f"文件重命名失败: {str(e)}")
                return file_path
        return file_path

    def pdf_to_image(self, pdf_path: Union[str, Path], image_path: Union[str, Path]) -> bool:
        """将PDF转换为图片"""
        try:
            pdf_doc = fitz.open(pdf_path)
            base_name = Path(pdf_path).stem
            
            for pg in range(pdf_doc.page_count):
                page = pdf_doc[pg]
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                image_name = f"{base_name}{'_%s' % pg if pdf_doc.page_count > 1 else ''}.png"
                image_full_path = Path(image_path) / image_name
                pix.save(str(image_full_path))
            
            pdf_doc.close()
            return True
            
        except Exception as e:
            logging.error(f"PDF转换失败 {pdf_path}: {str(e)}")
            return False

    def extract_text_from_image(self, image_path: Union[str, Path]) -> Optional[pd.DataFrame]:
        """从图片中提取文本"""
        try:
            result = self.reader.readtext(str(image_path))
            
            if not result:
                logging.warning(f"未检测到文本 {image_path}")
                return None
                
            texts = []
            for detection in result:
                text = detection[1]
                if text.strip():
                    texts.append(text)
            
            return pd.DataFrame({
                'text': texts,
                'source': Path(image_path).name
            })
            
        except Exception as e:
            logging.error(f"OCR处理失败 {image_path}: {str(e)}")
            return None

    def extract_invoice_info(self, text_df: pd.DataFrame) -> Dict:
        """从文本中提取发票信息"""
        # 重置当前发票信息
        self.current_invoice = {key: None for key in self.current_invoice}
        
        # 处理每一行文本
        for _, row in text_df.iterrows():
            self.process_text_line(row['text'])
        
        return self.current_invoice

    def process_text_line(self, text: str) -> None:
        """处理单行文本，提取发票信息"""
        # 提取发票号码
        if '发票号码' in text:
            match = re.search(r'[:：]\s*(\d+)', text)
            if match:
                self.current_invoice['发票号'] = match.group(1)

        # 提取日期
        if '开票日期' in text:
            date = self.extract_date(text)
            if date:
                self.current_invoice['日期'] = date

        # 提取金额
        if any(keyword in text for keyword in ['价税合计', '小写', '￥', '¥']):
            amount = self.extract_amount(text)
            if amount:
                self.current_invoice['总金额'] = amount

        # 提取其他字段...
        # (这里可以添加更多字段的提取逻辑)

    def extract_date(self, text: str) -> Optional[str]:
        """提取日期"""
        pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日?'
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day)).strftime('%Y-%m-%d')
            except ValueError:
                return None
        return None

    def extract_amount(self, text: str) -> Optional[float]:
        """提取金额"""
        text = re.sub(r'[^0-9.]', '', text)
        try:
            pattern = r'(\d+\.\d{2})'
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        except ValueError:
            return None
        return None

    def process_pdfs(self, 
                    input_dir: Union[str, Path], 
                    output_excel: Union[str, Path],
                    temp_dir: Union[str, Path] = './temp_images') -> None:
        """处理目录下的所有PDF文件并将结果保存到Excel"""
        input_dir = Path(input_dir)
        temp_dir = Path(temp_dir)
        
        # 准备目录
        self.ensure_directory(temp_dir, clear_contents=True)
        
        results = []
        
        # 处理所有PDF文件
        for pdf_file in input_dir.glob("*.pdf"):
            pdf_file = self.normalize_filename(pdf_file)
            logging.info(f"正在处理: {pdf_file.name}")
            
            # 转换为图片
            if not self.pdf_to_image(pdf_file, temp_dir):
                continue
            
            # 处理该PDF生成的所有图片
            for img_file in temp_dir.glob(f"{pdf_file.stem}*.png"):
                text_df = self.extract_text_from_image(img_file)
                if text_df is not None:
                    invoice_info = self.extract_invoice_info(text_df)
                    invoice_info['文件名'] = pdf_file.name
                    results.append(invoice_info)
                    logging.info(f"成功提取信息: {pdf_file.name}")
        
        # 保存结果
        if results:
            df = pd.DataFrame(results)
            df.to_excel(output_excel, index=False)
            logging.info(f"结果已保存到: {output_excel}")
        else:
            logging.warning("没有成功提取的结果")
        
        # 清理临时文件
        shutil.rmtree(temp_dir)

def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description='OCR发票信息提取工具')
    
    parser.add_argument('--input', '-i',
                       required=True,
                       help='输入PDF文件或目录')
    parser.add_argument('--output', '-o',
                       required=True,
                       help='输出Excel文件路径')
    parser.add_argument('--temp-dir', '-t',
                       default='./temp_images',
                       help='临时图片存储目录')
    
    args = parser.parse_args()
    
    extractor = OCRInvoiceExtractor()
    
    input_path = Path(args.input)
    if input_path.is_file():
        # 处理单个文件
        temp_dir = Path(args.temp_dir)
        extractor.ensure_directory(temp_dir, clear_contents=True)
        
        if extractor.pdf_to_image(input_path, temp_dir):
            results = []
            for img_file in temp_dir.glob(f"{input_path.stem}*.png"):
                text_df = extractor.extract_text_from_image(img_file)
                if text_df is not None:
                    invoice_info = extractor.extract_invoice_info(text_df)
                    invoice_info['文件名'] = input_path.name
                    results.append(invoice_info)
            
            if results:
                df = pd.DataFrame(results)
                df.to_excel(args.output, index=False)
                print(f"结果已保存到: {args.output}")
            else:
                print("处理失败")
                sys.exit(1)
        
        # 清理临时文件
        shutil.rmtree(temp_dir)
        
    elif input_path.is_dir():
        # 处理整个目录
        extractor.process_pdfs(input_path, args.output, args.temp_dir)
    
    else:
        print(f"错误：输入路径 {args.input} 无效")
        sys.exit(1)

if __name__ == '__main__':
    main() 