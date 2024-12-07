from pathlib import Path
import logging
from typing import Optional, Union
import fitz
import json
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import save_output, text_from_rendered
from .base import PDFExtractor

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