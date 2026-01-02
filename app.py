import streamlit as st
import pandas as pd
import io

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
# 2. 核心算法：基准峰校正匹配 (保留你提供的逻辑)
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
    
    # 在标准时间 ± 1.5 分钟范围内寻找
    search_window = 1.5 
    
    candidates = df_sample[
        (df_sample[time_col] >= c14_std_time - search_window) & 
        (df_sample[time_col] <= c14_std_time + search_window)
    ]
    
    shift = 0.0
    found_c14 = False
    
    if not candidates.empty:
        # 找面积最大的作为 C14:0
        if area_col and area_col in df_sample.columns:
            best_c14 = candidates.sort_values(by=area_col, ascending=False).iloc[0]
        else:
            candidates['temp_diff'] = (candidates[time_col] - c14_std_time).abs()
            best_c14 = candidates.sort_values(by='temp_diff').iloc[0]
            
        c14_actual_time = best_c14[time_col]
        shift = c14_actual_time - c14_std_time # 计算偏移量
        found_c14 = True
    
    # --- Step 2: 定义单行匹配函数 ---
    def match_row(row_time):
        current_std = std_df.copy()
        # 核心：标准时间 + 偏移量 = 理论当前时间
        current_std['calibrated_time'] = current_std['std_time'] + shift
        current_std['diff'] = (current_std['calibrated_time'] - row_time).abs()
        
        closest = current_std.loc[current_std['diff'].idxmin()]
        
        if closest['diff'] <= tolerance:
            return closest['fatty acid']
        else:
            return "未知"

    # --- Step 3: 应用匹配 ---
    results['Name'] = results[time_col].apply(match_row)
    
    return results, found_c14, shift

# ==========================================
# 3. 批量处理逻辑 (新增：处理多样品 Excel)
# ==========================================
def process_batch_file(df_raw, std_df, tolerance):
    final_results = pd.DataFrame()
    log_messages = []

    # 遍历每两列 (假设格式: SampleName -> Time/Area -> Data)
    for i in range(0, df_raw.shape[1], 2):
        if i + 1 >= df_raw.shape[1]:
            break
            
        # 1. 获取样品名称 (Row 0)
        sample_name = df_raw.iloc[0, i]
        if pd.isna(sample_name):
            sample_name = f"Sample_{i//2 + 1}"
        
        # 2. 提取数据 (Row 2+)
        sub_df = df_raw.iloc[2:, i:i+2].copy()
        sub_df.columns = ['Time', 'Area']
        
        # 清洗数据
        sub_df['Time'] = pd.to_numeric(sub_df['Time'], errors='coerce')
        sub_df['Area'] = pd.to_numeric(sub_df['Area'], errors='coerce')
        sub_df = sub_df.dropna(subset=['Time', 'Area'])
        
        if sub_df.empty:
            continue

        # 3. 调用核心算法进行识别 (带漂移校正)
        matched_df, found_c14, shift = calculate_shift_and_match(
            sub_df, 'Time', 'Area', std_df, tolerance
        )
        
        # 记录日志
        status = f"✅ 偏移 {shift:+.3f}m" if found_c14 else "⚠️ 未找到基准(C14)"
        log_messages.append(f"**{sample_name}**: {status}")

        # 4. 过滤与聚合 (用户要求：去未知，合并同类，算面积)
        # 去掉 "未知"
        filtered_df = matched_df[matched_df['Name'] != '未知'].copy()
        
        if filtered_df.empty:
            continue
            
        # 合并同类项 (Sum Area)
        aggregated = filtered_df.groupby('Name')['Area'].sum().reset_index()
        
        # 5. 计算百分比
        total_area = aggregated['Area'].sum()
        aggregated['Percentage'] = (aggregated['Area'] / total_area) * 100
        
        # 6. 整理到总表
        sample_series = aggregated.set_index('Name')['Percentage']
        sample_series.name = sample_name
        
        if final_results.empty:
            final_results = pd.DataFrame(sample_series)
        else:
            final_results = final_results.join(sample_series, how='outer')

    # 填充 NaN 为 0，并按标准品顺序排序（可选）
    final_results = final_results.fillna(0)
    
    # 尝试按标准品列表的顺序排序索引
    standard_order = std_df['fatty acid'].tolist()
    final_results = final_results.reindex([x for x in standard_order if x in final_results.index])
    
    return final_results, log_messages

# ==========================================
# 4. Streamlit 界面
# ==========================================

st.set_page_config(page_title="脂肪酸批量全自动处理", layout="wide")

st.title("🧪 脂肪酸 GC 数据全自动处理")
st.markdown("""
**逻辑说明：**
1. **基准校正**：自动在 12min 左右寻找 **C14:0**，计算时间整体偏移量。
2. **智能匹配**：基于校正后的时间匹配其他脂肪酸。
3. **自动清洗**：剔除“未知”峰，合并同名脂肪酸，计算 **百分含量 (%)**。
""")

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 参数设置")
    tolerance = st.slider("⏱️ 判定容差 (分钟)", 0.05, 0.5, 0.20, help="即使校正后，时间差距超过此值仍视为未知")
    
    st.markdown("### 📌 标准参考时间")
    # 允许用户在界面上微调标准时间
    std_df_original = get_standard_data()
    edited_std_df = st.data_editor(std_df_original, num_rows="dynamic", use_container_width=True)

# --- 主区域 ---
uploaded_file = st.file_uploader("📂 上传 Excel 文件 (多样品格式)", type=['xlsx', 'xls'])

if uploaded_file:
    # 直接读取，header=None 方便我们处理第一行的样品名
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        st.write("### 1. 原始数据预览")
        st.dataframe(df_raw.head(3))
        
        if st.button("🚀 开始批量处理", type="primary"):
            with st.spinner("正在逐个样品进行：C14漂移校正 -> 峰匹配 -> 合并计算..."):
                # 调用处理函数
                result_df, logs = process_batch_file(df_raw, edited_std_df, tolerance)
            
            # 显示校正日志
            with st.expander("查看每个样品的校正情况 (C14检测结果)"):
                st.markdown("  \n".join(logs))
            
            st.success("处理完成！结果如下（单位：%）")
            
            # 显示结果
            st.write("### 2. 最终结果 (百分含量)")
            st.dataframe(result_df.style.format("{:.2f}"), use_container_width=True)
            
            # 下载按钮
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, sheet_name='Percentage_Result')
                # 也可以把原始面积放进去，如果需要的话
            
            st.download_button(
                label="📥 下载最终结果 Excel",
                data=output.getvalue(),
                file_name="脂肪酸分析结果_百分比.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"文件处理出错: {e}")
        st.warning("请确保上传的文件是 Excel 格式，且排版为：第一行样品名，下面是 Time/Area 两列一组。")
