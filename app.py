import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. 核心处理函数
# ==========================================

def match_fatty_acid(rt, mapping_dict, tolerance=0.2):
    """
    根据保留时间 (RT) 匹配脂肪酸名称。
    tolerance: 容差范围（分钟），默认 +/- 0.2 分钟
    """
    for name, standard_rt in mapping_dict.items():
        if abs(rt - standard_rt) <= tolerance:
            return name
    return None

def process_chromatography_data(df, mapping_dict, tolerance):
    """
    处理特殊格式的色谱数据：
    Row 0: 样品名 (1, 2, 3...)
    Row 1: 标题 (出峰时间, 面积...)
    Row 2+: 数据
    """
    # 最终结果容器
    final_results = pd.DataFrame()

    # 遍历每两列（假设格式是：Time, Area, Time, Area...）
    # df.shape[1] 是列数
    for i in range(0, df.shape[1], 2):
        if i + 1 >= df.shape[1]:
            break
            
        # 1. 获取样品名称 (第一行)
        sample_name = df.iloc[0, i]
        if pd.isna(sample_name):
            sample_name = f"Sample_{i//2 + 1}"
        
        # 2. 获取该样品的数据 (Time列 和 Area列)
        # 从第3行开始是数据 (索引2)
        sub_df = df.iloc[2:, i:i+2].copy()
        sub_df.columns = ['Time', 'Area']
        
        # 强制转为数字，出错变成 NaN，然后丢弃空行
        sub_df['Time'] = pd.to_numeric(sub_df['Time'], errors='coerce')
        sub_df['Area'] = pd.to_numeric(sub_df['Area'], errors='coerce')
        sub_df = sub_df.dropna()
        
        if sub_df.empty:
            continue

        # 3. 匹配脂肪酸名称 (Mapping)
        # apply 函数对每一行执行 match_fatty_acid
        sub_df['Name'] = sub_df['Time'].apply(lambda t: match_fatty_acid(t, mapping_dict, tolerance))
        
        # 4. 过滤：去掉未匹配到 (Unknown) 的行
        # dropna(subset=['Name']) 会删掉那些 Name 是 None 的行
        filtered_df = sub_df.dropna(subset=['Name'])
        
        if filtered_df.empty:
            # 如果该样品没有匹配到任何已知物，填空
            continue

        # 5. 聚合：同名合并，面积相加
        aggregated = filtered_df.groupby('Name')['Area'].sum().reset_index()
        
        # 6. 计算百分比
        total_area = aggregated['Area'].sum()
        aggregated['Percentage'] = (aggregated['Area'] / total_area) * 100
        
        # 7. 整理格式以便合并
        # 将 Name 设为索引，Series 名字设为样品名
        sample_series = aggregated.set_index('Name')['Percentage']
        sample_series.name = sample_name
        
        # 合并到总表
        if final_results.empty:
            final_results = pd.DataFrame(sample_series)
        else:
            final_results = final_results.join(sample_series, how='outer')

    # 填充 NaN 为 0 (某些样品可能没检测到某种脂肪酸)
    final_results = final_results.fillna(0)
    
    # 按照索引(脂肪酸名称)排序，或者你可以按 mapping_dict 的顺序排序
    return final_results

# ==========================================
# 2. Streamlit 界面
# ==========================================

st.set_page_config(page_title="脂肪酸数据自动处理", layout="wide")

st.title("🧪 脂肪酸 GC 数据自动处理工具")
st.markdown("""
**功能：**
1. 上传原始 Excel (多样品排版)。
2. **自动剔除**未知物。
3. **自动合并**同名峰面积。
4. **自动计算**相对百分含量。
""")

# --- 侧边栏：设置标准品时间 ---
st.sidebar.header("⚙️ 参数设置")

st.sidebar.subheader("1. 脂肪酸对应表 (名称 : 保留时间)")
st.sidebar.info("请在此处修改标准品的保留时间。只有在此列表中的峰会被保留。")

# 默认数据 (基于你提供的数据示例猜测)
default_mapping = """C14:0 : 3.4
C16:0 : 4.93
C16:1 : 5.3
C18:0 : 7.56
C18:1 : 6.93
C18:2 : 8.25
C18:3 : 9.25
C20:0 : 9.9
C20:1 : 10.2"""

mapping_input = st.sidebar.text_area("格式：名称 : 时间 (每行一个)", value=default_mapping, height=250)

# 解析用户输入的 Mapping
mapping_dict = {}
for line in mapping_input.split('\n'):
    if ':' in line:
        parts = line.split(':')
        name = parts[0].strip()
        try:
            time_val = float(parts[1].strip())
            mapping_dict[name] = time_val
        except:
            pass

tolerance = st.sidebar.slider("时间匹配容差 (±分钟)", 0.01, 0.5, 0.15)

# --- 主界面：文件上传 ---
st.subheader("1. 上传数据文件")
uploaded_file = st.file_uploader("上传 Excel 文件 (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        # 读取 Excel，header=None 因为我们要自己处理前两行
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        st.write("原始数据预览 (前 5 行):")
        st.dataframe(df_raw.head())
        
        # --- 开始处理 ---
        if st.button("开始自动处理", type="primary"):
            with st.spinner('正在清洗数据、匹配峰位、计算百分比...'):
                result_df = process_chromatography_data(df_raw, mapping_dict, tolerance)
            
            st.success("处理完成！")
            
            st.subheader("2. 处理结果 (百分比 %)")
            st.dataframe(result_df.style.format("{:.2f}"))
            
            # --- 下载按钮 ---
            output = io.BytesIO()
            # 将结果写入 Excel
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, sheet_name='Result_Percentage')
            
            st.download_button(
                label="📥 下载最终结果 Excel",
                data=output.getvalue(),
                file_name="脂肪酸分析结果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"发生错误: {e}")
        st.info("请检查上传的文件格式是否正确（第一行为样品名，第二行为Time/Area...）")
