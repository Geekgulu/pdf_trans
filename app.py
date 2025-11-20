import os
import tempfile
import subprocess
import shutil
from pathlib import Path
from dotenv import load_dotenv
from pdf_translator import PDFTranslator
import streamlit as st
import sys

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
    ["中文", "英语", "日语", "韩语", "印度尼西亚语", "泰语", "阿拉伯语", "马来语"],
    index=0
)
lang_code_map = {
    "中文": "zh",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "印度尼西亚语": "id",
    "泰语": "th",
    "阿拉伯语": "ar",
    "马来语": "ms"
}
lang_code = lang_code_map.get(target_language, "zh")

# 添加对照翻译选项
show_comparison = st.checkbox("📋 显示原文和译文对照", value=True, help="选中后，输出的文档将同时显示原文和译文，方便对比检查翻译质量")
preserve_layout = st.checkbox("🧩 保持原版式排版", value=True, help="对PDF使用保版式引擎生成译文；DOCX将先转换为PDF后处理")

def _find_pdf2zh():
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools', 'pdf2zh', 'pdf2zh.exe')
    if os.path.exists(local_path):
        return local_path
    venv_path = os.path.join(sys.prefix, 'Scripts', 'pdf2zh.exe')
    if os.path.exists(venv_path):
        return venv_path
    cmd = shutil.which('pdf2zh')
    if cmd:
        return cmd
    return None

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

    if preserve_layout:
        output_suffix = '.pdf'
        mime_type = "application/pdf"
    
    # 翻译按钮
    if st.button("🚀 开始翻译", type="primary"):
        try:
            progress = st.progress(0)
            status = st.empty()
            status.text("正在准备...")
            progress.progress(0.05)
            # 创建临时文件保存上传的文档
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_path = temp_file.name
            progress.progress(0.1)

            if preserve_layout:
                input_pdf_path = None
                cleanup_paths = []
                if file_type == 'pdf':
                    input_pdf_path = temp_path
                elif file_type == 'docx':
                    status.text("正在转换为PDF...")
                    pdf_temp_dir = tempfile.mkdtemp()
                    pdf_temp_path = os.path.join(pdf_temp_dir, f"{Path(uploaded_file.name).stem}.pdf")
                    converted = False
                    try:
                        from docx2pdf import convert as docx2pdf_convert
                        docx2pdf_convert(temp_path, pdf_temp_path)
                        converted = os.path.exists(pdf_temp_path)
                    except Exception:
                        pass
                    if not converted:
                        try:
                            import win32com.client as win32
                            word = win32.DispatchEx('Word.Application')
                            doc = word.Documents.Open(temp_path)
                            doc.ExportAsFixedFormat(pdf_temp_path, 17)
                            doc.Close()
                            word.Quit()
                            converted = os.path.exists(pdf_temp_path)
                        except Exception:
                            pass
                    if not converted:
                        soffice = shutil.which('soffice') or shutil.which('libreoffice')
                        if soffice:
                            try:
                                r = subprocess.run([soffice, '--headless', '--convert-to', 'pdf', '--outdir', pdf_temp_dir, temp_path], capture_output=True, text=True)
                                converted_path = os.path.join(pdf_temp_dir, f"{Path(temp_path).stem}.pdf")
                                if os.path.exists(converted_path):
                                    pdf_temp_path = converted_path
                                    converted = True
                            except Exception:
                                pass
                    if converted:
                        input_pdf_path = pdf_temp_path
                        cleanup_paths.append(pdf_temp_path)
                        progress.progress(0.3)
                    else:
                        st.warning("DOCX转换为PDF失败，已回退为普通翻译输出")
                if input_pdf_path:
                    out_dir = tempfile.mkdtemp()
                    pdf2zh_cmd = _find_pdf2zh() or 'pdf2zh'
                    run_cmd = [pdf2zh_cmd, input_pdf_path, '-lo', lang_code, '-o', out_dir]
                    try:
                        status.text("正在使用保版式引擎翻译...")
                        progress.progress(0.7)
                        result = subprocess.run(run_cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            base = Path(input_pdf_path).stem
                            dual_path = os.path.join(out_dir, f"{base}-dual.pdf")
                            mono_path = os.path.join(out_dir, f"{base}-mono.pdf")
                            chosen_path = None
                            if show_comparison and os.path.exists(dual_path):
                                chosen_path = dual_path
                            elif os.path.exists(mono_path):
                                chosen_path = mono_path
                            else:
                                candidates = [p for p in [dual_path, mono_path] if os.path.exists(p)]
                                if candidates:
                                    chosen_path = candidates[0]
                            if chosen_path and os.path.exists(chosen_path):
                                with open(chosen_path, 'rb') as f:
                                    translated_doc = f.read()
                                progress.progress(0.95)
                                st.success("✅ 翻译完成！")
                                dl_name = f"translated_{Path(uploaded_file.name).stem}.pdf"
                                st.download_button(label="📥 下载翻译结果", data=translated_doc, file_name=dl_name, mime="application/pdf")
                                cleanup_paths.append(chosen_path)
                                progress.progress(1.0)
                            else:
                                st.warning("未找到保版式输出文件，已回退为普通翻译输出")
                        else:
                            st.warning("保版式引擎执行失败，已回退为普通翻译输出")
                    except Exception:
                        st.warning("保版式引擎不可用，已回退为普通翻译输出")
                    finally:
                        try:
                            shutil.rmtree(out_dir)
                        except Exception:
                            pass
                if not input_pdf_path or 'translated_doc' not in locals():
                    status.text("正在回退到普通翻译流程...")
                    output_path = tempfile.mktemp(suffix=('.pdf' if file_type == 'pdf' else '.docx'))
                    translator = PDFTranslator()
                    translator.translate_document(temp_path, output_path, target_language, show_comparison=show_comparison, file_type=file_type)
                    with open(output_path, 'rb') as file:
                        translated_doc = file.read()
                    progress.progress(0.95)
                    st.success("✅ 翻译完成！")
                    dl_name = f"translated_{uploaded_file.name}"
                    st.download_button(label="📥 下载翻译结果", data=translated_doc, file_name=dl_name, mime=("application/pdf" if file_type == 'pdf' else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
                    try:
                        os.unlink(output_path)
                    except Exception:
                        pass
                    progress.progress(1.0)
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                for p in cleanup_paths:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(os.path.dirname(cleanup_paths[0]))
                except Exception:
                    pass
            else:
                status.text("正在进行普通翻译...")
                output_path = tempfile.mktemp(suffix=output_suffix)
                translator = PDFTranslator()
                translator.translate_document(
                    temp_path,
                    output_path,
                    target_language,
                    show_comparison=show_comparison,
                    file_type=file_type
                )
                with open(output_path, 'rb') as file:
                    translated_doc = file.read()
                progress.progress(0.95)
                st.success("✅ 翻译完成！")
                st.download_button(
                    label="📥 下载翻译结果",
                    data=translated_doc,
                    file_name=f"translated_{uploaded_file.name}",
                    mime=mime_type
                )
                progress.progress(1.0)
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                try:
                    os.unlink(output_path)
                except Exception:
                    pass

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
    st.markdown("**支持的文件格式:** PDF、Word文档(.docx)")
    st.markdown("**使用语言:** 中文、英语、日语、韩语、印度尼西亚语、泰语、阿拉伯语、马来语")
    st.markdown("---")
    st.header("🧩 保版式引擎状态")
    engine_path = _find_pdf2zh()
    if engine_path:
        st.success(f"已检测到保版式引擎: {engine_path}")
    else:
        st.warning("未检测到保版式引擎（pdf2zh）")
    # 转换能力检测
    has_docx2pdf = False
    try:
        import docx2pdf  # noqa: F401
        has_docx2pdf = True
    except Exception:
        has_docx2pdf = False
    soffice = shutil.which('soffice') or shutil.which('libreoffice')
    st.caption(f"DOCX→PDF: docx2pdf={'✅' if has_docx2pdf else '❌'}, Word COM={'✅' if os.name=='nt' else '❌'}, LibreOffice={'✅' if bool(soffice) else '❌'}")