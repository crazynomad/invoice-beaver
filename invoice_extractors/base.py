from abc import ABC, abstractmethod
from typing import Dict, Optional, Union, List
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
    def process(self, contents: List[Dict[str, str]]) -> List[Dict[str, Union[str, Dict]]]:
        """
        处理提取的内容并返回发票信息
        Args:
            contents: 包含文件名和内容的字典列表
                     [{'filename': 'xxx.pdf', 'content': '发票内容'}, ...]
        Returns:
            包含文件名和解析后发票信息的字典列表
            [{'filename': 'xxx.pdf', 'invoice': {发票详细信息字典}}, ...]
        """
        pass 