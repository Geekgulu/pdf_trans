import os
import tempfile
from dotenv import load_dotenv
from pdf_translator import PDFTranslator
import streamlit as st

# 加载.env文件
load_dotenv()

# 页面配置
st.set_page_config(
    page_title="中软国际",
    page_icon="📄",
    layout="centered"
)

# 标题
st.title("📄 中软国际GBU 文档翻译工具")
st.markdown("---")

# 检查API密钥
api_key = os.getenv('DEEPSEEK_API_KEY')
if not api_key:
    st.error("⚠️ 请在.env文件中配置DEEPSEEK_API_KEY")
    st.stop()

# 文件上传
st.subheader("📤 上传文档")
uploaded_file = st.file_uploader(
    "选择文档文件",
    type=['pdf', 'docx'],
    help="支持PDF和Word文档格式"
)

# 语言选择
st.subheader("🌐 选择目标语言")
target_language = st.selectbox(
    "目标语言",
    ["中文", "English", "日本語", "한국어", "Bahasa Indonesia", "ภาษาไทย", "العربية", "Bahasa Melayu"],
    index=0
)

# 添加对照翻译选项
show_comparison = st.checkbox("📋 显示原文和译文对照", value=False, help="选中后，输出的文档将同时显示原文和译文，方便对比检查翻译质量")

if uploaded_file is not None:
    # 显示文件信息
    st.success(f"✅ 已上传文件: {uploaded_file.name}")
    st.info(f"📊 文件大小: {uploaded_file.size / 1024:.1f} KB")
    
    # 确定文件类型
    file_extension = uploaded_file.name.split('.')[-1].lower()
    if file_extension == 'pdf':
        file_type = 'pdf'
        output_suffix = '.pdf'
        mime_type = "application/pdf"
    elif file_extension == 'docx':
        file_type = 'docx'
        output_suffix = '.docx'
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        st.error("❌ 不支持的文件格式")
        st.stop()
    
    # 翻译按钮
    if st.button("🚀 开始翻译", type="primary"):
        try:
            # 创建临时文件保存上传的文档
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_path = temp_file.name

            # 创建临时文件用于保存翻译结果
            output_path = tempfile.mktemp(suffix=output_suffix)

            # 创建翻译器实例并执行翻译
            translator = PDFTranslator()
            translator.translate_document(
                temp_path, 
                output_path, 
                target_language, 
                show_comparison=show_comparison,
                file_type=file_type
            )
            
            # 读取翻译后的文件
            with open(output_path, 'rb') as file:
                translated_doc = file.read()

            # 提供下载按钮
            st.success("✅ 翻译完成！")
            st.download_button(
                label="📥 下载翻译结果",
                data=translated_doc,
                file_name=f"translated_{uploaded_file.name}",
                mime=mime_type
            )

            # 清理临时文件
            os.unlink(temp_path)
            os.unlink(output_path)

        except Exception as e:
            st.error(f"❌ 翻译失败: {str(e)}")

# 侧边栏信息
with st.sidebar:
    st.header("ℹ️ 使用说明")
    st.markdown("""
    1. 确保已配置API密钥
    2. 上传PDF或Word文档
    3. 选择目标语言
    4. 点击开始翻译
    5. 下载翻译结果
    """)
    
    st.header("⚙️ 配置")
    if api_key:
        st.success("✅ API密钥已配置")
    else:
        st.error("❌ API密钥未配置")
    
    st.markdown("---")
    st.markdown("**支持的文件格式:** PDF, Word文档(.docx)")
    st.markdown("**支持的语言:** 中文、英文、日文、韩文、印尼语、泰语、阿拉伯语、马来语")