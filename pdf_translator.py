import os
from typing import List, Tuple
from dotenv import load_dotenv
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import pdfplumber
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import streamlit as st
import tempfile
import docx
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import urllib.request
import zipfile
import shutil

class PDFTranslator:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.api_url = 'https://api.siliconflow.cn/v1/chat/completions'
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        # 确保字体目录存在
        self.fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
        if not os.path.exists(self.fonts_dir):
            os.makedirs(self.fonts_dir)

    def extract_text_from_pdf(self, pdf_path: str) -> List[Tuple[int, dict]]:
        """从PDF文件中提取文本、表格和图片，按段落返回内容"""
        content_by_page = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                # 创建文本提取进度条
                extract_progress = st.progress(0)
                extract_status = st.empty()
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    extract_status.text(f"正在提取第 {page_num}/{total_pages} 页...")
                    extract_progress.progress(page_num / total_pages)
                    
                    # 获取页面文本
                    text = page.extract_text() or ""
                    
                    # 使用更精确的段落分割方法
                    paragraphs = []
                    # 按两个或更多换行符分割段落
                    raw_paragraphs = text.split('\n\n')
                    
                    for para in raw_paragraphs:
                        para = para.strip()
                        if para:
                            paragraphs.append({
                                'text': para,
                                'bbox': None
                            })

                    page_content = {
                        "paragraphs": paragraphs,
                        "tables": page.extract_tables(),
                        "images": page.images
                    }
                    content_by_page.append((page_num, page_content))
                
                extract_status.text("文本提取完成！")
                extract_progress.progress(1.0)
                return content_by_page
                
        except Exception as e:
            raise Exception(f'PDF文件读取失败：{str(e)}')

    def translate_text(self, text: str, target_lang: str) -> str:
        """调用Deepseek API翻译文本"""
        if not isinstance(text, str):
            raise ValueError("输入的文本必须是字符串类型")
        if not text.strip():
            return ""  # 如果文本为空，直接返回空字符串

        system_prompt = f"""你是一个专业的翻译助手。请严格按照以下要求翻译文本：
1. 只输出翻译后的内容，不要添加任何解释、注释或说明
2. 保持原文的格式和段落结构
3. 翻译成{target_lang}
4. 不要输出"翻译如下"、"以下是翻译"等提示性文字
5. 不要添加任何括号内的解释或补充说明
6. 直接输出翻译结果，不要有任何前缀或后缀"""
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json={
                    'model': 'deepseek-ai/DeepSeek-V3',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'max_tokens': 1000,  # 限制最大 token 数，避免超出限制
                    'temperature': 0.3
                }
            )
            response.raise_for_status()
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            else:
                raise Exception("翻译API返回的结果格式不正确")
        except Exception as e:
            raise Exception(f'翻译请求失败：{str(e)}')

    def create_translated_pdf(self, original_pdf: str, original_texts: List[Tuple[int, dict]], 
                        translated_texts: List[Tuple[int, dict]], output_path: str, show_comparison: bool = True):
        """创建翻译后的PDF文件，支持原文译文对照"""
        try:
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            
            # 创建PDF文档
            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # 注册多语言字体
            font_name = self._register_fonts()
            
            # 创建样式
            styles = getSampleStyleSheet()
            original_style = ParagraphStyle(
                'OriginalText',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=11,
                leading=16,
                spaceAfter=6,
                alignment=0,  # 左对齐
                textColor='#666666'
            )
            translated_style = ParagraphStyle(
                'TranslatedText',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=12,
                leading=18,
                spaceAfter=12,
                alignment=0  # 左对齐
            )
            
            # 构建文档内容
            story = []
            
            for (orig_page, orig_content), (trans_page, trans_content) in zip(original_texts, translated_texts):
                # 处理段落
                for orig_para, trans_para in zip(orig_content["paragraphs"], trans_content["paragraphs"]):
                    if show_comparison:
                        # 添加原文
                        if orig_para["text"].strip():
                            story.append(Paragraph(orig_para["text"].strip(), original_style))
                        # 添加译文
                        if trans_para["text"].strip():
                            story.append(Paragraph(trans_para["text"].strip(), translated_style))
                    else:
                        # 仅显示译文
                        if trans_para["text"].strip():
                            story.append(Paragraph(trans_para["text"].strip(), translated_style))
                
                story.append(Spacer(1, 12))  # 段落间距

                # 添加表格
                for table in orig_content["tables"]:
                    table_data = [[Paragraph(cell or "", original_style) for cell in row] for row in table]
                    table_obj = Table(table_data)
                    table_obj.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                        ('FONTNAME', (0, 0), (-1, -1), font_name),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ]))
                    story.append(table_obj)
                    story.append(Spacer(1, 12))
                
                # 添加图片
                for image in orig_content["images"]:
                    img = Image(image["src"], width=inch, height=inch)
                    story.append(img)
                    story.append(Spacer(1, 12))
        
            # 生成PDF
            doc.build(story)
    
        except Exception as e:
            raise Exception(f'PDF文件创建失败：{str(e)}')
    
    def _register_fonts(self):
        """注册多语言字体，如果本地没有则自动下载"""
        # 字体文件路径
        font_paths = {
            'ArialUnicode': 'C:/Windows/Fonts/ARIALUNI.TTF',
            'NotoSans': 'C:/Windows/Fonts/NotoSans-Regular.ttf',
            'SimSun': 'C:/Windows/Fonts/simsun.ttc',
            'SimHei': 'C:/Windows/Fonts/simhei.ttf',
            'SourceHanSans': os.path.join(self.fonts_dir, 'SourceHanSansSC-Regular.otf')
        }
        
        # 尝试注册已有字体
        for font_name, font_path in font_paths.items():
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    return font_name
            except Exception as e:
                st.warning(f"注册字体 {font_name} 失败: {str(e)}")
                continue
        
        # 如果没有可用字体，下载并安装思源黑体
        try:
            source_han_path = font_paths['SourceHanSans']
            if not os.path.exists(source_han_path):
                st.info("正在下载思源黑体字体，请稍候...")
                # 下载思源黑体
                font_url = "https://github.com/adobe-fonts/source-han-sans/releases/download/2.004R/SourceHanSansSC.zip"
                zip_path = os.path.join(self.fonts_dir, "SourceHanSansSC.zip")
                
                urllib.request.urlretrieve(font_url, zip_path)
                
                # 解压字体文件
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(self.fonts_dir)
                
                # 删除zip文件
                os.remove(zip_path)
                
                st.success("思源黑体字体下载完成！")
            
            # 注册思源黑体
            pdfmetrics.registerFont(TTFont('SourceHanSans', source_han_path))
            return 'SourceHanSans'
        except Exception as e:
            st.error(f"下载安装思源黑体失败: {str(e)}")
            # 最后的备选方案
            return 'Helvetica'

    # 添加Word文档处理方法
    def extract_text_from_docx(self, docx_path: str) -> List[Tuple[int, dict]]:
        """从Word文档中提取文本，按段落返回内容"""
        content_by_page = []
        try:
            doc = Document(docx_path)
            
            # 创建文本提取进度条
            extract_progress = st.progress(0)
            extract_status = st.empty()
            extract_status.text("正在提取Word文档内容...")
            
            # 将文档内容按段落组织
            paragraphs = []
            tables = []
            
            # 提取段落
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append({
                        'text': para.text.strip(),
                        'bbox': None
                    })
            
            # 提取表格
            for table in doc.tables:
                table_data = []
                for row in table.rows:
                    row_data = [cell.text for cell in row.cells]
                    table_data.append(row_data)
                if table_data:
                    tables.append(table_data)
            
            # 由于Word文档没有明确的页面概念，我们将整个文档视为一页
            page_content = {
                "paragraphs": paragraphs,
                "tables": tables,
                "images": []  # Word文档中的图片处理较复杂，暂不支持
            }
            content_by_page.append((1, page_content))
            
            extract_status.text("文本提取完成！")
            extract_progress.progress(1.0)
            return content_by_page
                
        except Exception as e:
            raise Exception(f'Word文档读取失败：{str(e)}')

    def create_interleaved_docx(self, input_file: str, translated_texts: List[Tuple[int, dict]], output_path: str):
        """创建交错的Word文档，原文和译文交替显示"""
        try:
            # 创建新文档
            doc = Document()
            
            # 设置文档样式和字体
            style = doc.styles['Normal']
            style.font.name = 'SimSun'  # 使用宋体作为默认字体
            style.font.size = Pt(12)
            
            # 添加标题
            heading = doc.add_heading('文档翻译结果（原文与译文对照）', level=1)
            # 设置标题字体
            for run in heading.runs:
                run.font.name = 'SimHei'  # 使用黑体作为标题字体
            
            # 读取原始文档
            original_doc = Document(input_file)
            
            # 提取原始文档的段落和表格
            original_paragraphs = []
            for para in original_doc.paragraphs:
                if para.text.strip():
                    original_paragraphs.append(para.text.strip())
            
            original_tables = []
            for table in original_doc.tables:
                table_data = []
                for row in table.rows:
                    row_data = [cell.text for cell in row.cells]
                    table_data.append(row_data)
                if table_data:
                    original_tables.append(table_data)
            
            # 处理段落（原文和译文交替显示）
            doc.add_heading('段落内容', level=2)
            for run in doc.paragraphs[-1].runs:
                run.font.name = 'SimHei'
            
            for i, para_text in enumerate(original_paragraphs):
                # 添加原文标题
                p = doc.add_paragraph()
                p.add_run('原文：').bold = True
                p.runs[0].font.name = 'SimHei'
                
                # 添加原文内容
                p = doc.add_paragraph(para_text)
                p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进
                for run in p.runs:
                    run.font.name = 'SimSun'
                
                # 添加译文标题
                p = doc.add_paragraph()
                p.add_run('译文：').bold = True
                p.runs[0].font.name = 'SimHei'
                
                # 添加译文内容
                # 从translated_texts中找到对应的译文
                if i < len(translated_texts[0][1]["paragraphs"]):
                    trans_text = translated_texts[0][1]["paragraphs"][i]["text"]
                    p = doc.add_paragraph(trans_text)
                    p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进
                    for run in p.runs:
                        run.font.name = 'SimSun'
                
                # 添加分隔线
                doc.add_paragraph('-----------------------------------')
            
            # 处理表格（原文和译文交替显示）
            if original_tables:
                doc.add_heading('表格内容', level=2)
                for run in doc.paragraphs[-1].runs:
                    run.font.name = 'SimHei'
                
                for i, table_data in enumerate(original_tables):
                    # 添加原文表格标题
                    p = doc.add_paragraph()
                    p.add_run(f'原文表格 {i+1}：').bold = True
                    p.runs[0].font.name = 'SimHei'
                    
                    # 添加原文表格
                    if table_data:
                        table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
                        table.style = 'Table Grid'
                        
                        # 填充表格数据
                        for row_idx, row in enumerate(table_data):
                            for col_idx, cell in enumerate(row):
                                table.cell(row_idx, col_idx).text = cell or ""
                                # 设置单元格字体
                                for paragraph in table.cell(row_idx, col_idx).paragraphs:
                                    for run in paragraph.runs:
                                        run.font.name = 'SimSun'
                    
                    # 添加译文表格标题
                    p = doc.add_paragraph()
                    p.add_run(f'译文表格 {i+1}：').bold = True
                    p.runs[0].font.name = 'SimHei'
                    
                    # 添加译文表格
                    if i < len(translated_texts[0][1]["tables"]):
                        trans_table = translated_texts[0][1]["tables"][i]
                        if trans_table:
                            table = doc.add_table(rows=len(trans_table), cols=len(trans_table[0]))
                            table.style = 'Table Grid'
                            
                            # 填充表格数据
                            for row_idx, row in enumerate(trans_table):
                                for col_idx, cell in enumerate(row):
                                    table.cell(row_idx, col_idx).text = cell or ""
                                    # 设置单元格字体
                                    for paragraph in table.cell(row_idx, col_idx).paragraphs:
                                        for run in paragraph.runs:
                                            run.font.name = 'SimSun'
                    
                    # 添加分隔线
                    doc.add_paragraph('-----------------------------------')
            
            # 保存文档
            doc.save(output_path)
            
        except Exception as e:
            raise Exception(f'Word文档创建失败：{str(e)}')

    def create_translated_docx(self, translated_texts: List[Tuple[int, dict]], output_path: str, show_comparison: bool = True):
        """创建翻译后的Word文档"""
        try:
            doc = Document()
            
            # 设置文档样式
            style = doc.styles['Normal']
            style.font.name = 'SimSun'  # 使用宋体
            style.font.size = Pt(12)
            
            # 添加标题
            heading = doc.add_heading('文档翻译结果', level=1)
            # 设置标题字体
            for run in heading.runs:
                run.font.name = 'SimHei'  # 使用黑体作为标题字体
            
            # 处理所有翻译内容
            for page_num, page_content in translated_texts:
                # 添加页面标题
                subheading = doc.add_heading(f'第 {page_num} 页译文', level=2)
                # 设置小标题字体
                for run in subheading.runs:
                    run.font.name = 'SimHei'
                
                # 添加段落
                for para in page_content["paragraphs"]:
                    if para["text"].strip():
                        p = doc.add_paragraph(para["text"].strip())
                        p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进
                        # 设置段落字体
                        for run in p.runs:
                            run.font.name = 'SimSun'
                
                # 添加表格
                if page_content.get("tables"):
                    for table_data in page_content["tables"]:
                        if table_data:
                            # 创建表格
                            table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
                            table.style = 'Table Grid'
                            
                            # 填充表格数据
                            for i, row in enumerate(table_data):
                                for j, cell in enumerate(row):
                                    table.cell(i, j).text = cell or ""
                                    # 设置单元格字体
                                    for paragraph in table.cell(i, j).paragraphs:
                                        for run in paragraph.runs:
                                            run.font.name = 'SimSun'
                            
                            # 表格后添加空行
                            doc.add_paragraph()
            
            # 保存文档
            doc.save(output_path)
            
        except Exception as e:
            raise Exception(f'Word文档创建失败：{str(e)}')

    def _create_translation_pages(self, translated_texts: List[Tuple[int, dict]], output_path: str):
        """创建译文页面，确保每页译文单独成页，并有良好排版"""
        try:
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, PageBreak, TableStyle
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            
            # 创建PDF文档
            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                rightMargin=72,  # 1英寸页边距
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # 注册字体
            font_name = self._register_fonts()
            
            # 创建样式
            styles = getSampleStyleSheet()
            
            # 标题样式 - 更醒目
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontName=font_name,
                fontSize=16,
                leading=20,
                spaceBefore=24,
                spaceAfter=24,
                alignment=1,  # 居中
                textColor=colors.darkblue,
                borderWidth=1,
                borderColor=colors.lightgrey,
                borderPadding=10,
                backColor=colors.lightgrey,
                borderRadius=5
            )
            
            # 小标题样式 - 用于段落分组
            subtitle_style = ParagraphStyle(
                'SubtitleStyle',
                parent=styles['Heading2'],
                fontName=font_name,
                fontSize=14,
                leading=18,
                spaceBefore=16,
                spaceAfter=12,
                alignment=0,  # 左对齐
                textColor=colors.darkblue,
                borderWidth=0,
                borderColor=colors.lightgrey,
                borderPadding=5,
                leftIndent=10,
                underline=1
            )
            
            # 译文段落样式
            translated_style = ParagraphStyle(
                'TranslatedText',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=12,
                leading=18,  # 行间距
                spaceBefore=12,  # 段前空间
                spaceAfter=12,  # 段后空间
                firstLineIndent=24,  # 首行缩进
                alignment=0,  # 左对齐
                bulletIndent=10,  # 项目符号缩进
                leftIndent=20  # 左侧缩进
            )
            
            # 页码样式
            page_number_style = ParagraphStyle(
                'PageNumber',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                textColor=colors.darkgrey,
                alignment=1  # 居中
            )
            
            story = []
            
            # 按页面顺序处理译文
            for i, (page_num, page_content) in enumerate(translated_texts):
                # 如果不是第一页，添加分页符
                if i > 0:
                    story.append(PageBreak())
                
                # 添加页码标记作为标题
                story.append(Paragraph(f'第 {page_num} 页译文', title_style))
                story.append(Spacer(1, 24))
                
                # 分组处理段落，每3-5个段落为一组，添加小标题
                paragraphs = page_content["paragraphs"]
                if paragraphs:
                    # 根据段落数量决定分组数
                    group_size = min(5, max(3, len(paragraphs) // 3))
                    
                    for group_idx in range(0, len(paragraphs), group_size):
                        group_paragraphs = paragraphs[group_idx:group_idx + group_size]
                        
                        # 添加小标题（如果有多个分组）
                        if len(paragraphs) > group_size:
                            section_num = group_idx // group_size + 1
                            story.append(Paragraph(f'段落组 {section_num}', subtitle_style))
                        
                        # 添加译文段落，增加段落间的视觉分隔
                        for para in group_paragraphs:
                            if para["text"].strip():
                                # 处理段落文本，确保段落格式正确
                                para_text = para["text"].strip()
                                
                                # 添加段落
                                story.append(Paragraph(para_text, translated_style))
                                story.append(Spacer(1, 8))  # 段落间小间距
                        
                        # 组间分隔
                        if len(paragraphs) > group_size and group_idx + group_size < len(paragraphs):
                            story.append(Spacer(1, 16))
                            story.append(Paragraph('* * *', page_number_style))
                            story.append(Spacer(1, 16))
                
                # 处理表格
                if page_content.get("tables"):
                    story.append(Spacer(1, 16))  # 表格前增加间距
                    story.append(Paragraph('表格数据', subtitle_style))
                    story.append(Spacer(1, 12))
                    
                    for table_idx, table_data in enumerate(page_content["tables"]):
                        if table_data:
                            # 如果有多个表格，添加表格编号
                            if len(page_content["tables"]) > 1:
                                story.append(Paragraph(f'表格 {table_idx + 1}', ParagraphStyle(
                                    'TableTitle',
                                    parent=translated_style,
                                    fontSize=11,
                                    textColor=colors.darkblue,
                                    alignment=0
                                )))
                                story.append(Spacer(1, 8))
                            
                            # 创建表格
                            table = Table(table_data, repeatRows=1)
                            table.setStyle(TableStyle([
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                                ('FONTNAME', (0, 0), (-1, -1), font_name),
                                ('FONTSIZE', (0, 0), (-1, -1), 10),
                                ('PADDING', (0, 0), (-1, -1), 8),
                                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),  # 表头背景色
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # 表头文字颜色
                                ('FONTSIZE', (0, 0), (-1, 0), 11),  # 表头字体大小
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),  # 表头底部填充
                                ('TOPPADDING', (0, 0), (-1, 0), 10),  # 表头顶部填充
                                # 交替行颜色
                                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                            ]))
                            story.append(table)
                            story.append(Spacer(1, 16))
            
            # 生成PDF
            doc.build(story)
        
        except Exception as e:
            raise Exception(f'译文页面创建失败：{str(e)}')
    
    def create_interleaved_pdf(self, original_pdf: str, translated_texts: List[Tuple[int, dict]], output_path: str):
        """创建交错的PDF文件，原文页面和译文页面交替出现"""
        temp_trans_path = None
    
        try:
            # 使用临时文件上下文管理器
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_trans_path = temp_file.name
    
            # 创建译文页面
            self._create_translation_pages(translated_texts, temp_trans_path)
    
            # 检查临时文件是否成功创建
            if not os.path.exists(temp_trans_path):
                raise Exception("临时文件创建失败")
    
            # 创建最终的PDF文件
            writer = PdfWriter()
    
            # 打开原始PDF和译文PDF
            with open(original_pdf, 'rb') as orig_file, open(temp_trans_path, 'rb') as trans_file:
                # 一次性读取两个PDF文件
                orig_reader = PdfReader(orig_file)
                trans_reader = PdfReader(trans_file)
    
                # 计算总页数
                total_orig_pages = len(orig_reader.pages)
                total_trans_pages = len(trans_reader.pages)
    
                # 添加所有页面
                for i in range(max(total_orig_pages, total_trans_pages)):
                    # 添加原文页面
                    if i < total_orig_pages:
                        writer.add_page(orig_reader.pages[i])
    
                    # 添加译文页面
                    if i < total_trans_pages:
                        writer.add_page(trans_reader.pages[i])
    
            # 写入最终的PDF文件
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
    
        except Exception as e:
            raise Exception(f'PDF交错合并失败：{str(e)}')
    
        finally:
            # 删除临时文件
            if temp_trans_path and os.path.exists(temp_trans_path):
                try:
                    os.unlink(temp_trans_path)
                except:
                    pass

    def translate_pdf(self, input_file: str, output_file: str, target_language: str, show_comparison: bool = True):
        """翻译PDF文档"""
        try:
            # 提取PDF文档内容
            extracted_texts = self.extract_text_from_pdf(input_file)
            
            # 创建翻译进度条
            total_paragraphs = sum(len(page_content["paragraphs"]) for _, page_content in extracted_texts)
            translate_progress = st.progress(0)
            translate_status = st.empty()
            
            # 翻译所有段落
            translated_texts = []
            for page_num, page_content in extracted_texts:
                translated_paragraphs = []
                translated_tables = []
                
                # 翻译段落
                for i, para in enumerate(page_content["paragraphs"]):
                    translate_status.text(f"正在翻译第 {i+1}/{total_paragraphs} 个段落...")
                    translate_progress.progress((i+1) / total_paragraphs)
                    
                    if para["text"].strip():
                        translated_text = self.translate_text(para["text"], target_language)
                        translated_paragraphs.append({
                            "text": translated_text,
                            "bbox": para["bbox"]
                        })
                    else:
                        translated_paragraphs.append(para)
                
                # 翻译表格
                for table in page_content["tables"]:
                    translated_table = []
                    for row in table:
                        translated_row = []
                        for cell in row:
                            if cell and cell.strip():
                                translated_cell = self.translate_text(cell, target_language)
                                translated_row.append(translated_cell)
                            else:
                                translated_row.append(cell)
                        translated_table.append(translated_row)
                    translated_tables.append(translated_table)
                # 删除这行重复代码: translated_tables.append(translated_table)
                
                # 组合翻译后的内容
                translated_page_content = {
                    "paragraphs": translated_paragraphs,
                    "tables": translated_tables,
                    "images": page_content["images"]
                }
                translated_texts.append((page_num, translated_page_content))
            
            translate_status.text("翻译完成！正在生成PDF文档...")
            
            # 创建翻译后的PDF文档
            if show_comparison:
                self.create_interleaved_pdf(input_file, translated_texts, output_file)
            else:
                self._create_translation_pages(translated_texts, output_file)
            
            translate_status.text("PDF文档生成完成！")
            translate_progress.progress(1.0)
            
            return True
                
        except Exception as e:
            st.error(f"翻译失败: {str(e)}")
            raise Exception(f'文档翻译失败：{str(e)}')

    def translate_document(self, input_file: str, output_file: str, target_language: str, show_comparison: bool = True, file_type: str = 'pdf'):
        """翻译文档（支持PDF和Word文档）"""
        try:
            if file_type.lower() == 'pdf':
                return self.translate_pdf(input_file, output_file, target_language, show_comparison)
            elif file_type.lower() == 'docx':
                # 提取Word文档内容
                extracted_texts = self.extract_text_from_docx(input_file)
                
                # 创建翻译进度条
                total_paragraphs = sum(len(page_content["paragraphs"]) for _, page_content in extracted_texts)
                translate_progress = st.progress(0)
                translate_status = st.empty()
                
                # 翻译所有段落
                translated_texts = []
                for page_num, page_content in extracted_texts:
                    translated_paragraphs = []
                    translated_tables = []
                    
                    # 翻译段落
                    for i, para in enumerate(page_content["paragraphs"]):
                        translate_status.text(f"正在翻译第 {i+1}/{total_paragraphs} 个段落...")
                        translate_progress.progress((i+1) / total_paragraphs)
                        
                        if para["text"].strip():
                            translated_text = self.translate_text(para["text"], target_language)
                            translated_paragraphs.append({
                                "text": translated_text,
                                "bbox": para["bbox"]
                            })
                        else:
                            translated_paragraphs.append(para)
                    
                    # 翻译表格
                    for table in page_content["tables"]:
                        translated_table = []
                        for row in table:
                            translated_row = []
                            for cell in row:
                                if cell and cell.strip():
                                    translated_cell = self.translate_text(cell, target_language)
                                    translated_row.append(translated_cell)
                                else:
                                    translated_row.append(cell)
                            translated_table.append(translated_row)
                        translated_tables.append(translated_table)
                    
                    # 组合翻译后的内容
                    translated_page_content = {
                        "paragraphs": translated_paragraphs,
                        "tables": translated_tables,
                        "images": page_content["images"]
                    }
                    translated_texts.append((page_num, translated_page_content))
                
                translate_status.text("翻译完成！正在生成Word文档...")
                
                # 创建翻译后的Word文档
                if show_comparison:
                    self.create_interleaved_docx(input_file, translated_texts, output_file)
                else:
                    self.create_translated_docx(translated_texts, output_file)
                
                translate_status.text("Word文档生成完成！")
                translate_progress.progress(1.0)
                
                return True
            else:
                raise Exception(f'不支持的文件类型：{file_type}')
                
        except Exception as e:
            st.error(f"翻译失败: {str(e)}")
            raise Exception(f'文档翻译失败：{str(e)}')

def main():
    # 使用示例
    translator = PDFTranslator()
    input_file = 'input.pdf'  # 输入文件路径
    output_file = 'output.pdf'  # 输出文件路径
    target_language = '中文'  # 目标语言：'中文' 或 'English'
    
    translator.translate_pdf(input_file, output_file, target_language)

if __name__ == '__main__':
    main()