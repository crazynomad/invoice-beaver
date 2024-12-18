import os
import streamlit as st
from pathlib import Path
import tempfile
import json
from PIL import Image
import fitz  # PyMuPDF
import io
from typing import Optional, List
from datetime import datetime
from invoice_extractors.pdf_extractors import PyMuPDFExtractor, MarkerPDFExtractor, EasyOCRExtractor
from invoice_extractors.processors import OpenAIProcessor
from invoice_processor import InvoiceExtractorService
import pandas as pd
import re

# 定义可用的提取策略
EXTRACTION_STRATEGIES = {
    "PyMuPDF": "pymupdf",
    "Marker": "marker",
    "EasyOCR": "easyocr"
}

def get_page_image(pdf_file: bytes, page_num: int, zoom: float = 2.0):
    """获取PDF页面的图像预览"""
    pdf_document = fitz.open(stream=pdf_file, filetype="pdf")
    page = pdf_document[page_num]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    return Image.open(io.BytesIO(img_data))

def get_page_count(pdf_file: bytes) -> int:
    """获取PDF的总页数"""
    pdf_document = fitz.open(stream=pdf_file, filetype="pdf")
    return len(pdf_document)

def process_pdf(pdf_file: bytes, api_key: str, strategy: str, log_container) -> Optional[dict]:
    """处理单个PDF文件"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_file.write(pdf_file)
        tmp_path = tmp_file.name

    try:
        # 选择PDF提取器
        if strategy == 'easyocr':
            pdf_extractor = EasyOCRExtractor()
        elif strategy == 'marker':
            pdf_extractor = MarkerPDFExtractor()
        else:
            pdf_extractor = PyMuPDFExtractor()

        # 创建处理器和服务
        invoice_processor = OpenAIProcessor(api_key)
        service = InvoiceExtractorService(pdf_extractor, invoice_processor)

        # 处理PDF
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_container.write(f"[{timestamp}] 开始处理PDF文件...\n")
        
        result = service.process_single_pdf(tmp_path)
        
        if result:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_container.write(f"[{timestamp}] PDF处理成功完成\n")
            return result
        else:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_container.write(f"[{timestamp}] PDF处理完成，但未返回结果\n")
            return None

    except Exception as e:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_container.write(f"[{timestamp}] PDF处理失败: {str(e)}\n")
        raise
    finally:
        try:
            os.unlink(tmp_path)
        except Exception as e:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_container.write(f"[{timestamp}] 清理临时文件失败: {str(e)}\n")

def sanitize_filename(filename: str) -> str:
    """安全处理文件名，移除特殊字符并限制长度"""
    # 移除文件扩展名
    filename = os.path.splitext(filename)[0]
    # 只保留字母、数字、下划线、连字符和点
    filename = re.sub(r'[^\w\-\.]', '_', filename)
    # 限制文件名长度为100个字符
    return filename[:100]

def process_multiple_pdfs(pdf_files: List[bytes], pdf_names: List[str], api_key: str, strategy: str, batch_id: str, progress_bar, log_container):
    """处理多个PDF文件"""
    # 创建临时目录存储上传的PDF文件
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        
        # 保存所有上传的PDF文件到临时目录
        for i, (pdf_file, original_name) in enumerate(zip(pdf_files, pdf_names)):
            # 安全处理文件名
            safe_name = sanitize_filename(original_name)
            # 确保文件名唯一
            temp_pdf_path = temp_dir / f"{safe_name}_{i}.pdf"
            with open(temp_pdf_path, "wb") as f:
                f.write(pdf_file)
            progress_bar.progress((i + 1) / (len(pdf_files) * 2))

        try:
            # 选择PDF提取器
            if strategy == 'easyocr':
                pdf_extractor = EasyOCRExtractor()
            elif strategy == 'marker':
                pdf_extractor = MarkerPDFExtractor()
            else:
                pdf_extractor = PyMuPDFExtractor()

            # 创建处理器和服务
            invoice_processor = OpenAIProcessor(api_key)
            service = InvoiceExtractorService(pdf_extractor, invoice_processor)
            
            # 修改Excel文件名以包含批次ID
            temp_excel = temp_dir / f"results_{batch_id}.xlsx"
            
            # 处理所有PDF文件
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_container.write(f"[{timestamp}] 开始批量处理PDF文件...\n")
            
            service.process_pdfs(temp_dir, temp_excel)
            
            # 读取Excel结果
            if temp_excel.exists():
                df = pd.read_excel(temp_excel)
                results = df.to_dict('records')
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_container.write(f"[{timestamp}] 批量处理完成，成功处理 {len(results)} 个文件\n")
                progress_bar.progress(1.0)  # 完成
                
                # 添加Excel下载按钮
                with open(temp_excel, 'rb') as f:
                    excel_data = f.read()
                    st.download_button(
                        label="下载Excel结果",
                        data=excel_data,
                        file_name=f"发票信息_批量_{batch_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                return results
            else:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_container.write(f"[{timestamp}] 处理完成，但未生成结果\n")
                return []
                
        except Exception as e:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_container.write(f"[{timestamp}] 批量处理失败: {str(e)}\n")
            raise

def main():
    st.set_page_config(layout="wide", page_title="发票信息提取工具")
    
    st.markdown("""
    # 发票信息提取工具
    
    这个工具可以自动从PDF发票中提取关键信息。支持：
    - 多种提取策略
    - 批量处理PDF文件
    - 实时处理日志
    - JSON格式输出
    """)
    
    # 侧边栏配置
    with st.sidebar:
        # 首先尝试从环境变量获取 API key
        default_api_key = os.environ.get('OPENAI_API_KEY', '')
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="输入你的OpenAI API密钥，如果不输入将使用���境变量中的API密钥",
            value=default_api_key
        )
        
        # 如果用户没有输入，尝试用环境变量中的 API key
        if not api_key and default_api_key:
            api_key = default_api_key
            st.info("使用环境变量中的 OpenAI API 密钥")
        
        strategy = st.selectbox(
            "选择提取策略",
            options=list(EXTRACTION_STRATEGIES.keys()),
            format_func=lambda x: x,
            help="选择用于提取文本的策略"
        )
        
        uploaded_files = st.file_uploader(
            "上传PDF发票:",
            type=["pdf"],
            accept_multiple_files=True,
            help="选择要处理的PDF发票文件"
        )
    
    if not uploaded_files:
        st.info("请上传PDF发票文件")
        return
        
    if not api_key:
        st.warning("请提供OpenAI API密钥")
        return
    
    # 创建三列布局
    col1, col2, col3 = st.columns([0.3, 0.4, 0.3])
    
    # 左侧显示PDF预览
    with col1:
        st.subheader("PDF预览")
        selected_file_index = st.selectbox(
            "选择要预览的文件",
            range(len(uploaded_files)),
            format_func=lambda x: uploaded_files[x].name
        )
        
        try:
            pdf_content = uploaded_files[selected_file_index].read()
            page_count = get_page_count(pdf_content)
            page_number = st.number_input(
                f"页码 (共{page_count}页):",
                min_value=0,
                max_value=page_count-1,
                value=0
            )
            
            preview_image = get_page_image(pdf_content, page_number)
            st.image(preview_image, caption="PDF预览", use_container_width=True)
            
        except Exception as e:
            st.error(f"预览生成失败: {str(e)}")
    
    # 中间显示处理日志
    with col2:
        st.subheader("处理日志")
        log_container = st.empty()
        progress_bar = st.progress(0)
        
        if st.button("开始处理"):
            with st.spinner("正在处理..."):
                try:
                    # 生成批次ID
                    batch_id = datetime.now().strftime("%H%M")
                    
                    # 获取所有PDF文件内容和文件名
                    pdf_contents = []
                    pdf_names = []
                    for uploaded_file in uploaded_files:
                        uploaded_file.seek(0)
                        pdf_contents.append(uploaded_file.read())
                        pdf_names.append(uploaded_file.name)
                    
                    # 处理所有文件
                    results = process_multiple_pdfs(
                        pdf_contents,
                        pdf_names,
                        api_key,
                        EXTRACTION_STRATEGIES[strategy],
                        batch_id,
                        progress_bar,
                        log_container
                    )
                    
                    if results:
                        # 保存所有结果
                        all_results = {
                            "batch_id": batch_id,
                            "extraction_strategy": strategy,
                            "timestamp": datetime.now().isoformat(),
                            "results": results
                        }
                        
                        # 提供下载按钮
                        json_str = json.dumps(all_results, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="下载所有结果",
                            data=json_str.encode('utf-8'),
                            file_name=f"发票信息_批量_{batch_id}.json",
                            mime="application/json"
                        )
                    else:
                        st.error("没有成功提取的结果")
                        
                except Exception as e:
                    st.error(f"处理失败: {str(e)}")
    
    # 右侧显示提取结果
    with col3:
        st.subheader("提取结果")
        if 'results' in locals():
            for i, result in enumerate(results):
                with st.expander(f"文件 {i+1} 的结果"):
                    st.json(result)

if __name__ == "__main__":
    main() 