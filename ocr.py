#!/usr/bin python3
# -*- coding:UTF-8 -*-
# Author: nigo
import easyocr
import pandas as pd
import logging
from pathlib import Path

# 全局 OCR 实例
reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)  # 使用中文简体和英文，启用GPU

def extract_text_from_result(result):
    """从 OCR 结果中提取文本"""
    texts = []
    for detection in result:
        text = detection[1]  # EasyOCR 结果格式: [([[坐标]], '文本', 置信度)]
        if text.strip():  # 确保文本不为空
            texts.append(text)
    return texts

def invoice_ocr(path):
    try:
        # 使用 EasyOCR 进行识别
        result = reader.readtext(path)
        
        if not result:
            logging.warning(f"No text detected in {path}")
            return None
            
        # 提取文本
        texts = extract_text_from_result(result)
        
        # 创建数据框
        df = pd.DataFrame({
            'text': texts,
            'source': Path(path).name
        })
        
        return df
        
    except Exception as e:
        logging.error(f"Error processing {path}: {str(e)}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = './img/test.png'
    result = invoice_ocr(path)
    print(result)