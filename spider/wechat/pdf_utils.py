import os
import re
import hashlib
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp
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


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:80] or 'untitled'


def _extract_image_urls(markdown_content: str) -> List[str]:
    urls = re.findall(r'!\[.*?\]\((.*?)\)', markdown_content)
    result = []
    for url in urls:
        url = url.strip()
        if url and 'mmbiz.qpic.cn' in url:
            result.append(url)
    return result


def _url_to_cache_path(url: str, cache_dir: str) -> str:
    ext = os.path.splitext(url.split('?')[0])[1] or '.jpg'
    if not ext or len(ext) > 5:
        ext = '.jpg'
    hash_name = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(cache_dir, f'{hash_name}{ext}')


async def download_images_for_pdf(
    markdown_content: str,
    img_cache_dir: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> str:
    urls = _extract_image_urls(markdown_content)
    if not urls:
        return markdown_content

    os.makedirs(img_cache_dir, exist_ok=True)

    async def _download_one(url: str):
        cache_path = _url_to_cache_path(url, img_cache_dir)
        if os.path.exists(cache_path):
            return url, cache_path
        try:
            close_session = False
            if session is None:
                session = aiohttp.ClientSession()
                close_session = True
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(cache_path, 'wb') as f:
                        f.write(data)
                    return url, cache_path
        except Exception as e:
            logger.warning(f'下载图片失败: {url[:60]} - {e}')
        finally:
            if close_session and session:
                await session.close()
        return url, None

    tasks = [_download_one(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    url_map = {}
    for r in results:
        if isinstance(r, tuple) and r[1]:
            url_map[r[0]] = r[1]

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
            i += 1
            continue

        stripped = line.strip()
        if stripped.startswith('# ') and len(stripped) > 2:
            pdf.set_font('zh', 'B', 18)
            pdf.multi_cell(0, 10, stripped[2:])
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
            pdf.multi_cell(0, 6, stripped)

        i += 1

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)


async def generate_article_pdfs(
    articles: List[Dict],
    base_output_dir: str,
    font_path: str,
    img_cache_dir: Optional[str] = None,
    progress_callback=None,
) -> List[str]:
    if img_cache_dir is None:
        img_cache_dir = os.path.join(base_output_dir, '.imgcache')

    generated = []
    session = aiohttp.ClientSession()
    try:
        for idx, article in enumerate(articles):
            name = article.get('name', '未知公众号')
            pub_time = article.get('publish_time', '')
            title = article.get('title', '无标题')
            content = article.get('content', '')

            year_month = pub_time[:7] if len(pub_time) >= 7 else 'unknown'
            pdf_dir = os.path.join(base_output_dir, _sanitize_filename(name), year_month)
            pdf_name = f'{_sanitize_filename(title)}.pdf'
            pdf_path = os.path.join(pdf_dir, pdf_name)

            if not content:
                logger.warning(f'跳过PDF生成（无内容）: {title}')
                if progress_callback:
                    progress_callback('pdf_progress', {'current': idx + 1, 'total': len(articles), 'article': title, 'status': 'skipped'})
                continue

            try:
                content_with_local = await download_images_for_pdf(content, img_cache_dir, session)
                markdown_to_pdf(content_with_local, pdf_path, font_path, title)
                generated.append(pdf_path)
                logger.info(f'PDF生成成功: {pdf_path}')
                if progress_callback:
                    progress_callback('pdf_progress', {'current': idx + 1, 'total': len(articles), 'article': title, 'status': 'ok'})
            except Exception as e:
                logger.error(f'PDF生成失败 [{title}]: {e}')
                if progress_callback:
                    progress_callback('pdf_progress', {'current': idx + 1, 'total': len(articles), 'article': title, 'status': 'error', 'error': str(e)})
    finally:
        await session.close()

    return generated


def generate_article_pdfs_sync(
    articles, base_output_dir, font_path=None, img_cache_dir=None
):
    if font_path is None:
        font_path = find_chinese_font()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            generate_article_pdfs(articles, base_output_dir, font_path, img_cache_dir)
        )
    finally:
        loop.close()
