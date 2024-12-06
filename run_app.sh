#!/bin/bash
# 激活 conda 环境并运行应用
source ~/miniconda3/etc/profile.d/conda.sh
conda activate invoice
streamlit run invoice_app.py 