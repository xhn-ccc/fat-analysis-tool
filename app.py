import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. 核心数据：内置的标准品出峰时间表
# ==========================================
def get_standard_data():
    """
    直接返回固定的标准品数据
    """
    data = {
        'fatty acid': [
            'C14:0', 'C14:1', 'C16:0', 'C16:1', 'C18:0',
            'C18:1n-9', 'C18:1n-7', 'C18:2n-6(LA)', 'C18:3n-3(ALA)',
            'C18:4n-3', 'C20:0', 'C20:1n-9', 'C20:3n-3 ', 
            'C20:2n-6', 'C20:4n-3', 'C20:4n-6（ARA）', 'C20:5n-3  (EPA)',
            'C22:1n-11', 'C22:5n-3(DPA)', 'C22:6n-3(DHA)'
        ],
        'std_time': [
            11.972, 12.299, 14.611, 14.787, 16.261,
            17.251, 17.750, 18.400, 19.193, 20.675,
            21.056, 21.644, 22.668, 22.726, 23.544,
            23.811, 24.347, 26.737, 30.662, 31.955
        ]
    }
    return pd.DataFrame(data)

# ==========================================
# 2. 核心逻辑：智能读取文件 & 匹配
# ==========================================
def load_data_smart(uploaded_file):
    """
    智能读取文件：
    1. 自动处理 CSV 编码 (utf-8 / gbk)
    2. 自动寻找表头 (如果第一行不是列名，会自动往下找)
    """
    try:
        # --- 步骤A: 初步读取 ---
        # 这种读取方式不指定 header，先把前几行都读进来分析
        if uploaded_file.name.endswith('.csv'):
            try:
                # 尝试 UTF-8
                df_temp = pd.read_csv(uploaded_file, header=None, nrows=10)
            except UnicodeDecodeError:
                # 失败则尝试 GBK (中文常见)
                uploaded_file.seek(0)
                df_temp = pd.read_csv(uploaded_file, header=None, nrows=10, encoding='gbk')
        else:
            df_temp = pd.read_excel(uploaded_file, header=None, nrows=10)
        
        # --- 步骤B: 寻找最佳 Header 行 ---
        # 遍历前 5 行，看哪一行包含最多的关键词
        best_header_idx = 0
        max_matches = 0
        keywords = ['时间', 'Time', 'time', '面积', 'Area', 'area']
        
        for i in range(min(5, len(df_temp))):
            # 把这一行转成字符串，统计关键词出现的次数
            row_str = " ".join(df_temp.iloc[i].astype(str).tolist())
            matches = sum(1 for k in keywords if k in row_str)
            if matches > max_matches:
                max_matches = matches
                best_header_idx = i
        
        # --- 步骤C: 重新按正确的 Header 读取所有数据 ---
        uploaded_file.seek(0) # 重置文件指针
        
        if uploaded_file.name.endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file, header=best_header_idx)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, header=best_header_idx, encoding='gbk')
        else:
            df = pd.read_excel(uploaded_file, header=best_header_idx)
            
        return df, best_header_idx

    except Exception as e:
        return None, str(e)

def match_peak_name(sample_time, std_df, tolerance=0.2):
    """
    匹配逻辑
    """
    # 确保 sample_time 是数字，如果不是数字直接返回未知
    try:
        sample_time = float(sample_time)
    except:
        return "数据无效"

    std_df['diff'] = (std_df['std_time'] - sample_time).abs()
    closest_match = std_df.loc[std_df['diff'].idxmin()]
    
    if closest_match['diff'] <= tolerance:
        return closest_match['fatty acid']
    else:
        return "未知/未匹配"

# ==========================================
# 3. Streamlit 页面布局
# ==========================================

st.set_page_config(page_title="脂肪酸自动识别工具", layout="wide")

st.title("🧪 脂肪酸峰自动识别工具 (智能读取版)")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 参数设置")
    tolerance = st.slider("⏱️ 匹配时间窗口 (分钟)", 0.01, 1.0, 0.3, 0.01)
    st.divider()
    st.markdown("### 📌 内置标准参考")
    std_df = get_standard_data()
    st.dataframe(std_df, hide_index=True, use_container_width=True)

# --- 主区域 ---
uploaded_file = st.file_uploader("📂 请上传待测样品数据", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    # 调用智能读取
    df_sample, msg = load_data_smart(uploaded_file)
    
    if df_sample is None:
        st.error(f"❌ 读取文件失败: {msg}")
    else:
        # 如果跳过了行，提示一下用户
        if isinstance(msg, int) and msg > 0:
            st.info(f"💡 检测到复杂表头，已自动跳过前 {msg} 行，定位到有效数据。")
            
        st.write("### 1. 数据预览")
        st.dataframe(df_sample.head())
        
        # --- 列选择 ---
        # 过滤掉空的列名（有时候Excel会有很多Unnamed空列）
        valid_columns = [c for c in df_sample.columns if "Unnamed" not in str(c)]
        
        col1, col2 = st.columns(2)
        with col1:
            # 尝试自动选中包含“时间”的列
            default_time_idx = 0
            for i, col in enumerate(valid_columns):
                if "时间" in str(col) or "Time" in str(col):
                    default_time_idx = i
                    break
            time_col = st.selectbox("请选择【保留时间】列：", valid_columns, index=default_time_idx)
            
        with col2:
            # 尝试自动选中包含“面积”的列
            default_area_idx = 0
            for i, col in enumerate(valid_columns):
                if "面积" in str(col) or "Area" in str(col):
                    default_area_idx = i
                    break
            area_col = st.selectbox("请选择【峰面积】列 (可选)：", [None] + valid_columns, index=default_area_idx+1 if default_area_idx else 0)

        if st.button("🚀 开始识别", type="primary"):
            # 数据清洗：确保时间列是数字
            process_df = df_sample.copy()
            
            # 强制将时间列转为数字，无法转换的变为 NaN (Coerce)
            process_df[time_col] = pd.to_numeric(process_df[time_col], errors='coerce')
            
            # 去除时间为空的行（比如单位行、空行）
            process_df = process_df.dropna(subset=[time_col])
            
            # 执行匹配
            process_df['匹配结果'] = process_df[time_col].apply(
                lambda x: match_peak_name(x, std_df.copy(), tolerance)
            )
            
            # 整理结果列
            cols = [time_col, '匹配结果']
            if area_col:
                cols.append(area_col)
            
            # 最终展示
            st.success("✅ 识别完成！")
            
            # 高亮函数
            def highlight(val):
                return 'background-color: salmon' if val == "未知/未匹配" else 'background-color: lightgreen'

            st.dataframe(
                process_df[cols].style.map(highlight, subset=['匹配结果']), 
                use_container_width=True
            )
            
            # 下载
            csv = process_df[cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载结果 CSV", csv, f"结果_{uploaded_file.name}.csv", "text/csv")
