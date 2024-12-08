#!/usr/bin python3
# -*- coding:UTF-8 -*-
import pandas as pd
import logging
from pathlib import Path
from legacy.invoice_extractor import InvoiceExtractor
from natsort import natsorted

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('invoice_process.log'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    logging.info("开始处理发票数据...")
    
    processor = InvoiceExtractor()
    invoices = []
    failed_files = []
    
    try:
        # 读取CSV文件
        df = pd.read_csv('output.csv').dropna(how='all')
        
        # 第一次处理
        current_source = None
        for _, row in df.iterrows():
            if current_source != row['source']:
                if current_source is not None:
                    processor.finalize_invoice()
                    if (processor.current_invoice['发票号'] is not None and 
                        processor.current_invoice['总金额'] is not None):
                        invoices.append(processor.current_invoice.copy())
                    else:
                        failed_files.append(current_source)
                current_source = row['source']
            processor.process_line(row['text'], row['source'])
        
        # 确保处理最后一张发票
        if current_source is not None:
            processor.finalize_invoice()
            if (processor.current_invoice['发票号'] is not None and 
                processor.current_invoice['总金额'] is not None):
                invoices.append(processor.current_invoice.copy())
            else:
                failed_files.append(current_source)

        # 对失败的文件进行二次处理
        if failed_files:
            logging.info("\n=== 开始二次处理失败件 ===")
            retry_success = []
            for failed_file in failed_files[:]:
                # 获取该文件的所有文本行
                text_lines = df[df['source'] == failed_file]['text'].tolist()
                invoice_data = processor.second_pass_process(failed_file, text_lines)
                if invoice_data:  # 如果二次处理成功返回发票数据
                    retry_success.append(failed_file)
                    failed_files.remove(failed_file)
                    # 将成功处理的发票数据添加到 invoices 列表中
                    invoices.append({
                        '路径': failed_file,
                        **invoice_data  # 展开发票数据字典
                    })
            
            if retry_success:
                logging.info(f"\n二次处理成功数量: {len(retry_success)}")
                logging.info("二次处理成功的文件:")
                for file in retry_success:
                    logging.info(f"- {file}")

        # 创建结果DataFrame
        result_df = pd.DataFrame(invoices)
        
        # 先获取所有有效的发票记录（包括第一次处理成功和二次处理成功的）
        valid_invoices = result_df.dropna(subset=['发票号', '总金额'])
        valid_invoices = valid_invoices[valid_invoices['发票号'].notna() & (valid_invoices['发票号'] != '')]
        
        # 按发票号分组，保留每组中最早的记录（即第一次处理成功的记录）
        unique_invoices = valid_invoices.sort_values('路径').groupby('发票号').first().reset_index()
        
        # 保存到Excel
        output_file = 'processed_invoices.xlsx'
        unique_invoices.to_excel(output_file, index=False)
        
        # 按路径排序后再输出处理结果详情
        unique_invoices = unique_invoices.sort_values('路径', key=lambda x: natsorted(x))
        logging.info("\n=== 发票处理详情 ===")
        logging.info("成功处理的发票：")
        for _, row in unique_invoices.iterrows():
            logging.info(f"文件路径: {row['路径']}, 发票号: {row['发票号']}, 金额: {row['总金额']:.2f}")
        
        # 打印重复的发票信息
        duplicate_invoices = valid_invoices[valid_invoices.duplicated(subset=['发票号'], keep=False)]
        if not duplicate_invoices.empty:
            logging.info("\n重复的发票：")
            for _, row in duplicate_invoices.iterrows():
                logging.info(f"文件路径: {row['路径']}, 发票号: {row['发票号']}, 金额: {row['总金额']:.2f}")
        
        # 只打印仍然失败的发票
        remaining_failed_files = set(failed_files) - set(valid_invoices['路径'])
        if remaining_failed_files:
            logging.info("\n处理失败的发票：")
            for file in remaining_failed_files:
                logging.info(f"文件路径: {file}")
        
        logging.info(f"\n总计：处理了 {len(result_df)} 张发票，中 {len(unique_invoices)} 张有效发票")
        
        # 如果还有失败文件，则记录它们
        if failed_files:
            failed_files_path = 'failed_invoices.txt'
            with open(failed_files_path, 'w', encoding='utf-8') as f:
                for file in failed_files:
                    f.write(f"{file}\n")
            logging.info(f"失败文件列表已存到: {failed_files_path}")
        else:
            logging.info("所有文件处理成功！")
            
    except Exception as e:
        logging.error(f"处理过程中出现错误: {str(e)}")

if __name__ == "__main__":
    main() 