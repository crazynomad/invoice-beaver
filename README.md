# Invoice OCR Processor

基于 EasyOCR 的发票识别处理系统，支持 M1 GPU 加速。本项目可以批量处理发票 PDF 文件，提取关键信息并输出结构化数据。

## 功能特点

- PDF 转图片：使用 PyMuPDF 高效转换
- OCR 文字识别：使用 EasyOCR，支持 M1 GPU 加速
- 发票信息结构化提取：
  - 发票基本信息（代码、号码、日期等）
  - 购销方信息（名称、税号等）
  - 金额信息（总金额、税额等）
- 批量处理支持
- 并发处理优化
- 详细的日志记录

## 项目结构

.
├── main.py # 主程序入口，负责流程控制
├── ocr.py # OCR 识别模块，使用 EasyOCR 进行文字识别
├── pdf2img.py # PDF 转图片模块，使用 PyMuPDF 进行转换
├── process_invoice.py # 发票信息提取模块，处理结构化数据
├── config.py # 配置文件，包含各种参数设置
├── requirements.txt # 项目依赖列表
└── README.md # 项目说明文档



## 环境要求

- Python 3.8+
- MacOS (M1/M2 芯片)或其他支持 GPU 的系统
- 足够的磁盘空间用于存储转换���的图片

## 安装步骤

1. 克隆项目

bash
git clone <repository-url>
cd invoice-ocr-processor

2. 创建并激活虚拟环境
bash
python -m venv venv
source venv/bin/activate # Unix/MacOS
或
.\venv\Scripts\activate # Windows

3. 安装依赖
bash
pip install -r requirements.txt

## 使用方法

1. 准备工作
   - 创建 `pdf` 目录并放入待处理的发票 PDF 文件
   - 确保 `img` 目录存在（用于存储转换后的图片）

2. 运行程序
bash
python main.py

3. 查看结果
   - `output.csv`: OCR 原始识别结果
   - `processed_invoices.xlsx`: 结构化后的发票信息
   - `process.log`: 处理日志

## 输出数据说明

processed_invoices.xlsx 包含以下字段：
- 路径：原始文件路径
- 购买方：购买方名称
- 购买方纳税人识别号：购买方税号
- 销售方：销售方名称
- 销售方纳税人识别号：销售方税号
- 发票代码：发票代码
- 发票号：发票号码
- 校验码：发票校验码
- 日期：开票日期
- 总金额：价税合计金额
- 销售金额：不含税金额
- 税率：增值税税率

## 配置说明

在 `config.py` 中可以修改以下配置：
python
class Config:
PDF_DIRECTORY = './pdf' # PDF 文件目录
IMG_DIRECTORY = './img' # 图片输出目录
# OCR 配置
OCR_CONFIG = {
'languages': ['ch_sim', 'en'], # 支持中文简体和英文
'gpu': True, # 启用 GPU
'batch_size': 4, # 批处理大小
'paragraph': True # 启用段落识别
}
# PDF 转换配置
PDF_CONVERSION = {
'matrix_scale': 2.0, # 图片缩放比例
'alpha': False # 是否保留透明通道
}

## 性能优化

1. GPU 加速
   - 默认启用 M1 GPU 加速
   - 可通过 config.py 中的 gpu 参数控制

2. 并发处理
   - PDF 转换使用多线程
   - OCR 识别使用批处理

3. 内存管理
   - 批量处理大量图片
   - 定期释放内存

## 常见问题

1. GPU 加速不生效
   - 确认已正确安装 PyTorch
   - 检查 GPU 驱动是否正确安装

2. 内存占用过高
   - 调整 config.py 中的 batch_size
   - 减小 PDF 转换时的 matrix_scale

3. 识别准确率不足
   - 调整图片转换质量
   - 检查原始 PDF 质量

## 开发计划

- [ ] 支持更多发票类型
- [ ] 优化识别准确率
- [ ] 添加 Web 界面
- [ ] 支持导出更多格式

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进项目。

## 许可证

MIT License

## 更新日志

- 2024-01-01: 初始版本发布
- 2024-01-02: 添加 M1 GPU 支持
- 2024-01-03: 优化发票信息提取