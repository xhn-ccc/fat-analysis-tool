import streamlit as st
import pandas as pd


# ==========================================
# 1. 核心数据：内置的标准品出峰时间表
# ==========================================
def get_standard_data():
    """
    直接返回固定的标准品数据，无需用户上传
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
# 2. 核心逻辑：根据时间匹配名字
# ==========================================
def match_peak_name(sample_time, std_df, tolerance=0.2):
    """
    sample_time: 待测样品的出峰时间
    std_df: 标准品数据表
    tolerance: 时间误差窗口（分钟），默认 ±0.2 分钟
    """
    # 计算待测时间与所有标准时间的差值的绝对值
    std_df['diff'] = (std_df['std_time'] - sample_time).abs()

    # 找到差异最小的那一行
    closest_match = std_df.loc[std_df['diff'].idxmin()]

    # 如果差异小于设定的容差，就认为匹配成功
    if closest_match['diff'] <= tolerance:
        return closest_match['fatty acid']
    else:
        return "未知/未匹配"


# ==========================================
# 3. Streamlit 页面布局
# ==========================================

st.set_page_config(page_title="脂肪酸自动识别工具", layout="wide")

st.title("🧪 脂肪酸峰自动识别工具 (内置标准版)")

# --- 侧边栏：设置与参考 ---
with st.sidebar:
    st.header("⚙️ 参数设置")

    # 容差设置：很重要，因为机器每次跑可能会有微小的时间漂移
    tolerance = st.slider(
        "⏱️ 匹配时间窗口 (分钟)",
        min_value=0.01,
        max_value=1.0,
        value=0.3,
        step=0.01,
        help="如果待测样品的出峰时间在 标准时间 ± 这个数值 范围内，则判定匹配成功。"
    )

    st.divider()

    st.markdown("### 📌 当前内置标准参考")
    std_df = get_standard_data()
    st.dataframe(std_df, hide_index=True, use_container_width=True)

# --- 主区域：上传待测样品 ---
st.info(f"💡 说明：无需上传标准表，只需上传待测样品数据。当前匹配时间容差为：±{tolerance} 分钟")

uploaded_file = st.file_uploader("📂 请上传待测样品数据 (Excel 或 CSV)", type=['xlsx', 'xls', 'csv'])

if uploaded_file:
    try:
        # 读取文件
        if uploaded_file.name.endswith('.csv'):
            df_sample = pd.read_csv(uploaded_file)
        else:
            df_sample = pd.read_excel(uploaded_file)

        st.write("### 1. 数据预览 (前5行)")
        st.dataframe(df_sample.head())

        # --- 让用户选择列名 (防止用户上传的文件列名不一样) ---
        col1, col2 = st.columns(2)
        with col1:
            time_col = st.selectbox("请选择代表【保留时间/Time】的列：", df_sample.columns)
        with col2:
            # 如果有峰面积列，也可以选上，方便后续展示
            area_col = st.selectbox("请选择代表【峰面积/Area】的列 (可选)：", [None] + list(df_sample.columns))

        if st.button("🚀 开始匹配识别", type="primary"):
            # 执行匹配
            results = df_sample.copy()

            # 使用 apply 函数应用匹配逻辑
            results['匹配结果 (Fatty Acid)'] = results[time_col].apply(
                lambda x: match_peak_name(x, std_df.copy(), tolerance)
            )

            # 整理显示列的顺序
            cols_to_show = [time_col, '匹配结果 (Fatty Acid)']
            if area_col:
                cols_to_show.append(area_col)
            # 把剩下的列也放后面
            remaining_cols = [c for c in results.columns if c not in cols_to_show]
            final_cols = cols_to_show + remaining_cols

            results = results[final_cols]

            st.success("✅ 匹配完成！")

            # --- 展示结果 ---
            st.write("### 2. 识别结果")


            # 高亮显示“未知”的数据，方便检查
            def highlight_unknown(val):
                color = 'salmon' if val == "未知/未匹配" else 'lightgreen'
                return f'background-color: {color}'


            st.dataframe(
                results.style.map(highlight_unknown, subset=['匹配结果 (Fatty Acid)']),
                use_container_width=True
            )

            # --- 下载按钮 ---
            csv = results.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下载处理后的结果 (CSV)",
                data=csv,
                file_name=f"识别结果_{uploaded_file.name}.csv",
                mime='text/csv',
            )

    except Exception as e:
        st.error(f"❌ 读取文件出错，请检查文件格式: {e}")
