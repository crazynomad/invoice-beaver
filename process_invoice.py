#!/usr/bin python3
# -*- coding:UTF-8 -*-
import pandas as pd
import re
from pathlib import Path
import logging
from datetime import datetime

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('invoice_process.log'),
            logging.StreamHandler()
        ]
    )

class InvoiceProcessor:
    def __init__(self):
        self.current_invoice = {
            '路径': None,
            '购买方': None,
            '购买方纳税人识别号': None,
            '销售方': None,
            '销售方纳税人识别号': None,
            '发票代码': None,
            '发票号': None,
            '校验码': None,
            '日期': None,
            '总金额': None,
            '销售金额': None,
            '税率': None
        }
        self.invoices = []
        self.failed_files = []
        
    def extract_date(self, text):
        """提取日期"""
        pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日?'
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day)).strftime('%Y-%m-%d')
            except ValueError:
                return None
        return None

    def extract_amount(self, text):
        """提取金额"""
        # 移除所有特殊字符，保留数字和小数点
        text = re.sub(r'[^0-9.]', '', text)
        try:
            # 查找符合金额格式的部分
            pattern = r'(\d+\.\d{2})'
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        except ValueError:
            return None
        return None

    def extract_tax_rate(self, text):
        """提取税率"""
        pattern = r'(\d+)%'
        match = re.search(pattern, text)
        if match:
            return float(match.group(1)) / 100
        return None

    def process_line(self, text, source):
        """处理每一行文本"""
        if self.current_invoice['路径'] != source:
            if self.current_invoice['路径'] is not None:
                self.invoices.append(self.current_invoice.copy())
            self.current_invoice = {key: None for key in self.current_invoice}
            self.current_invoice['路径'] = source

        # 提取发票号码
        if '发票号码' in text:
            number_pattern = r'[:：]\s*(\d+)'
            match = re.search(number_pattern, text)
            if match:
                self.current_invoice['发票号'] = match.group(1)

        # 提取校验码
        if '校验码' in text:
            code_pattern = r'[:：]\s*([0-9\s]+)'
            match = re.search(code_pattern, text)
            if match:
                self.current_invoice['校验码'] = match.group(1).replace(' ', '')

        # 提取购买方信息
        if '购' in text and '名称' in text:
            name_pattern = r'[:：]\s*(.+)'
            match = re.search(name_pattern, text)
            if match:
                self.current_invoice['购买方'] = match.group(1).strip()

        # 提取销售方信息
        if '销' in text and '名称' in text:
            name_pattern = r'[:：]\s*(.+)'
            match = re.search(name_pattern, text)
            if match:
                self.current_invoice['销售方'] = match.group(1).strip()

        # 提取纳税人识别号
        if '纳税人识别号' in text or '统一社会信用代码' in text:
            tax_id_pattern = r'[:：]\s*([0-9A-Z]+)'
            match = re.search(tax_id_pattern, text)
            if match:
                if not self.current_invoice['购买方纳税人识别号']:
                    self.current_invoice['购买方纳税人识别号'] = match.group(1)
                else:
                    self.current_invoice['销售方纳税人识别号'] = match.group(1)

        # 提取日期
        if '开票日期' in text:
            date = self.extract_date(text)
            if date:
                self.current_invoice['日期'] = date

        # 提取金额 - 改进的逻辑
        if any(keyword in text for keyword in ['价税合计', '小写', '￥', '¥', '*']):
            amount = self.extract_amount(text)
            if amount and (self.current_invoice['总金额'] is None or amount > self.current_invoice['总金额']):
                self.current_invoice['总金额'] = amount

        # 提取销售金额
        if '金额' in text and '税率' in text:
            amount = self.extract_amount(text)
            if amount:
                self.current_invoice['销售金额'] = amount

        # 提取税率
        if '税率' in text:
            tax_rate = self.extract_tax_rate(text)
            if tax_rate:
                self.current_invoice['税率'] = tax_rate

    def finalize_invoice(self):
        """完成当前发票的处理并进行验证"""
        if self.current_invoice['路径'] is not None:
            # 检查关键字段是否都已成功提取
            if (self.current_invoice['发票号'] is not None and 
                self.current_invoice['总金额'] is not None and 
                self.validate_amount(self.current_invoice['总金额'])):
                # 打印成功处理的发票信息
                logging.info(f"成功处理发票 - 发票号: {self.current_invoice['发票号']}, "
                           f"金额: {self.current_invoice['总金额']:.2f}")
            else:
                # 记录处理失败的文件
                failed_file = self.current_invoice['路径']
                if failed_file not in self.failed_files:
                    self.failed_files.append(failed_file)
                logging.warning(f"发票处理失败 - 文件: {failed_file}")

    def process_csv(self, csv_path):
        """处理CSV文件"""
        df = pd.read_csv(csv_path)
        
        current_source = None
        for _, row in df.iterrows():
            if current_source != row['source']:
                self.finalize_invoice()  # 处理完一个发票后进行验证
                current_source = row['source']
            self.process_line(row['text'], row['source'])
        
        # 处理最后一个发票
        self.finalize_invoice()

        # 创建结果DataFrame
        result_df = pd.DataFrame(self.invoices)
        return result_df

    def validate_amount(self, amount):
        """验证金额是否合理"""
        if amount is None:
            return False
        # 金额应该大于0且小于一个合理的最大值（比如100万）
        return 0 < amount < 1000000

def main():
    setup_logging()
    logging.info("开始处理发票数据...")
    
    processor = InvoiceProcessor()
    try:
        result_df = processor.process_csv('output.csv')
        output_file = 'processed_invoices.xlsx'
        result_df.to_excel(output_file, index=False)
        
        # 打印统计信息
        total_invoices = len(result_df)
        valid_invoices = len(result_df.dropna(subset=['发票号', '总金额']))
        logging.info(f"总共处理了 {total_invoices} 张发票，其中 {valid_invoices} 张有效发票")
        
        # 打印失败文件列表
        if processor.failed_files:
            logging.warning("以下文件处理失败：")
            for failed_file in processor.failed_files:
                logging.warning(f"- {failed_file}")
            
            # 将失败文件列表保存到文件
            failed_files_path = 'failed_invoices.txt'
            with open(failed_files_path, 'w', encoding='utf-8') as f:
                for file in processor.failed_files:
                    f.write(f"{file}\n")
            logging.info(f"失败文件列表已保存到: {failed_files_path}")
        else:
            logging.info("所有文件处理成功！")
            
    except Exception as e:
        logging.error(f"处理过程中出现错误: {str(e)}")

if __name__ == "__main__":
    main() 