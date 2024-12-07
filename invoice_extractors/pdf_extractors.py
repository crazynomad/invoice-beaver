from pathlib import Path
import logging
from typing import Optional, Union
import fitz
import json
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import save_output, text_from_rendered
from .base import PDFExtractor
import easyocr
import numpy as np
import cv2
import tempfile

class PyMuPDFExtractor(PDFExtractor):
    """使用PyMuPDF提取PDF内容"""
    
    def __init__(self):
        self.blocks_dir = Path("blocks")
        self.blocks_dir.mkdir(exist_ok=True)

    def extract(self, pdf_path: Union[str, Path]) -> Optional[str]:
        try:
            pdf_path = Path(pdf_path)
            blocks_dir = self.blocks_dir / pdf_path.stem
            blocks_dir.mkdir(parents=True, exist_ok=True)
            
            doc = fitz.open(pdf_path)
            all_blocks = []
            
            for page_num, page in enumerate(doc):
                blocks = page.get_text("blocks")
                page_blocks = []
                
                for i, block in enumerate(blocks):
                    block_text = block[4].strip()
                    if block_text:
                        block_info = {
                            "text": block_text,
                            "bbox": block[:4],
                            "block_no": i,
                            "page": page_num + 1
                        }
                        page_blocks.append(block_info)
                
                all_blocks.extend(page_blocks)
            
            text_content = "\n".join(block["text"] for block in all_blocks)
            
            # 保存提取结果
            blocks_file = blocks_dir / f"{pdf_path.stem}_blocks.json"
            text_file = blocks_dir / f"{pdf_path.stem}_text.txt"
            
            with open(blocks_file, 'w', encoding='utf-8') as f:
                json.dump(all_blocks, f, ensure_ascii=False, indent=2)
            text_file.write_text(text_content, encoding='utf-8')
            
            return text_content
            
        except Exception as e:
            logging.error(f"PDF提取失败: {str(e)}")
            return None

class MarkerPDFExtractor(PDFExtractor):
    """使用Marker库提取PDF内容"""
    
    def __init__(self):
        self.pdf_converter = PdfConverter(artifact_dict=create_model_dict())
        self.markdown_dir = Path("markdown")
        self.markdown_dir.mkdir(exist_ok=True)

    def extract(self, pdf_path: Union[str, Path]) -> Optional[str]:
        try:
            pdf_path = Path(pdf_path)
            markdown_dir = self.markdown_dir / pdf_path.stem
            markdown_dir.mkdir(parents=True, exist_ok=True)
            
            rendered = self.pdf_converter(str(pdf_path))
            save_output(rendered, str(markdown_dir), pdf_path.stem)
            
            text, _, _ = text_from_rendered(rendered)
            return text
            
        except Exception as e:
            logging.error(f"PDF提取失败: {str(e)}")
            return None 

class EasyOCRExtractor(PDFExtractor):
    """使用EasyOCR提取PDF内容"""
    
    def __init__(self):
        self.blocks_dir = Path("blocks")
        self.blocks_dir.mkdir(exist_ok=True)
        # 初始化EasyOCR reader，支持中文和英文
        self.reader = easyocr.Reader(['ch_sim', 'en'])
        
    def _pdf_to_images(self, pdf_path: Union[str, Path]) -> list:
        """将PDF转换为图片列表"""
        images = []
        doc = fitz.open(pdf_path)
        
        for page_num, page in enumerate(doc):
            # 获取页面像素图
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))  # 300 DPI
            
            # 转换为OpenCV格式
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            
            if pix.n == 4:  # RGBA
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
            
            images.append((img, page_num + 1))
            
        return images

    def _convert_to_native_types(self, obj):
        """将numpy类型转换为Python原生类型"""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, list):
            return [self._convert_to_native_types(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: self._convert_to_native_types(value) for key, value in obj.items()}
        return obj

    def extract(self, pdf_path: Union[str, Path]) -> Optional[str]:
        try:
            pdf_path = Path(pdf_path)
            blocks_dir = self.blocks_dir / pdf_path.stem
            blocks_dir.mkdir(parents=True, exist_ok=True)
            
            # 将PDF转换为图片
            images = self._pdf_to_images(pdf_path)
            all_blocks = []
            
            # 处理每一页
            for img, page_num in images:
                # 使用EasyOCR识别文字
                results = self.reader.readtext(img)
                
                # 转换为标准格式
                for i, (bbox, text, conf) in enumerate(results):
                    if text.strip():  # 只保存非空文本
                        # EasyOCR的bbox格式是[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                        # 转换为[x1,y1,x2,y2]格式
                        x1 = min(float(bbox[0][0]), float(bbox[3][0]))
                        y1 = min(float(bbox[0][1]), float(bbox[1][1]))
                        x2 = max(float(bbox[1][0]), float(bbox[2][0]))
                        y2 = max(float(bbox[2][1]), float(bbox[3][1]))
                        
                        block_info = {
                            "text": text.strip(),
                            "bbox": [x1, y1, x2, y2],
                            "block_no": i,
                            "page": page_num,
                            "confidence": float(conf)  # 确保置信度是float类型
                        }
                        all_blocks.append(block_info)
            
            # 生成文本内容
            text_content = "\n".join(block["text"] for block in all_blocks)
            
            # 保存提取结果前转换类型
            all_blocks = self._convert_to_native_types(all_blocks)
            
            # 保存提取结果
            blocks_file = blocks_dir / f"{pdf_path.stem}_blocks.json"
            text_file = blocks_dir / f"{pdf_path.stem}_text.txt"
            
            with open(blocks_file, 'w', encoding='utf-8') as f:
                json.dump(all_blocks, f, ensure_ascii=False, indent=2)
            text_file.write_text(text_content, encoding='utf-8')
            
            logging.info(f"EasyOCR提取完成: {pdf_path.name}")
            return text_content
            
        except Exception as e:
            logging.error(f"EasyOCR提取失败: {str(e)}")
            logging.exception("详细错误信息：")  # 添加详细的错误堆栈信息
            return None 