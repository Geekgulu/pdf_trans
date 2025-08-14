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
import tempfile  # 添加到文件开头的导入部分

class PDFTranslator:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.api_url = 'https://api.siliconflow.cn/v1/chat/completions'
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

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
        """注册多语言字体"""
        try:
            # 尝试注册支持多语言的字体
            # Arial Unicode MS 支持大多数语言包括阿拉伯语、泰语等
            pdfmetrics.registerFont(TTFont('ArialUnicode', 'C:/Windows/Fonts/ARIALUNI.TTF'))
            return 'ArialUnicode'
        except:
            try:
                # 备选：Noto Sans 字体（如果系统有安装）
                pdfmetrics.registerFont(TTFont('NotoSans', 'C:/Windows/Fonts/NotoSans-Regular.ttf'))
                return 'NotoSans'
            except:
                try:
                    # 中文字体
                    pdfmetrics.registerFont(TTFont('SimSun', 'C:/Windows/Fonts/simsun.ttc'))
                    return 'SimSun'
                except:
                    try:
                        pdfmetrics.registerFont(TTFont('SimHei', 'C:/Windows/Fonts/simhei.ttf'))
                        return 'SimHei'
                    except:
                        return 'Helvetica'
    
    def _create_simple_pdf(self, translated_texts: List[Tuple[int, str]], output_path: str, original_texts: List[Tuple[int, str]] = None, show_comparison: bool = False):
        """简单的PDF创建方法（备用），支持段落对照格式"""
        from reportlab.lib.utils import simpleSplit
        
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        
        # 设置页边距
        left_margin = 72  # 1英寸
        right_margin = 72
        top_margin = 72
        bottom_margin = 72
        
        # 可用宽度和高度
        usable_width = width - left_margin - right_margin
        usable_height = height - top_margin - bottom_margin
        
        # 注册多语言字体
        font_name = self._register_fonts()
        
        # 提取所有段落
        all_paragraphs = []
        
        # 创建原文和译文的映射
        for i in range(len(original_texts)):
            orig_page, orig_text = original_texts[i]
            trans_page, trans_text = translated_texts[i]
            
            # 按段落分割文本
            orig_paras = orig_text.split('\n\n')
            trans_paras = trans_text.split('\n\n')
            
            # 确保两个列表长度一致
            max_len = max(len(orig_paras), len(trans_paras))
            orig_paras = orig_paras + [""] * (max_len - len(orig_paras))
            trans_paras = trans_paras + [""] * (max_len - len(trans_paras))
            
            # 将段落对添加到列表中
            for orig_para, trans_para in zip(orig_paras, trans_paras):
                if orig_para.strip() or trans_para.strip():
                    all_paragraphs.append((orig_para, trans_para))
        
        # 初始位置
        y_position = height - top_margin
        
        # 处理所有段落
        for orig_para, trans_para in all_paragraphs:
            if not (orig_para.strip() or trans_para.strip()):
                continue
            
            # 检查是否需要换页
            if y_position < bottom_margin + 100:  # 预留更多空间
                c.showPage()
                y_position = height - top_margin
            
            if show_comparison:
                # 对照模式：显示原文和译文（无标签）
                if orig_para.strip():
                    c.setFont(font_name, 11)
                    c.setFillColorRGB(0.4, 0.4, 0.4)  # 灰色
                    
                    # 使用simpleSplit进行自动换行
                    lines = simpleSplit(orig_para, font_name, 11, usable_width)
                    for line in lines:
                        if y_position < bottom_margin + 20:
                            c.showPage()
                            y_position = height - top_margin
                            c.setFont(font_name, 11)
                            c.setFillColorRGB(0.4, 0.4, 0.4)  # 灰色
                        
                        c.drawString(left_margin, y_position, line)
                        y_position -= 16  # 行间距
                    
                    y_position -= 5  # 原文和译文之间的间距
                
                if trans_para.strip():
                    c.setFont(font_name, 12)
                    c.setFillColorRGB(0, 0, 0)  # 黑色
                    
                    # 使用simpleSplit进行自动换行
                    lines = simpleSplit(trans_para, font_name, 12, usable_width)
                    for line in lines:
                        if y_position < bottom_margin + 20:
                            c.showPage()
                            y_position = height - top_margin
                            c.setFont(font_name, 12)
                            c.setFillColorRGB(0, 0, 0)  # 黑色
                        
                        c.drawString(left_margin, y_position, line)
                        y_position -= 18  # 行间距
                    
                    y_position -= 20  # 段落组间距
            else:
                # 仅显示译文
                c.setFont(font_name, 12)
                c.setFillColorRGB(0, 0, 0)  # 黑色
                
                if trans_para.strip():
                    # 使用simpleSplit进行自动换行
                    lines = simpleSplit(trans_para, font_name, 12, usable_width)
                    
                    for line in lines:
                        if y_position < bottom_margin + 20:  # 检查是否需要换页
                            c.showPage()
                            y_position = height - top_margin
                            c.setFont(font_name, 12)
                        
                        c.drawString(left_margin, y_position, line)
                        y_position -= 18  # 行间距
                    
                    y_position -= 12  # 段落间距
        
        c.save()

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
        """翻译整个PDF文件"""
        try:
            # 提取PDF内容
            original_texts = self.extract_text_from_pdf(input_file)
            translated_texts = []

            # 计算总段落数
            total_paragraphs = sum(len(page_content["paragraphs"]) 
                          for _, page_content in original_texts)
            
            # 创建进度条
            progress_bar = st.progress(0)
            status_text = st.empty()
            current_para = 0

            # 遍历每页内容
            for page_num, page_content in original_texts:
                translated_paragraphs = []
                
                # 逐段翻译
                for para in page_content["paragraphs"]:
                    text = para["text"]
                    if text.strip():
                        # 更新状态信息
                        current_para += 1
                        status_text.text(f"正在翻译第 {page_num} 页 - 段落 {current_para}/{total_paragraphs}")
                        progress = current_para / total_paragraphs
                        progress_bar.progress(progress)

                        # 翻译文本
                        translated_text = self.translate_text(text, target_language)
                        translated_paragraphs.append({
                            "text": translated_text,
                            "bbox": para["bbox"]
                        })

                # 保存翻译结果
                translated_texts.append((
                    page_num, 
                    {
                        "paragraphs": translated_paragraphs,
                        "tables": page_content["tables"],
                        "images": page_content["images"]
                    }
                ))

            # 更新状态
            status_text.text("正在生成翻译后的PDF文档...")
            
            # 根据show_comparison参数决定PDF生成方式
            if show_comparison:
                self.create_interleaved_pdf(input_file, translated_texts, output_file)
            else:
                self._create_translation_pages(translated_texts, output_file)
            
            # 完成提示
            status_text.text("翻译完成！")
            progress_bar.progress(1.0)

        except Exception as e:
            st.error(f'PDF翻译失败：{str(e)}')
            raise Exception(f'PDF翻译失败：{str(e)}')

def main():
    # 使用示例
    translator = PDFTranslator()
    input_file = 'input.pdf'  # 输入文件路径
    output_file = 'output.pdf'  # 输出文件路径
    target_language = '中文'  # 目标语言：'中文' 或 'English'
    
    translator.translate_pdf(input_file, output_file, target_language)

if __name__ == '__main__':
    main()