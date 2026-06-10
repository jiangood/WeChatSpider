import os
import re
import hashlib
from typing import List, Dict, Optional

from fpdf import FPDF
from spider.log.utils import logger


def find_chinese_font() -> str:
    candidates = [
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\msyhbd.ttc',
        r'C:\Windows\Fonts\simsun.ttc',
        r'C:\Windows\Fonts\SIMHEI.TTF',
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError('未找到中文字体（msyh.ttc/simsun.ttc），请安装微软雅黑或宋体')


_INLINE_BOLD = re.compile(r'\*\*(.+?)\*\*')


def _render_text_line(pdf, text, font_size=11, line_h=6):
    parts = _INLINE_BOLD.split(text)
    if len(parts) == 1:
        pdf.multi_cell(0, line_h, text)
        return
    for i, part in enumerate(parts):
        if not part:
            continue
        pdf.set_font('zh', 'B' if i % 2 else '', font_size)
        pdf.write(line_h, part)
    pdf.ln()


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', '', name).strip()[:100]
    return safe or 'untitled'


def _extract_image_urls(markdown_content: str) -> List[str]:
    urls = re.findall(r'!\[.*?\]\((.*?)\)', markdown_content)
    result = []
    for url in urls:
        url = url.strip()
        if url and 'mmbiz.qpic.cn' in url:
            result.append(url)
    return result


def _get_image_extension(url: str) -> str:
    if 'wx_fmt=' in url:
        match = re.search(r'wx_fmt=(\w+)', url)
        if match:
            fmt = match.group(1).lower()
            if fmt in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                return f'.{fmt}'
    ext = os.path.splitext(url.split('?')[0])[1].lower()
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        return ext
    return '.jpg'


def _url_to_cache_path(url: str, cache_dir: str) -> str:
    ext = _get_image_extension(url)
    hash_name = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(cache_dir, f'{hash_name}{ext}')


_DOWNLOAD_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def _merge_headers(headers: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if headers is None:
        return dict(_DOWNLOAD_HEADERS)
    merged = dict(headers)
    merged.setdefault('Accept', _DOWNLOAD_HEADERS['Accept'])
    merged.setdefault('Accept-Language', _DOWNLOAD_HEADERS['Accept-Language'])
    return merged


def _sync_download_images(markdown_content: str, img_cache_dir: str, headers: Optional[Dict[str, str]] = None) -> str:
    import requests as req_lib
    download_headers = _merge_headers(headers)
    urls = _extract_image_urls(markdown_content)
    if not urls:
        return markdown_content
    os.makedirs(img_cache_dir, exist_ok=True)
    url_map = {}
    for url in urls:
        cache_path = _url_to_cache_path(url, img_cache_dir)
        if os.path.exists(cache_path):
            url_map[url] = cache_path
            continue
        try:
            resp = req_lib.get(url, headers=download_headers, timeout=30)
            if resp.status_code == 200:
                with open(cache_path, 'wb') as f:
                    f.write(resp.content)
                url_map[url] = cache_path
        except Exception as e:
            logger.warning(f'下载图片失败: {url[:60]} - {e}')
    def _replace(match):
        alt = match.group(1)
        url = match.group(2).strip()
        local = url_map.get(url)
        if local:
            return f'![{alt}]({local})'
        return match.group(0)
    return re.sub(r'!\[(.*?)\]\((.*?)\)', _replace, markdown_content)


class ArticlePDF(FPDF):
    def __init__(self, font_path: str):
        super().__init__()
        self.font_path = font_path
        self.title_str = ''
        self.add_font('zh', '', font_path, uni=True)
        self.add_font('zh', 'B', font_path, uni=True)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font('zh', '', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, self.title_str or '', align='C')
            self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('zh', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'{self.page_no()}', align='C')


def markdown_to_pdf(markdown_content: str, output_path: str, font_path: str, title: str = ''):
    pdf = ArticlePDF(font_path)
    pdf.title_str = title
    pdf.set_title(title)
    pdf.add_page()

    pdf.set_font('zh', '', 11)
    pdf.set_text_color(30, 30, 30)

    lines = markdown_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        img_match = re.match(r'!\[(.*?)\]\((.*?)\)', line.strip())
        if img_match:
            img_path = img_match.group(2)
            if os.path.exists(img_path):
                w = pdf.w - 20
                pdf.image(img_path, x=10, w=min(w, 170))
                pdf.ln(4)
            else:
                logger.warning(f'PDF渲染跳过不存在的图片: {img_path}')
            i += 1
            continue

        stripped = line.strip()
        if stripped.startswith('# ') and len(stripped) > 2:
            pdf.set_font('zh', 'B', 18)
            pdf.multi_cell(0, 10, stripped[2:], align='C')
            pdf.ln(2)
            pdf.set_font('zh', '', 11)
        elif stripped.startswith('## ') and len(stripped) > 3:
            pdf.set_font('zh', 'B', 15)
            pdf.multi_cell(0, 9, stripped[3:])
            pdf.ln(2)
            pdf.set_font('zh', '', 11)
        elif stripped.startswith('### ') and len(stripped) > 4:
            pdf.set_font('zh', 'B', 13)
            pdf.multi_cell(0, 8, stripped[4:])
            pdf.ln(1)
            pdf.set_font('zh', '', 11)
        elif stripped.startswith('> '):
            pdf.set_font('zh', '', 10)
            pdf.set_x(15)
            pdf.multi_cell(pdf.w - 25, 6, stripped[2:])
            pdf.set_font('zh', '', 11)
        elif not stripped.strip():
            pdf.ln(4)
        else:
            _render_text_line(pdf, stripped)

        i += 1

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)


def generate_single_article_pdf(
    article: Dict,
    base_output_dir: str,
    font_path: str,
    headers: Optional[Dict[str, str]] = None,
    img_cache_dir: Optional[str] = None,
) -> Optional[str]:
    name = article.get('name', '未知公众号')
    pub_time = article.get('publish_time', '')
    title = article.get('title', '无标题')
    content = article.get('content', '')
    if not content:
        logger.warning(f'跳过PDF生成（无内容）: {title}')
        return None
    if img_cache_dir is None:
        img_cache_dir = os.path.join(base_output_dir, '.imgcache')
    date_prefix = pub_time[:10].replace('-', '') if len(pub_time) >= 10 else 'unknown'
    pdf_dir = os.path.join(base_output_dir, _sanitize_filename(name))
    pdf_name = f'{date_prefix}_{_sanitize_filename(title)}.pdf'
    pdf_path = os.path.join(pdf_dir, pdf_name)
    try:
        content_with_local = _sync_download_images(content, img_cache_dir, headers)
        pdf_content = f"# {title}\n\n公众号：{name} ｜ {pub_time}\n\n{content_with_local}"
        markdown_to_pdf(pdf_content, pdf_path, font_path, title)
        logger.info(f'PDF生成成功: {pdf_path}')
        return pdf_path
    except Exception as e:
        logger.error(f'PDF生成失败 [{title}]: {e}')
        return None


def generate_article_pdfs_sync(
    articles: List[Dict],
    base_output_dir: str,
    font_path: Optional[str] = None,
    img_cache_dir: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> List[str]:
    if font_path is None:
        font_path = find_chinese_font()
    generated = []
    for article in articles:
        pdf_path = generate_single_article_pdf(article, base_output_dir, font_path, headers, img_cache_dir)
        if pdf_path:
            generated.append(pdf_path)
    return generated
