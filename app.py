import streamlit as st
import pandas as pd
import numpy as np
import io
import zipfile


# ==========================================
# 核心处理逻辑 (从你的脚本重构)
# ==========================================

def process_single_dataframe(sample_df, filename, ref_df, window_size=0.15, base_fa='C14:0'):
    """
    处理单个 DataFrame 数据
    """
    # 标准化列名（防止大小写问题）
    sample_df.columns = [c.lower() for c in sample_df.columns]

    # 检查必要列
    if 'rt' not in sample_df.columns or 'area' not in sample_df.columns:
        return None, f"文件 {filename} 缺少 'rt' 或 'area' 列"

    # 数据类型转换
    sample_df['rt'] = pd.to_numeric(sample_df['rt'], errors='coerce')
    sample_df['area'] = pd.to_numeric(sample_df['area'], errors='coerce')
    sample_df = sample_df.fillna(0)

    # 1. 寻找基准脂肪酸 (Base Fatty Acid)
    ref_base = ref_df[ref_df['fatty_acid'] == base_fa]
    if ref_base.empty:
        return None, f"参考表中未找到基准脂肪酸: {base_fa}"

    rt_ref_base = float(ref_base['rt_ref'].iloc[0])

    # 在样本中找最接近 rt_ref_base 的峰
    if sample_df.empty:
        return None, f"文件 {filename} 内容为空"

    idx_base = (sample_df['rt'] - rt_ref_base).abs().idxmin()
    rt_act_base = float(sample_df.loc[idx_base, 'rt'])
    delta = rt_act_base - rt_ref_base

    # 2. 逐个匹配
    results = []
    for _, r in ref_df.iterrows():
        fa = r['fatty_acid']
        rt_ref = float(r['rt_ref'])
        center = rt_ref + delta

        # 找 window_size 范围内的所有峰
        df_win = sample_df[np.abs(sample_df['rt'] - center) <= window_size]

        if df_win.empty:
            area_sum = np.nan
            rt_act = np.nan
        else:
            area_sum = float(df_win['area'].sum())
            idx_best = (df_win['rt'] - center).abs().idxmin()
            rt_act = float(sample_df.loc[idx_best, 'rt'])

        results.append({
            'fatty_acid': fa,
            'rt_ref': rt_ref,
            'rt_actual': rt_act,
            'area_sum': area_sum
        })

    return pd.DataFrame(results), None


# ==========================================
# Streamlit 界面代码
# ==========================================

st.set_page_config(page_title="气相色谱脂肪酸匹配工具", layout="wide")

st.title("⚗️ 气相色谱脂肪酸数据自动筛选工具")
st.markdown("""
上传 **标准参考表 (ref.csv)** 和 **气相色谱原始数据**，系统将自动根据保留时间(RT)进行峰匹配和面积积分。
""")

# --- 侧边栏配置 ---
st.sidebar.header("⚙️ 参数设置")
window_size = st.sidebar.number_input("匹配窗口大小 (min)", min_value=0.01, value=0.15, step=0.01, format="%.2f")
base_fa = st.sidebar.text_input("基准脂肪酸名称 (用于校正偏移)", value="C14:0")

st.sidebar.markdown("---")
st.sidebar.info("说明：系统会根据基准脂肪酸计算整体时间偏移量，然后在固定窗口内寻找对应峰并计算面积总和。")

# --- 文件上传 ---
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. 上传参考表")
    ref_file = st.file_uploader("上传 ref.csv (包含 fatty_acid, rt_ref)", type=['csv'])

with col2:
    st.subheader("2. 上传样本数据")
    sample_files = st.file_uploader("上传样本文件 (.xlsx, .xls, .csv)", type=['xlsx', 'xls', 'csv'],
                                    accept_multiple_files=True)

# --- 处理逻辑 ---
if st.button("🚀 开始处理", type="primary"):
    if not ref_file:
        st.error("❌ 请先上传参考表 (ref.csv)")
    elif not sample_files:
        st.error("❌ 请至少上传一个样本文件")
    else:
        # 读取参考表
        try:
            ref_df = pd.read_csv(ref_file)
            # 简单的列名检查
            if 'fatty_acid' not in ref_df.columns or 'rt_ref' not in ref_df.columns:
                st.error("❌ ref.csv 格式错误：必须包含 'fatty_acid' 和 'rt_ref' 列")
                st.stop()
        except Exception as e:
            st.error(f"❌ 读取参考表失败: {e}")
            st.stop()

        # 准备结果容器
        processed_files = []
        logs = []
        progress_bar = st.progress(0)

        # 内存中的 ZIP 文件
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for i, uploaded_file in enumerate(sample_files):
                # 更新进度条
                progress_bar.progress((i + 1) / len(sample_files))

                filename = uploaded_file.name
                ext = filename.split('.')[-1].lower()

                try:
                    # 读取样本文件
                    if ext == 'csv':
                        sample_df = pd.read_csv(uploaded_file)
                    else:
                        sample_df = pd.read_excel(uploaded_file)

                    # 处理数据
                    result_df, error_msg = process_single_dataframe(
                        sample_df, filename, ref_df,
                        window_size=window_size, base_fa=base_fa
                    )

                    if error_msg:
                        logs.append(f"⚠️ {filename}: {error_msg}")
                    else:
                        logs.append(f"✅ {filename}: 处理成功")
                        # 将结果写入 ZIP
                        csv_buffer = result_df.to_csv(index=False, encoding='utf_8_sig')
                        zip_file.writestr(f"matched_{filename.rsplit('.', 1)[0]}.csv", csv_buffer)

                        # 仅展示第一个文件的结果作为预览
                        if len(processed_files) == 0:
                            preview_df = result_df
                            preview_name = filename

                        processed_files.append(filename)

                except Exception as e:
                    logs.append(f"❌ {filename}: 处理异常 - {str(e)}")

        # --- 结果展示 ---
        st.success(f"处理完成！成功处理 {len(processed_files)} / {len(sample_files)} 个文件。")

        # 显示日志
        with st.expander("查看处理日志"):
            for log in logs:
                st.text(log)

        # 如果有成功的文件，提供下载和预览
        if processed_files:
            st.markdown("---")
            st.subheader("3. 结果预览与下载")

            # 下载按钮
            st.download_button(
                label="📥 下载所有结果 (.zip)",
                data=zip_buffer.getvalue(),
                file_name="fatty_acid_results.zip",
                mime="application/zip"
            )

            st.write(f"**预览 ({preview_name}):**")
            st.dataframe(preview_df.style.format({"rt_ref": "{:.3f}", "rt_actual": "{:.3f}", "area_sum": "{:.1f}"}))