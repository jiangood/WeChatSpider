# 简化架构：移除异步模式 + 改为逐篇生成 PDF — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 移除异步爬虫和批量 PDF 生成，改为「爬一篇 → 生成一篇 PDF → 再爬下一篇」

**Architecture:** 删除 async_utils.py、AsyncBatchWeChatScraper、AsyncBatchScrapeWorker；pdf_utils.py 改为纯同步；同步 BatchWeChatScraper 在每篇文章内容获取后立即生成 PDF；修复 request_interval 配置除以 10 的 bug。

**Tech Stack:** requests, fpdf2, PyQt6

---

### Task 1: pdf_utils.py — 重构为纯同步 + 新增单篇 PDF 生成

**Files:**
- Modify: `spider/wechat/pdf_utils.py:1-288`

- [ ] **Step 1: 删除 async 导入和函数**

删除第 4 行 `import asyncio`，第 7 行 `import aiohttp`。

删除第 90-142 行 `download_images_for_pdf` async 函数。

删除第 226-273 行 `generate_article_pdfs` async 函数。

修改第 276-288 行 `generate_article_pdfs_sync`，改为纯同步循环：

```python
def generate_article_pdfs_sync(articles, base_output_dir, font_path=None, img_cache_dir=None, headers=None):
    if font_path is None:
        font_path = find_chinese_font()
    generated = []
    for article in articles:
        success = generate_single_article_pdf(article, base_output_dir, font_path, headers)
        if success:
            name = article.get('name', '未知公众号')
            pub_time = article.get('publish_time', '')
            title = article.get('title', '无标题')
            date_prefix = pub_time[:10].replace('-', '') if len(pub_time) >= 10 else 'unknown'
            pdf_name = f'{date_prefix}_{_sanitize_filename(title)}.pdf'
            pdf_dir = os.path.join(base_output_dir, _sanitize_filename(name))
            generated.append(os.path.join(pdf_dir, pdf_name))
    return generated
```

- [ ] **Step 2: 新增 `_sync_download_images` 辅助函数**

在第 88 行（`_merge_headers` 之后）插入：

```python
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
```

- [ ] **Step 3: 新增 `generate_single_article_pdf` 函数**

在第 224 行（`markdown_to_pdf` 之后，原 `generate_article_pdfs` 之前）插入：

```python
def generate_single_article_pdf(
    article: Dict,
    base_output_dir: str,
    font_path: str,
    headers: Optional[Dict[str, str]] = None,
    img_cache_dir: Optional[str] = None,
) -> bool:
    name = article.get('name', '未知公众号')
    pub_time = article.get('publish_time', '')
    title = article.get('title', '无标题')
    content = article.get('content', '')
    if not content:
        logger.warning(f'跳过PDF生成（无内容）: {title}')
        return False
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
        return True
    except Exception as e:
        logger.error(f'PDF生成失败 [{title}]: {e}')
        return False
```

- [ ] **Step 4: 验证文件无语法错误**

Run: `cd spider/wechat && python -c "from pdf_utils import generate_single_article_pdf, generate_article_pdfs_sync; print('OK')"`
Expected: `OK`


### Task 2: scraper.py — 修复 request_interval + 增加逐篇 PDF 生成

**Files:**
- Modify: `spider/wechat/scraper.py:1-1101`

- [ ] **Step 1: 修复所有 `request_interval` 除以 10 的 bug**

三处修改，把 `/ 10` 去掉：

第 610 行：
```python
# 改前
self.scraper.request_delay = (1, config.get('request_interval', 60) / 10)
# 改后
self.scraper.request_delay = (1, config.get('request_interval', 60))
```

第 648 行：
```python
# 改前
delay = random.uniform(1, config.get('request_interval', 60) / 10)
# 改后
delay = random.uniform(1, config.get('request_interval', 60))
```

第 714 行：
```python
# 改前
delay = random.uniform(1, config.get('request_interval', 60) / 10)
# 改后
delay = random.uniform(1, config.get('request_interval', 60))
```

- [ ] **Step 2: 在 `_scrape_single_account()` 中增加逐篇 PDF 生成**

在第 642-653 行的内容获取循环内，`get_article_content_by_url` 之后、sleep 之前，增加 PDF 生成调用：

```python
                    try:
                        # 获取内容
                        article = self.scraper.get_article_content_by_url(article)

                        # 立即生成 PDF（利用 PDF 处理时间作为自然间隔）
                        if config.get('generate_pdf', True):
                            try:
                                from spider.wechat.pdf_utils import generate_single_article_pdf, find_chinese_font
                                font_path = find_chinese_font()
                                output_dir = config.get('output_dir', '')
                                if output_dir:
                                    generate_single_article_pdf(article, output_dir, font_path, headers=config.get('headers'))
                            except FileNotFoundError as e:
                                logger.warning(f"PDF生成跳过（字体未找到）: {e}")
                                config['generate_pdf'] = False  # 后续不再尝试
                            except Exception as e:
                                logger.error(f"PDF生成失败: {e}")

                        # 请求间延迟
                        if i < len(articles_in_range) - 1:
                            delay = random.uniform(1, config.get('request_interval', 60))
                            time.sleep(delay)
```

注意：`find_chinese_font()` 在第一次成功后可缓存 font_path 避免重复搜索。为简化实现，可以每次调用 — 函数内部有缓存效果（`os.path.exists`）且调用开销极小。

- [ ] **Step 3: 删除 `start_batch_scrape()` 末尾的批量 PDF 生成**

删除第 466-477 行（完整的代码块）：

```python
            # 生成 PDF
            if config.get('generate_pdf', True) and all_articles:
                try:
                    from spider.wechat.pdf_utils import generate_article_pdfs_sync, find_chinese_font
                    font_path = find_chinese_font()
                    output_dir = os.path.dirname(output_file) if output_file else config.get('output_dir', '')
                    if output_dir:
                        generate_article_pdfs_sync(all_articles, output_dir, font_path, headers=config.get('headers'))
                except FileNotFoundError as e:
                    logger.warning(f"PDF生成跳过（字体未找到）: {e}")
                except Exception as e:
                    logger.error(f"PDF生成失败: {e}")
```

保留前后的 `if not self.is_cancelled:` 和 `self._trigger_batch_completed(...)`。

- [ ] **Step 4: 删除 `import asyncio`**

删除第 39 行 `import asyncio`。

- [ ] **Step 5: 修改顶部 `generate_article_pdfs` 导入为 `find_chinese_font`**

第 46 行：
```python
# 改前
from spider.wechat.pdf_utils import generate_article_pdfs, find_chinese_font
# 改后
from spider.wechat.pdf_utils import find_chinese_font
```

- [ ] **Step 6: 删除 `AsyncBatchWeChatScraper` 整个类**

删除第 759-1101 行（从 `class AsyncBatchWeChatScraper:` 到文件末尾）。

注意保留下面的代码（如果有的话），这个类之后没有别的代码了，但确认一下第 1099 行之后是否有空行或结尾。

Run: `python -c "import ast; ast.parse(open('spider/wechat/scraper.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`


### Task 3: workers.py — 删除 AsyncBatchScrapeWorker

**Files:**
- Modify: `gui/workers.py:1-270`

- [ ] **Step 1: 删除 `AsyncBatchScrapeWorker` 类**

删除第 150-270 行（从 `class AsyncBatchScrapeWorker(QThread):` 到文件末尾）。

更新模块 docstring，将第 14-18 行的异步工作线程描述删除：

```python
"""
工作线程类型:
    1. BatchScrapeWorker: 同步爬取工作线程
       - 使用 ThreadPoolExecutor 实现并发
       - 适用于简单的批量爬取场景
"""
```

- [ ] **Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('gui/workers.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`


### Task 4: unified_scrape_page.py — 改用同步爬虫

**Files:**
- Modify: `gui/pages/unified_scrape_page.py:1-576`

- [ ] **Step 1: 修改导入**

第 47 行：
```python
# 改前
from ..workers import AsyncBatchScrapeWorker
# 改后
from ..workers import BatchScrapeWorker
```

第 49 行：
```python
# 改前
from spider.wechat.scraper import AsyncBatchWeChatScraper
# 改后
from spider.wechat.scraper import BatchWeChatScraper
```

更新模块 docstring 第 23 行：
```python
# 改前
#     - 使用异步爬虫 AsyncBatchWeChatScraper 进行数据抓取
# 改后
#     - 使用同步爬虫 BatchWeChatScraper 进行数据抓取
```

- [ ] **Step 2: 修改实例化代码**

第 431-432 行：
```python
# 改前
        self.batch_scraper = AsyncBatchWeChatScraper()
        self.scrape_worker = AsyncBatchScrapeWorker(self.batch_scraper, config)
# 改后
        self.batch_scraper = BatchWeChatScraper()
        self.scrape_worker = BatchScrapeWorker(self.batch_scraper, config)
```

更新类 docstring 第 101 行：
```python
# 改前
        batch_scraper: 异步批量爬虫实例
# 改后
        batch_scraper: 批量爬虫实例
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('gui/pages/unified_scrape_page.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`


### Task 5: 删除 async_utils.py + 更新配置文件

**Files:**
- Delete: `spider/wechat/async_utils.py`
- Modify: `WeChatSpider.spec:116`
- Modify: `AGENTS.md:17,19,27,30`
- Modify: `README.md:114,129`

- [ ] **Step 1: 删除 async_utils.py**

Run: `Remove-Item -LiteralPath "spider/wechat/async_utils.py"`

- [ ] **Step 2: 更新 WeChatSpider.spec**

删除第 116 行 `'spider.wechat.async_utils',`。

- [ ] **Step 3: 更新 AGENTS.md**

第 17 行：
```markdown
# 改前
  - `spider.wechat.scraper` — three scraper classes: `WeChatScraper` (single), `BatchWeChatScraper` (ThreadPoolExecutor), `AsyncBatchWeChatScraper` (aiohttp).
# 改后
  - `spider.wechat.scraper` — two scraper classes: `WeChatScraper` (single), `BatchWeChatScraper` (ThreadPoolExecutor).
```

第 19 行：删除 `  - \`spider.wechat.async_utils\` — async HTTP (aiohttp). Parallel copy of image/article logic.`

第 27-28 行（Key quirks）：
```markdown
# 改前
- **Two parallel scraper implementations** (sync + async). They share some but not all features (e.g., content keyword filtering differs). Keep both in sync when adding features.
# 改后
- **PDF 生成**：每爬取一篇文章后立即生成 PDF，利用处理时间作为自然反爬间隔。
```

第 30 行：删除 `- **\`async_utils.py\` duplicates** \`ImageBlockConverter\` from \`utils.py\`. Both files have their own copy.`

- [ ] **Step 4: 更新 README.md**

第 114 行：删除 `│   │   ├── async_utils.py  # 异步工具`

第 129 行：
```markdown
# 改前
- **异步处理**: asyncio + aiohttp
# 改后
- **网络请求**: requests + BeautifulSoup
```

- [ ] **Step 5: 验证整体运行**

Run: `python run_gui.py`
Expected: 程序正常启动，无明显错误。

或者至少验证 import 链：
Run: `python -c "from spider.wechat.scraper import BatchWeChatScraper; from spider.wechat.pdf_utils import generate_single_article_pdf; print('All imports OK')"`
Expected: `All imports OK`


### Task 6: 验证运行 + commit

- [ ] **Step 1: 最终验证**

Run: `python -c "
import ast
for f in ['spider/wechat/scraper.py', 'spider/wechat/pdf_utils.py', 'gui/workers.py', 'gui/pages/unified_scrape_page.py']:
    ast.parse(open(f).read())
print('All files syntax OK')
"`
Expected: `All files syntax OK`

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "refactor: 移除异步爬虫，改为逐篇生成PDF，修复request_interval配置"
```
