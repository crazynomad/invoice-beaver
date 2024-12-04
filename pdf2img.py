#!/usr/bin python3
# -*- coding:UTF-8 -*-
# Author: nigo
import sys, os, datetime
import fitz  # 直接导入 fitz
import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('process.log'),
            logging.StreamHandler()
        ]
    )

def pyMuPDF_fitz(pdf_path, image_path):
    pdfDoc = None
    try:
        pdfDoc = fitz.open(pdf_path)
        base_name = os.path.basename(pdf_path)
        pdf_name = os.path.splitext(base_name)[0]
        
        for pg in range(pdfDoc.page_count):
            page = pdfDoc[pg]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            if not os.path.exists(image_path):
                os.makedirs(image_path)
                
            image_name = pdf_name + ('_%s.png' % pg if pdfDoc.page_count > 1 else '.png')
            image_full_path = os.path.join(image_path, image_name)
            pix.save(image_full_path)
            
        return True
        
    except Exception as e:
        logging.error(f"Error processing {pdf_path}: {str(e)}")
        return False
    finally:
        if pdfDoc:
            pdfDoc.close()

if __name__ == "__main__":
    setup_logging()
    pdfPath = './TJB/餐饮94.pdf'
    imagePath = './img'
    pyMuPDF_fitz(pdfPath, imagePath)