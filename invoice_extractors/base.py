from abc import ABC, abstractmethod
from typing import Dict, Optional, Union
from pathlib import Path

class PDFExtractor(ABC):
    """PDF内容提取器的基类"""
    
    @abstractmethod
    def extract(self, pdf_path: Union[str, Path]) -> Optional[str]:
        """从PDF中提取文本内容"""
        pass

class InvoiceProcessor(ABC):
    """发票信息处理器的基类"""
    
    @abstractmethod
    def process(self, content: str) -> Optional[Dict]:
        """处理提取的内容并返回发票信息"""
        pass 