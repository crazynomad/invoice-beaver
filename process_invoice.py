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
        self.retry_patterns = {
            '发票号码': [
                r'发票号码:?\s*(\d+)',
                r'^\d{20}$'  # 匹配单独的20位数字
            ],
            '总金额': [
                r'价税合计.*小写.*[¥￥]?\s*(\d+\.?\d*)',  # 修改：更灵活的小数点匹配
                r'价税合计.*小写.*芈\s*(\d+\.?\d*)',      # 添加：处理特殊字符"芈"的情况
                r'芈\s*(\d+\.?\d*)',                      # 其次匹配 "芈" 后的金额
                r'[¥￥]?\s*(\d+\.?\d*)',                  # 最后匹配其他金额格式
            ],
            '日期': [
                r'(\d{4})年(\d{1,2})月(\d{1,2})日?',
                r'开票日期:?\s*(\d{4})年(\d{1,2})月(\d{1,2})'
            ],
            '购买方': [
                r'购.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'  # 匹配以"公司"结尾的名称
            ],
            '销售方': [
                r'销.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'  # 匹配以"公司"结尾的名称
            ],
            '税率': [
                r'(\d+)%',
                r'税率.*?(\d+)%'
            ]
        }
        self._cached_tax_rate = None
        self._cached_amounts = None

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
            # 检查关键字段是否都已成功提
            if (self.current_invoice['发票号'] is not None and 
                self.current_invoice['总金额'] is not None and 
                self.validate_amount(self.current_invoice['总金额'])):
                # 打印成功处理的发票信息
                logging.info(f"成功处理发票 - 发票号: {self.current_invoice['发票号']}, "
                             f"金额: {self.current_invoice['总金额']:.2f}, "
                             f"文件: {self.current_invoice['路径']}")
            else:
                # 记录处理失败的文件
                failed_file = self.current_invoice['路径']
                if failed_file not in self.failed_files:
                    self.failed_files.append(failed_file)
                logging.warning(f"发票处理失败 - 文件: {failed_file}")

    def retry_extract(self, text_lines, field):
        """使用多个模式尝试提取字段值"""
        # 如果是发票号码，使用专门的模式匹配
        if field == '发票号码':
            for line in text_lines:
                for pattern in self.retry_patterns['发票号码']:
                    match = re.search(pattern, line)
                    if match:
                        # 确保使用正确的捕获组
                        invoice_number = match.group(1) if match.groups() else match.group(0)
                        if len(invoice_number) >= 8:  # 确保发票号长度合理
                            logging.info(f"二次处理成功提取发票号: {invoice_number}")
                            return invoice_number
            return None

        # 如果是购买方，使用原来的逻辑
        if field == '购买方':
            for line in text_lines:
                if '购' in line and '名称' in line:
                    match = re.search(r'[:：]\s*(.+)', line)
                    if match:
                        return match.group(1).strip()
            return None

        # 首先确定税率（使用缓存）
        if self._cached_tax_rate is None:
            for line in text_lines:
                tax_match = re.search(r'(\d+)%', line)
                if tax_match:
                    rate = float(tax_match.group(1))
                    if 0 < rate < 100:  # 只要是合理的百分数就接受
                        self._cached_tax_rate = rate / 100
                        logging.info(f"找到有效税率: {rate}%")
                        break

        # 如果是在找税率，直接返回缓存的税率
        if field == '税率':
            return self._cached_tax_rate

        # 收集所有可能的金额（使用缓存）
        if self._cached_amounts is None:
            self._cached_amounts = []
            for line in text_lines:
                numbers = re.findall(r'(\d+\.?\d*)', line)
                for num in numbers:
                    try:
                        amount = float(num)
                        if 0 < amount < 1000000:  # 验证金额合理性
                            self._cached_amounts.append(amount)
                    except ValueError:
                        continue
            # 去重并排序
            self._cached_amounts = sorted(list(set(self._cached_amounts)))
            logging.info(f"找到的所有可能金额: {self._cached_amounts}")

        # 如果在寻找总金额或销售金额，且已知税率
        if field in ['总金额', '销售金额'] and self._cached_tax_rate is not None:
            if not hasattr(self, '_found_match'):
                logging.info("开始寻找符合税率关系的金额组合...")
                for sales_amount in self._cached_amounts:
                    expected_total = round(sales_amount * (1 + self._cached_tax_rate), 2)
                    logging.info(f"尝试: 销售金额={sales_amount:.2f}, 期望总金额={expected_total:.2f}")
                    if expected_total in self._cached_amounts:
                        logging.info(f"找到匹配组合: 销售金额={sales_amount:.2f}, "
                                   f"税率={self._cached_tax_rate*100}%, "
                                   f"总金额={expected_total:.2f}")
                        self._found_match = True
                        self._cached_sales_amount = sales_amount
                        self._cached_total_amount = expected_total
                        break

            if hasattr(self, '_found_match'):
                if field == '总金额':
                    return self._cached_total_amount
                else:  # field == '销售金额'
                    return self._cached_sales_amount

        return None

    def second_pass_process(self, failed_file):
        """对失败的文件进行二次处理"""
        logging.info(f"开始二次处理文件: {failed_file}")
        # 重置缓存
        self._cached_tax_rate = None
        self._cached_amounts = None
        if hasattr(self, '_found_match'):
            delattr(self, '_found_match')
        
        try:
            # 读取该文件的所有文本行
            df = pd.read_csv('output.csv')
            text_lines = df[df['source'] == failed_file]['text'].tolist()
            
            # 重置当前发票信息
            self.current_invoice = {key: None for key in self.current_invoice}
            self.current_invoice['路径'] = failed_file
            
            # 尝试提取各个字段
            fields_to_retry = ['发票号码', '总金额', '日期', '购买方', '销售方', '税率']
            for field in fields_to_retry:
                field_map = {
                    '发票号码': '发票号',
                    '总金额': '总金额',
                    '日期': '日期',
                    '购买方': '购买方',
                    '销售方': '销售方',
                    '税率': '税率'
                }
                try:
                    value = self.retry_extract(text_lines, field)
                    if value is not None:
                        self.current_invoice[field_map[field]] = value
                        logging.info(f"二次处理成功提取 {field}: {value}")
                except Exception as e:
                    logging.error(f"提取字段 {field} 时出错: {str(e)}")
                    continue

            # 如果找到匹配，则更新发票列表并移除失败文件
            if (hasattr(self, '_found_match') and 
                self.current_invoice['发票号'] is not None and 
                self.current_invoice['总金额'] is not None):
                # 从 invoices 列表中移除旧的记录（如果存在）
                self.invoices = [inv for inv in self.invoices if inv['路径'] != failed_file]
                # 添加新的记录
                self.invoices.append(self.current_invoice.copy())
                logging.info(f"成功处理发票 - 发票号: {self.current_invoice['发票号']}, "
                            f"金额: {self.current_invoice['总金额']:.2f}, 路径: {self.current_invoice['路径']}")
                return True
            return False
        except Exception as e:
            logging.error(f"二次处理文件 {failed_file} 时出错: {str(e)}")
            return False

    def process_csv(self, csv_path):
        """处理CSV文件"""
        df = pd.read_csv(csv_path)
        
        current_source = None
        for _, row in df.iterrows():
            if current_source != row['source']:
                self.finalize_invoice()
                current_source = row['source']
            self.process_line(row['text'], row['source'])
        
        self.finalize_invoice()

        # 对失败的文件进行二次处理
        retry_success = []
        for failed_file in self.failed_files[:]:
            if self.second_pass_process(failed_file):
                retry_success.append(failed_file)
                self.failed_files.remove(failed_file)
                logging.info(f"二次处理成功: {failed_file}")

        # 记录二次处理的统计信息
        if retry_success:
            logging.info(f"二次处理成功数量: {len(retry_success)}")
            logging.info("二次处理成功的文件:")
            for file in retry_success:
                logging.info(f"- {file}")

        return pd.DataFrame(self.invoices)

    def validate_amount(self, amount):
        """验证金额是否合理"""
        if amount is None:
            return False
        # 金额应该大于0且小于一个合理的最大值（比如100万）
        return 0 < amount < 1000000

    def process_failed_files(self):
        """处理失败的文件"""
        if not self.failed_files:
            return
        
        successfully_processed = []
        for failed_file in self.failed_files:
            if self.second_pass_process(failed_file):
                successfully_processed.append(failed_file)
        
        # 在循环结束后一次性移除成功处理的文件
        for file in successfully_processed:
            self.failed_files.remove(file)

def main():
    setup_logging()
    logging.info("开始处理发票数据...")
    
    processor = InvoiceProcessor()
    try:
        result_df = processor.process_csv('output.csv')
        output_file = 'processed_invoices.xlsx'
        result_df.to_excel(output_file, index=False)
        
        # 统计信息
        result_df = result_df.drop_duplicates(subset=['路径'])
        valid_invoices = result_df.dropna(subset=['发票号', '总金额'])
        
        # 根据发票号去重
        unique_invoices = valid_invoices.drop_duplicates(subset=['发票号'])
        duplicate_invoices = valid_invoices[valid_invoices.duplicated(subset=['发票号'], keep=False)]
        
        total_invoices = len(result_df)
        valid_count = len(unique_invoices)
        
        # 打印处理结果详情
        logging.info("\n=== 发票处理详情 ===")
        logging.info("成功处理的发票：")
        for _, row in unique_invoices.iterrows():
            logging.info(f"发票号: {row['发票号']}, 金额: {row['总金额']:.2f}")
        
        # 打印重复的发票信息
        if not duplicate_invoices.empty:
            logging.info("\n重复的发票：")
            for _, row in duplicate_invoices.iterrows():
                logging.info(f"文件路径: {row['路径']}, 发票号: {row['发票号']}, 金额: {row['总金额']:.2f}")
        
        # 只打印仍然失败的发票
        remaining_failed_files = set(processor.failed_files) - set(valid_invoices['路径'])
        if remaining_failed_files:
            logging.info("\n处理失败的发票：")
            for file in remaining_failed_files:
                logging.info(f"文件路径: {file}")
        
        logging.info(f"\n总计：处理了 {total_invoices} 张发票，其中 {valid_count} 张有效发票")
        
        # 如果还有失败文件，则记录它们
        if processor.failed_files:
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