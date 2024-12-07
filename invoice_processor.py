from pathlib import Path
import logging
import pandas as pd
from typing import Dict, Optional, Union
import urllib.parse
from invoice_extractors.base import PDFExtractor, InvoiceProcessor

class InvoiceExtractorService:
    """发票处理服务"""
    
    def __init__(self, pdf_extractor: PDFExtractor, invoice_processor: InvoiceProcessor):
        self.pdf_extractor = pdf_extractor
        self.invoice_processor = invoice_processor
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def normalize_filename(self, file_path: Union[str, Path]) -> Path:
        """处理文件名，解码URL编码的文件名"""
        file_path = Path(file_path)
        decoded_name = urllib.parse.unquote(file_path.name)
        
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

    def process_single_pdf(self, pdf_path: Union[str, Path]) -> Optional[Dict]:
        """处理单个PDF文件"""
        pdf_path = self.normalize_filename(pdf_path)
        
        content = self.pdf_extractor.extract(pdf_path)
        if not content:
            return None
            
        result = self.invoice_processor.process(content)
        if result:
            result["文件名"] = pdf_path.name
            
        return result

    def process_pdfs(self, input_dir: Union[str, Path], output_excel: Union[str, Path]) -> None:
        """批量处理PDF文件"""
        input_dir = Path(input_dir)
        results = []
        
        for pdf_file in input_dir.glob("*.pdf"):
            result = self.process_single_pdf(pdf_file)
            if result:
                results.append(result)
        
        if results:
            df = pd.DataFrame(results)
            df.to_excel(output_excel, index=False)
            logging.info(f"结果已保存到: {output_excel}")
        else:
            logging.warning("没有成功提取结果") 