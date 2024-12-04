class Config:
    PDF_DIRECTORY = './pdf'
    IMG_DIRECTORY = './img'
    OUTPUT_FILE = 'output.xlsx'
    
    # OCR 配置
    OCR_CONFIG = {
        'languages': ['ch_sim', 'en'],  # 支持中文简体和英文
        'gpu': True,                    # 启用 GPU
        'batch_size': 4,                # 批处理大小
        'paragraph': True               # 启用段落识别
    }
    
    # PDF 转换配置
    PDF_CONVERSION = {
        'matrix_scale': 2.0,  # fitz.Matrix 缩放因子
        'alpha': False
    } 