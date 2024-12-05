#!/usr/bin python3
# -*- coding:UTF-8 -*-
import re
import logging
from datetime import datetime

class InvoiceExtractor:
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
                r'价税合计.*小写.*[¥￥]?\s*(\d+\.?\d*)',
                r'价税合计.*小写.*芈\s*(\d+\.?\d*)',
                r'芈\s*(\d+\.?\d*)',
                r'[¥￥]?\s*(\d+\.?\d*)',
            ],
            '日期': [
                r'(\d{4})年(\d{1,2})月(\d{1,2})日?',
                r'开票日期:?\s*(\d{4})年(\d{1,2})月(\d{1,2})'
            ],
            '购买方': [
                r'购.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'
            ],
            '销售方': [
                r'销.*名称:?\s*(.+)',
                r'名称:\s*(.+?公司)'
            ],
            '税率': [
                r'(\d+)%',
                r'税率.*?(\d+)%'
            ]
        }
        self._cached_tax_rate = None
        self._cached_amounts = None

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

    def second_pass_process(self, failed_file, text_lines):
        """对失败的文件进行二次处理"""
        logging.info(f"开始二次处理文件: {failed_file}")
        
        try:
            # 重置当前发票信息
            self.current_invoice = {key: None for key in self.current_invoice}
            self.current_invoice['路径'] = failed_file
            
            # 尝试提取各个字段
            fields_to_retry = ['发票号码', '总金额', '日期', '购买方', '销售方', '税率']
            field_map = {
                '发票号码': '发票号',
                '总金额': '总金额',
                '日期': '日期',
                '购买方': '购买方',
                '销售方': '销售方',
                '税率': '税率'
            }
            
            for field in fields_to_retry:
                try:
                    value = self.retry_extract(text_lines, field)
                    if value is not None:
                        self.current_invoice[field_map[field]] = value
                        logging.info(f"二次处理成功提取 {field}: {value}")
                except Exception as e:
                    logging.error(f"提取字段 {field} 时出错: {str(e)}")
                    continue

            # 验证二次处理结果
            if (self.current_invoice['发票号'] is not None and 
                self.current_invoice['总金额'] is not None and 
                self.validate_amount(self.current_invoice['总金额'])):
                logging.info(f"二次处理成功 - 发票号: {self.current_invoice['发票号']}, "
                           f"金额: {self.current_invoice['总金额']:.2f}")
                self.invoices.append(self.current_invoice.copy())
                return True
            return False
            
        except Exception as e:
            logging.error(f"二次处理文件 {failed_file} 时出错: {str(e)}")
            return False

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
        text = re.sub(r'[^0-9.]', '', text)
        try:
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

        # 提取金额
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
            if (self.current_invoice['发票号'] is not None and 
                self.current_invoice['总金额'] is not None and 
                self.validate_amount(self.current_invoice['总金额'])):
                logging.info(f"成功处理发票 - 发票号: {self.current_invoice['发票号']}, "
                           f"金额: {self.current_invoice['总金额']:.2f}, "
                           f"文件: {self.current_invoice['路径']}")
            else:
                failed_file = self.current_invoice['路径']
                if failed_file not in self.failed_files:
                    self.failed_files.append(failed_file)
                logging.warning(f"发票处理失败 - 文件: {failed_file}")

    def validate_amount(self, amount):
        """验证金额是否合理"""
        if amount is None:
            return False
        return 0 < amount < 1000000

  