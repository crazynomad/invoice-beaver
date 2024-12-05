#!/usr/bin python3
# -*- coding:UTF-8 -*-
# Author: nigo
import ocr
from pdf2img import pyMuPDF_fitz
import os
import pandas as pd
from pathlib import Path
import time
import logging
from tqdm import tqdm
import fitz
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from urllib.parse import unquote
import shutil

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('process.log'),
            logging.StreamHandler()
        ]
    )

def get_file_path(directory):
    # 使用 Path 对象处理路径
    directory_path = Path(directory)
    # 只获取 PDF 文件
    paths = list(directory_path.glob('*.pdf'))
    return [str(path) for path in paths if path.is_file()]

def ensure_directory(directory, clear_contents=False):
    """确保目录存在，如果不存在则创建。可选择是否清空目录内容"""
    if not os.path.exists(directory):
        os.makedirs(directory)
    elif clear_contents:
        # 只有当 clear_contents 为 True 时才清空目录
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logging.error(f'Error deleting {file_path}: {str(e)}')

def process_pdfs(paths, img_directory):
    successful_conversions = 0
    total_files = len(paths)
    
    with tqdm(total=total_files, desc="Converting PDFs") as pbar:
        for path in paths:
            try:
                if pyMuPDF_fitz(path, img_directory):
                    successful_conversions += 1
                pbar.update(1)
            except Exception as e:
                logging.error(f'Error converting {Path(path).name}: {str(e)}')
    
    return successful_conversions, total_files

def process_images(img_paths, batch_size=10):
    df_list = []
    
    for i in range(0, len(img_paths), batch_size):
        batch = img_paths[i:i + batch_size]
        # 处理这一批图片
        for path in batch:
            try:
                df = ocr.invoice_ocr(path)
                if df is not None and not df.empty:
                    df_list.append(df)
            except Exception as e:
                logging.error(f'Error processing {Path(path).name}: {str(e)}')
        
        # 定期释放内存
        if len(df_list) > 100:
            df = pd.concat(df_list, ignore_index=True)
            df_list = [df]
    
    return df_list

def validate_pdf(path):
    # 检查文件大小
    max_size = 100 * 1024 * 1024  # 100MB
    if os.path.getsize(path) > max_size:
        logging.warning(f"File too large: {path}")
        return False
    
    # 检查是否为有效的PDF
    try:
        with fitz.open(path) as doc:
            if doc.page_count == 0:
                logging.warning(f"Empty PDF file: {path}")
                return False
    except Exception:
        logging.warning(f"Invalid PDF file: {path}")
        return False
    
    return True

def process_pdfs_parallel(paths, img_directory):
    with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        futures = [executor.submit(pyMuPDF_fitz, path, img_directory) for path in paths]
        results = [future.result() for future in futures]
    return sum(results), len(paths)

def rename_url_encoded_files(directory):
    """检查并重命名包含URL编码的PDF文件"""
    directory_path = Path(directory)
    renamed_files = {}  # 用于存储原文件名和���文件名的映射
    
    for pdf_path in directory_path.glob('*.pdf'):
        original_name = pdf_path.name
        decoded_name = unquote(original_name)
        
        # 如果解码后的文件名与原文件名不同，说明包含URL编码
        if decoded_name != original_name:
            new_path = pdf_path.parent / decoded_name
            try:
                # 如果目标文件已存在，添加数字后缀
                if new_path.exists():
                    base, ext = os.path.splitext(decoded_name)
                    counter = 1
                    while new_path.exists():
                        new_name = f"{base}_{counter}{ext}"
                        new_path = pdf_path.parent / new_name
                        counter += 1
                
                # 重命名文件
                shutil.move(str(pdf_path), str(new_path))
                renamed_files[str(pdf_path)] = str(new_path)
                logging.info(f"重命名文件: {original_name} -> {new_path.name}")
            except Exception as e:
                logging.error(f"重命名文件失败 {original_name}: {str(e)}")
    
    return renamed_files

if __name__ == "__main__":
    setup_logging()
    pdf_directory = './pdf'
    img_directory = './img'
    
    # pdf 目录不清空，img 目录需要清空
    ensure_directory(pdf_directory, clear_contents=False)
    ensure_directory(img_directory, clear_contents=True)
    
    # 重命名包含URL编码的文件
    renamed_files = rename_url_encoded_files(pdf_directory)
    
    # PDF 处理
    paths = get_file_path(pdf_directory)
    if not paths:
        logging.warning(f"Warning: No PDF files found in {pdf_directory}")
        exit(1)
    
    # 使用新的处理函数
    successful_conversions, total_files = process_pdfs_parallel(paths, img_directory)
    logging.info(f'\nPDF to PNG conversion completed: {successful_conversions}/{total_files} files converted successfully\n')
    
    # 确保在处理图片前有短暂暂停
    time.sleep(1)
    
    # 重新获取图片列表
    img_paths = list(Path(img_directory).glob('*.png'))
    img_paths = [str(path) for path in img_paths if path.is_file()]
    
    df_list = process_images(img_paths)
    
    if df_list:
        df = pd.concat(df_list, ignore_index=True)
        # Excel 输出
        excel_path = 'output.xlsx'
        # CSV 输出
        csv_path = 'output.csv'
        try:
            df.to_excel(excel_path, index=False)
            df.to_csv(csv_path, index=False, encoding='utf-8')
            logging.info(f'Results successfully saved to {excel_path} and {csv_path}')
        except Exception as e:
            logging.error(f'Error saving results: {str(e)}')
    else:
        logging.info("No data to save - all OCR processing failed")