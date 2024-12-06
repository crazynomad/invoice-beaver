import os
import subprocess

# 获取 conda 环境的 Python 路径
conda_env = "invoice"
python_path = subprocess.check_output(f"conda run -n {conda_env} which python", shell=True).decode().strip()

# 构建环境变量
env = os.environ.copy()
env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))

# 运行 streamlit
subprocess.run([python_path, "-m", "streamlit", "run", "invoice_app.py"], env=env) 