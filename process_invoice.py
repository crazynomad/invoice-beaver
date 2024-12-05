#!/usr/bin python3
# -*- coding:UTF-8 -*-
import pandas as pd
import logging
from pathlib import Path
from invoice_extractor import InvoiceExtractor

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
    try:
        # 读取CSV文件
        df = pd.read_csv('output.csv')
        
        # 第一次处理
        current_source = None
        for _, row in df.iterrows():
            if current_source != row['source']:
                processor.finalize_invoice()
                current_source = row['source']
            processor.process_line(row['text'], row['source'])
        
        processor.finalize_invoice()

        # 对失败的文件进行二次处理
        if processor.failed_files:
            logging.info("\n=== 开始二次处理失败的文件 ===")
            retry_success = []
            for failed_file in processor.failed_files[:]:  # 使用切片创建副本
                # 获取该文件的所有文本行
                text_lines = df[df['source'] == failed_file]['text'].tolist()
                if processor.second_pass_process(failed_file, text_lines):
                    retry_success.append(failed_file)
                    processor.failed_files.remove(failed_file)
            
            if retry_success:
                logging.info(f"\n二次处理成功数量: {len(retry_success)}")
                logging.info("二次处理成功的文件:")
                for file in retry_success:
                    logging.info(f"- {file}")

        # 创建结果DataFrame
        result_df = pd.DataFrame(processor.invoices)
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