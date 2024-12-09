#!/usr/bin python3
# -*- coding:UTF-8 -*-
# Author: nigo
import argparse
import os
import sys
from invoice_extractors.pdf_extractors import PyMuPDFExtractor, MarkerPDFExtractor, EasyOCRExtractor
from invoice_extractors.processors import OpenAIProcessor
from invoice_processor import InvoiceExtractorService
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='AI发票信息提取工具')
    parser.add_argument('--api-key', '-k',
                       help='OpenAI API密钥。也可通过环境变量 OPENAI_API_KEY 设置',
                       default=os.getenv('OPENAI_API_KEY'))
    parser.add_argument('--extractor', '-e',
                       choices=['pymupdf', 'marker', 'easyocr'],
                       default='pymupdf',
                       help='选择PDF提取器 (默认: pymupdf)')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    single_parser = subparsers.add_parser('single', help='处理单个PDF文件')
    single_parser.add_argument('--pdf', '-p', required=True, help='PDF文件路径')
    single_parser.add_argument('--output', '-o', help='输出JSON文件路径（可选）')
    
    batch_parser = subparsers.add_parser('batch', help='批量处理PDF文件')
    batch_parser.add_argument('--input', '-i', required=True, help='输入PDF文件目录')
    batch_parser.add_argument('--output', '-o', required=True, help='输出Excel文件路径')
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("错误：未提供OpenAI API密钥")
        sys.exit(1)
    
    # 选择PDF提取器
    if args.extractor == 'easyocr':
        pdf_extractor = EasyOCRExtractor()
    elif args.extractor == 'marker':
        pdf_extractor = MarkerPDFExtractor()
    else:
        pdf_extractor = PyMuPDFExtractor()
    
    # 创建处理器和服务
    invoice_processor = OpenAIProcessor(args.api_key, debug=True)
    service = InvoiceExtractorService(pdf_extractor, invoice_processor)
    
    if args.command == 'single':
        # 获取PDF文件名
        pdf_path = Path(args.pdf)
        filename = pdf_path.name
        
        # 处理单个PDF
        result = service.process_single_pdf(args.pdf)
        if result and len(result) > 0:
            # 获取第一个结果（因为是单文件处理）
            invoice_data = result[0]
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(invoice_data, f, ensure_ascii=False, indent=2)
                print(f"结果已保存到: {args.output}")
            else:
                print(json.dumps(invoice_data, ensure_ascii=False, indent=2))
        else:
            print("处理失败")
            sys.exit(1)
            
    elif args.command == 'batch':
        service.process_pdfs(args.input, args.output)
    
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()