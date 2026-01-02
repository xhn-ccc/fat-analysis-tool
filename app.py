import streamlit as st
import pandas as pd

# ==========================================
# 1. 核心数据：内置的标准品出峰时间表
# ==========================================
def get_standard_data():
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
# 2. 核心逻辑：智能读取文件 (带表头探测)
# ==========================================
def load_data_smart(uploaded_file):
    try:
        # A. 初步读取前10行
        if uploaded_file.name.endswith('.csv'):
            try:
                df_temp = pd.read_csv(uploaded_file, header=None, nrows=10)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df_temp = pd.read_csv(uploaded_file, header=None, nrows=10, encoding='gbk')
        else:
            df_temp = pd.read_excel(uploaded_file, header=None, nrows=10)
        
        # B. 寻找表头
        best_header_idx = 0
        max_matches = 0
        keywords = ['时间', 'Time', 'time', '面积', 'Area', 'area']
        
        for i in range(min(5, len(df_temp))):
            row_str = " ".join(df_temp.iloc[i].astype(str).tolist())
            matches = sum(1 for k in keywords if k in row_str)
            if matches > max_matches:
                max_matches = matches
                best_header_idx = i
        
        # C. 重新读取
        uploaded_file.seek(0)
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

# ==========================================
# 3. 新核心算法：基准峰校正匹配
# ==========================================
def calculate_shift_and_match(df_sample, time_col, area_col, std_df, tolerance):
    """
    1. 找到 C14:0 (基准)
    2. 计算整体偏移
    3. 匹配其余所有峰
    """
    results = df_sample.copy()
    
    # --- Step 1: 寻找基准峰 C14:0 ---
    # C14的标准时间
    c14_std_time = std_df[std_df['fatty acid'] == 'C14:0']['std_time'].values[0]
    
    # 在标准时间 ± 1.0 分钟范围内寻找
    # 这里范围可以大一点，因为我们还要看面积最大
    search_window = 1.5 
    
    # 筛选出在 C14 附近的峰
    candidates = df_sample[
        (df_sample[time_col] >= c14_std_time - search_window) & 
        (df_sample[time_col] <= c14_std_time + search_window)
    ]
    
    shift = 0.0
    found_c14 = False
    c14_actual_time = 0.0
    
    if not candidates.empty:
        # 如果指定了面积列，找面积最大的；否则找时间最近的
        if area_col and area_col in df_sample.columns:
            # 按面积降序排列，取第一个
            best_c14 = candidates.sort_values(by=area_col, ascending=False).iloc[0]
        else:
            # 没选面积列，只能找时间最接近的（风险较大，但作为兜底）
            candidates['temp_diff'] = (candidates[time_col] - c14_std_time).abs()
            best_c14 = candidates.sort_values(by='temp_diff').iloc[0]
            
        c14_actual_time = best_c14[time_col]
        shift = c14_actual_time - c14_std_time # 计算偏移量 (正数代表整体偏晚)
        found_c14 = True
    
    # --- Step 2: 定义单行匹配函数 ---
    def match_row(row_time):
        # 如果没找到基准，shift就是0，相当于回退到原始匹配
        # 校正后的标准时间 = 原始标准 + 偏移量
        # 我们要找一个标准脂肪酸，使得 (std_time + shift) 与 row_time 最接近
        
        current_std = std_df.copy()
        current_std['calibrated_time'] = current_std['std_time'] + shift
        current_std['diff'] = (current_std['calibrated_time'] - row_time).abs()
        
        # 找差异最小的
        closest = current_std.loc[current_std['diff'].idxmin()]
        
        if closest['diff'] <= tolerance:
            return closest['fatty acid'], closest['diff']
        else:
            return "未知", closest['diff']

    # --- Step 3: 应用匹配 ---
    matched_names = []
    diffs = []
    
    for t in df_sample[time_col]:
        name, diff = match_row(t)
        matched_names.append(name)
        diffs.append(diff)
        
    results['匹配结果'] = matched_names
    # results['偏差值'] = diffs # 调试用，可以注释掉
    
    return results, found_c14, shift, c14_actual_time

# ==========================================
# 4. Streamlit 界面
# ==========================================

st.set_page_config(page_title="脂肪酸智能校正工具", layout="wide")

st.title("🧪 脂肪酸自动识别 (基准峰校正版)")
st.caption("逻辑升级：自动寻找 C14:0 最高峰作为基准，计算整体时间漂移，再匹配其他物质。")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 参数设置")
    tolerance = st.slider("⏱️ 判定容差 (分钟)", 0.05, 0.5, 0.2, 0.01, help="即使经过校正，如果差距还是超过这个值，则判为未知")
    st.divider()
    st.markdown("### 📌 标准参考 (未校正)")
    std_df = get_standard_data()
    st.dataframe(std_df, hide_index=True, use_container_width=True)

# --- 主区域 ---
uploaded_file = st.file_uploader("📂 请上传待测样品数据", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    df_sample, msg = load_data_smart(uploaded_file)
    
    if df_sample is None:
        st.error(f"读取失败: {msg}")
    else:
        st.write("### 1. 数据预览")
        st.dataframe(df_sample.head())
        
        # 列选择
        valid_cols = [c for c in df_sample.columns if "Unnamed" not in str(c)]
        
        c1, c2 = st.columns(2)
        # 智能选时间列
        t_idx = next((i for i, c in enumerate(valid_cols) if "时间" in str(c) or "Time" in str(c)), 0)
        time_col = c1.selectbox("【保留时间】列 (必选)", valid_cols, index=t_idx)
        
        # 智能选面积列 (现在是找基准峰的关键)
        a_idx = next((i for i, c in enumerate(valid_cols) if "面积" in str(c) or "Area" in str(c)), 0)
        area_col = c2.selectbox("【峰面积】列 (强烈建议选)", [None]+valid_cols, index=a_idx+1 if a_idx is not None else 0)

        if st.button("🚀 开始校正并识别", type="primary"):
            # 数据清洗
            work_df = df_sample.copy()
            work_df[time_col] = pd.to_numeric(work_df[time_col], errors='coerce')
            if area_col:
                work_df[area_col] = pd.to_numeric(work_df[area_col], errors='coerce')
            work_df = work_df.dropna(subset=[time_col])
            
            # === 调用新逻辑 ===
            final_df, found_c14, shift, c14_time = calculate_shift_and_match(
                work_df, time_col, area_col, std_df, tolerance
            )
            
            # === 结果反馈区 ===
            st.divider()
            st.write("### 2. 校正报告")
            
            res_col1, res_col2, res_col3 = st.columns(3)
            if found_c14:
                res_col1.metric("基准峰 (C14:0)", "✅ 已定位")
                res_col2.metric("基准实际出峰", f"{c14_time:.3f} min")
                
                # 根据偏移量显示不同颜色
                shift_display = f"{shift:+.3f} min"
                res_col3.metric("系统整体偏移", shift_display, delta_color="inverse")
                
                st.info(f"💡 分析：检测到 C14:0 实际出峰比标准偏了 **{shift:.3f} 分钟**。系统已自动将所有标准参考时间调整了此数值，然后进行最近匹配。")
            else:
                res_col1.metric("基准峰 (C14:0)", "❌ 未找到")
                st.warning("⚠️ 警告：在 11.972 ± 1.5 min 范围内未找到有效的 C14:0 峰（或未选择面积列导致无法判断最高峰）。系统将使用 **原始标准时间** 进行强制匹配，准确率可能下降。")
            
            # === 展示结果 ===
            st.write("### 3. 详细识别表")
            
            # 整理列顺序
            cols = [time_col, '匹配结果']
            if area_col: cols.append(area_col)
            
            # 样式
            def highlight(val):
                if val == "C14:0": return 'background-color: lightblue; font-weight: bold' # 基准峰标蓝
                if val == "未知": return 'color: gray'
                return 'background-color: lightgreen'

            st.dataframe(
                final_df[cols].style.map(highlight, subset=['匹配结果']), 
                use_container_width=True
            )
            
            # 下载
            out_csv = final_df[cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载校正后的结果", out_csv, f"校正结果_{uploaded_file.name}.csv", "text/csv")
