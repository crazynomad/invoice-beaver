import os
import streamlit as st
from pathlib import Path
import tempfile
import json
from PIL import Image
import fitz  # PyMuPDF
import io
from typing import Optional
from ai_invoice_extractor import AIInvoiceExtractor

def get_page_image(pdf_file: bytes, page_num: int, zoom: float = 2.0):
    """获取PDF页面的图像预览"""
    pdf_document = fitz.open(stream=pdf_file, filetype="pdf")
    page = pdf_document[page_num]
    
    # 设置缩放和旋转
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # 转换为PIL Image
    img_data = pix.tobytes("png")
    return Image.open(io.BytesIO(img_data))

def get_page_count(pdf_file: bytes) -> int:
    """获取PDF的总页数"""
    pdf_document = fitz.open(stream=pdf_file, filetype="pdf")
    return len(pdf_document)

def process_pdf(pdf_file: bytes, api_key: str) -> Optional[dict]:
    """处理单个PDF文件"""
    # 创建临时文件保存上传的PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        tmp_file.write(pdf_file)
        tmp_path = tmp_file.name

    try:
        # 创建提取器实例
        extractor = AIInvoiceExtractor(api_key)
        
        # 处理PDF
        result = extractor.process_single_pdf(tmp_path)
        return result
    finally:
        # 清理临时文件
        os.unlink(tmp_path)

def main():
    st.set_page_config(layout="wide", page_title="发票信息提取工具")
    
    st.markdown("""
    # 发票信息提取工具
    
    这个工具可以自动从PDF发票中提取关键信息。支持：
    - PDF文件预览
    - 自动信息提取
    - JSON格式输出
    """)
    
    # 创建两列布局
    col1, col2 = st.columns([.5, .5])
    
    # 侧边栏配置
    api_key = st.sidebar.text_input(
        "OpenAI API Key",
        type="password",
        help="输入你的OpenAI API密钥"
    )
    
    uploaded_file = st.sidebar.file_uploader(
        "上传PDF发票:",
        type=["pdf"],
        help="选择要处理的PDF发票文件"
    )
    
    if uploaded_file is None:
        st.info("请上传PDF发票文件")
        return
        
    if not api_key:
        st.warning("请提供OpenAI API密钥")
        return
    
    # 左侧显示PDF预览
    with col1:
        st.subheader("PDF预览")
        try:
            # 获取PDF页面预览
            pdf_content = uploaded_file.read()
            page_count = get_page_count(pdf_content)
            page_number = st.number_input(
                f"页码 (共{page_count}页):",
                min_value=0,
                max_value=page_count-1,
                value=0
            )
            
            # 显示预览图像
            preview_image = get_page_image(pdf_content, page_number)
            st.image(preview_image, caption="PDF预览", use_column_width=True)
            
        except Exception as e:
            st.error(f"预览生成失败: {str(e)}")
    
    # 右侧显示提取结果
    with col2:
        st.subheader("提取结果")
        if st.button("开始提取"):
            with st.spinner("正在处理..."):
                try:
                    # 重置文件指针
                    uploaded_file.seek(0)
                    result = process_pdf(uploaded_file.read(), api_key)
                    
                    if result:
                        # 显示提取结果
                        st.json(result)
                        
                        # 提供下载按钮
                        json_str = json.dumps(result, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="下载JSON结果",
                            data=json_str.encode('utf-8'),
                            file_name="发票信息.json",
                            mime="application/json"
                        )
                    else:
                        st.error("提取失败，请检查PDF文件是否正确")
                        
                except Exception as e:
                    st.error(f"处理失败: {str(e)}")

if __name__ == "__main__":
    main() 