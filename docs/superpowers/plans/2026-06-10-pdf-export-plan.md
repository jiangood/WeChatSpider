# PDF 导出功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在爬取文章的同时，自动生成 PDF 文件，目录结构为 `公众号名称/年月/文章标题.pdf`

**Architecture:** 新模块 `spider/wechat/pdf_utils.py` 提供 Markdown→PDF 转换（fpdf2），图片下载到 `.imgcache/` 按 URL 哈希去重。在 `AsyncBatchWeChatScraper._async_scrape_all()` 内容获取和 CSV 保存之间插入 PDF 生成。GUI 设置页增加开关。

**Tech Stack:** fpdf2, PyQt6 SwitchButton, aiohttp (已有), hashlib

---

### Task 1: 添加 fpdf2 依赖

**Files:**
- Modify: `requirements.txt:26`

- [ ] **Step 1: 在 requirements.txt 末尾添加 fpdf2**

编辑 `requirements.txt`，在末尾添加一行：

```
fpdf2>=2.7.0
```

- [ ] **Step 2: 安装 fpdf2**

```bash
pip install fpdf2
```

- [ ] **Step 3: 提交**

```bash
git add requirements.txt
git commit -m "feat: add fpdf2 dependency for PDF export"
```

---

### Task 2: 创建 PDF 工具模块 `spider/wechat/pdf_utils.py`

**Files:**
- Create: `spider/wechat/pdf_utils.py`

这个模块包含三个核心函数：
1. `find_chinese_font()` — 自动检测系统微软雅黑字体路径
2. `download_images_for_pdf(markdown_content, img_cache_dir, session)` — 解析 Markdown 中的图片 URL，下载到缓存，返回替换后的 Markdown（本地路径）
3. `markdown_to_pdf(markdown_content, output_path, font_path, title)` — 单篇 Markdown → PDF
4. `generate_article_pdfs(articles, base_output_dir, font_path, img_cache_dir)` — 遍历文章列表生成 PDF

- [ ] **Step 1: 创建文件并实现字体检测**

```python
import os
import re
import hashlib
import asyncio
from datetime import datetime
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


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:80] or 'untitled'
```

- [ ] **Step 2: 实现图片下载和缓存替换**

```python
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
```

- [ ] **Step 3: 实现 Markdown → PDF 转换（fpdf2）**

```python
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

        # 图片行
        img_match = re.match(r'!\[(.*?)\]\((.*?)\)', line.strip())
        if img_match:
            img_path = img_match.group(2)
            if os.path.exists(img_path):
                w = pdf.w - 20
                pdf.image(img_path, x=10, w=min(w, 170))
                pdf.ln(4)
            i += 1
            continue

        # 标题
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
```

- [ ] **Step 4: 实现 `generate_article_pdfs` 主入口**

```python
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
```

- [ ] **Step 5: 同步 wrapper（供非异步上下文使用）**

```python
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
```

- [ ] **Step 6: 提交**

```bash
git add spider/wechat/pdf_utils.py
git commit -m "feat: add PDF generation module with fpdf2"
```

---

### Task 3: 在异步爬虫中集成 PDF 生成（`AsyncBatchWeChatScraper`）

**Files:**
- Modify: `spider/wechat/scraper.py:879-1003`

修改 `AsyncBatchWeChatScraper._async_scrape_all()` 方法，在内容获取完成后、CSV 保存之前插入 PDF 生成。

- [ ] **Step 1: 在 `_async_scrape_all` 顶部添加 import**

在 `scraper.py` 顶部附近的已有 import 区域添加：

```python
from spider.wechat.pdf_utils import generate_article_pdfs, find_chinese_font
```

- [ ] **Step 2: 在 `_async_scrape_all` 的 `results` 聚合后、`return` 前插入 PDF 生成**

找到 `_async_scrape_all` 方法末尾（约第 993-1003 行），在 `return all_articles` 之前添加：

```python
        # ===== PDF 生成 =====
        if not self.is_cancelled and config.get('generate_pdf', True) and all_articles:
            self._trigger_account_status("系统", "processing", "正在生成PDF...")
            try:
                output_dir = config.get('output_dir')
                if output_dir:
                    font_path = find_chinese_font()
                    pdf_callback = lambda event, data: None
                    await generate_article_pdfs(
                        all_articles,
                        base_output_dir=output_dir,
                        font_path=font_path,
                        progress_callback=pdf_callback,
                    )
            except FileNotFoundError as e:
                logger.warning(f"PDF生成跳过（字体未找到）: {e}")
            except Exception as e:
                logger.error(f"PDF生成失败: {e}")
```

完整的修改后方法末尾代码（第 991-1010 行）：

```python
        # 收集结果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"爬取异常: {result}")
                continue
            if result:
                all_articles.extend(result)

        # ===== PDF 生成 =====
        if not self.is_cancelled and config.get('generate_pdf', True) and all_articles:
            self._trigger_account_status("系统", "processing", "正在生成PDF...")
            try:
                output_dir = config.get('output_dir')
                if output_dir:
                    font_path = find_chinese_font()
                    await generate_article_pdfs(
                        all_articles,
                        base_output_dir=output_dir,
                        font_path=font_path,
                    )
            except FileNotFoundError as e:
                logger.warning(f"PDF生成跳过（字体未找到）: {e}")
            except Exception as e:
                logger.error(f"PDF生成失败: {e}")

        return all_articles
```

- [ ] **Step 3: 提交**

```bash
git add spider/wechat/scraper.py
git commit -m "feat: integrate PDF generation into async scraper"
```

---

### Task 4: 在同步爬虫（`BatchWeChatScraper`）中集成 PDF 生成（fallback）

**Files:**
- Modify: `spider/wechat/scraper.py:462-471`

修改 `BatchWeChatScraper.start_batch_scrape()`，在 CSV 保存后添加 PDF 生成。

- [ ] **Step 1: 在 CSV 保存后添加 PDF 生成**

找到 `start_batch_scrape` 方法中的 CSV 保存代码（第 462-469 行），在其后添加：

```python
            # 生成 PDF
            if config.get('generate_pdf', True) and all_articles:
                try:
                    from spider.wechat.pdf_utils import generate_article_pdfs_sync, find_chinese_font
                    font_path = find_chinese_font()
                    output_dir = os.path.dirname(config.get('output_file', '')) or config.get('output_dir', '')
                    if output_dir:
                        generate_article_pdfs_sync(all_articles, output_dir, font_path)
                except FileNotFoundError as e:
                    logger.warning(f"PDF生成跳过（字体未找到）: {e}")
                except Exception as e:
                    logger.error(f"PDF生成失败: {e}")
```

完整修改后的代码块：

```python
        # 保存结果到CSV
        if not self.is_cancelled:
            output_file = config.get('output_file')
            if output_file:
                self.scraper.save_articles_to_csv(all_articles, output_file)

            # 生成 PDF
            if config.get('generate_pdf', True) and all_articles:
                try:
                    from spider.wechat.pdf_utils import generate_article_pdfs_sync, find_chinese_font
                    font_path = find_chinese_font()
                    output_dir = os.path.dirname(output_file) if output_file else config.get('output_dir', '')
                    if output_dir:
                        generate_article_pdfs_sync(all_articles, output_dir, font_path)
                except FileNotFoundError as e:
                    logger.warning(f"PDF生成跳过（字体未找到）: {e}")
                except Exception as e:
                    logger.error(f"PDF生成失败: {e}")

            # 触发完成回调
            self._trigger_batch_completed(len(all_articles))
```

- [ ] **Step 2: 提交**

```bash
git add spider/wechat/scraper.py
git commit -m "feat: integrate PDF generation into sync scraper (fallback)"
```

---

### Task 5: GUI 设置页添加"导出 PDF"开关

**Files:**
- Modify: `gui/pages/settings_page.py:47-55, 206-212, 338-345, 358-364`

- [ ] **Step 1: DEFAULT_CONFIG 增加 `generate_pdf` 字段**

```python
DEFAULT_CONFIG = {
    'request_interval': 10,
    'account_interval_min': 15,
    'account_interval_max': 30,
    'max_workers': 1,
    'include_content': False,
    'generate_pdf': True,              # 新增
    'output_dir': DEFAULT_OUTPUT_DIR,
    'cache_expire_hours': 96,
}
```

- [ ] **Step 2: 在爬取设置卡片中"获取文章正文"下面添加"导出 PDF"开关**

在 `_setup_ui()` 中，找到 `item4`（获取正文开关）添加后的位置，在其后添加分隔线和 PDF 开关：

```python
        self._add_separator(scrape_layout)

        # 获取正文
        item4 = SettingItem("获取文章正文", "默认爬取文章内容（较慢）")
        self.content_switch = SwitchButton()
        self.content_switch.setChecked(self.config.get('include_content', False))
        item4.addControl(self.content_switch)
        scrape_layout.addWidget(item4)

        self._add_separator(scrape_layout)

        # 导出 PDF
        item_pdf = SettingItem("导出PDF", "爬取同时生成PDF文件（需中文字体）")
        self.pdf_switch = SwitchButton()
        self.pdf_switch.setChecked(self.config.get('generate_pdf', True))
        item_pdf.addControl(self.pdf_switch)
        scrape_layout.addWidget(item_pdf)
```

- [ ] **Step 3: `_on_save` 中收集 PDF 开关状态**

```python
        self.config = {
            'request_interval': self.interval_spin.value(),
            'max_workers': 1,
            'include_content': self.content_switch.isChecked(),
            'generate_pdf': self.pdf_switch.isChecked(),
            'output_dir': self.output_input.text().strip() or DEFAULT_OUTPUT_DIR,
            'cache_expire_hours': self.cache_spin.value(),
        }
```

- [ ] **Step 4: `_on_reset` 中重置 PDF 开关**

```python
    def _on_reset(self):
        self.config = DEFAULT_CONFIG.copy()
        self.interval_spin.setValue(self.config['request_interval'])
        self.content_switch.setChecked(self.config['include_content'])
        self.pdf_switch.setChecked(self.config['generate_pdf'])
        self.output_input.setText(self.config['output_dir'])
        self.cache_spin.setValue(self.config['cache_expire_hours'])
        self._save_config()
```

- [ ] **Step 5: 提交**

```bash
git add gui/pages/settings_page.py
git commit -m "feat: add PDF export toggle to settings page"
```

---

### Task 6: 爬取页面传递 `generate_pdf` 配置

**Files:**
- Modify: `gui/pages/unified_scrape_page.py:393-403`

- [ ] **Step 1: 在爬取配置字典中添加 `generate_pdf` 和 `output_dir`**

找到 `unified_scrape_page.py` 中 `config = {...}` 字典（第 393-403 行），添加 `generate_pdf` 和 `output_dir`：

```python
        config = {
            'accounts': accounts,
            'start_date': start.toString("yyyy-MM-dd"),
            'end_date': end.toString("yyyy-MM-dd"),
            'token': token, 'headers': headers,
            'request_interval': 10,
            'include_content': True,
            'generate_pdf': self.config.get('generate_pdf', True),
            'output_file': output_file,
            'output_dir': output_dir,
            'max_concurrent_accounts': 1,
            'max_concurrent_requests': 1
        }
```

- [ ] **Step 2: 提交**

```bash
git add gui/pages/unified_scrape_page.py
git commit -m "feat: pass generate_pdf config from scrape page to scraper"
```

---

### Task 7: 更新 config.json 默认值

**Files:**
- Modify: `config.json:5`

- [ ] **Step 1: 添加 `generate_pdf` 字段**

```json
{
  "request_interval": 10,
  "max_workers": 5,
  "include_content": true,
  "generate_pdf": true,
  "cache_expire_hours": 96
}
```

- [ ] **Step 2: 提交**

```bash
git add config.json
git commit -m "feat: add generate_pdf to default config"
```

---

### Task 8: 最终验证与导入更新

**Files:**
- Modify: `spider/wechat/__init__.py`

- [ ] **Step 1: 运行应用确认无导入错误**

```bash
python run_gui.py
```

确认应用启动正常，设置页能看到"导出PDF"开关，开始爬取不会报错。

- [ ] **Step 2: （可选）将 `generate_article_pdfs` 加入包导出**

如果希望 pdf_utils 能从 `spider.wechat` 导入：

```bash
# 无需修改，通过 spider.wechat.pdf_utils 直接导入即可
```

- [ ] **Step 3: 提交最终调整**

```bash
git add -A
git commit -m "chore: final adjustments for PDF export feature"
```
