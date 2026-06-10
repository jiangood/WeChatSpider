# 简化架构：移除异步模式 + 改为逐篇生成 PDF

## 背景

当前代码库维护着两套并行的爬虫实现：

- **同步路径**: `BatchWeChatScraper` (基于 requests + ThreadPoolExecutor)
- **异步路径**: `AsyncBatchWeChatScraper` (基于 aiohttp + asyncio)

两套实现功能重叠，但细节不一致（如 `request_interval` 在异步路径中未正确应用）。维护两套代码成本高。

此外，PDF 生成目前是在所有文章爬取完成后**批量**进行的，不能利用 PDF 的 I/O 耗时作为反爬间隔。

## 目标

1. 移除异步爬虫及相关代码，只保留同步路径
2. 改为「爬取一篇文章 → 立即生成该篇 PDF → 再爬下一篇」，利用 PDF 处理时间作为自然间隔
3. 修复 `request_interval` 配置值被除以 10 的 bug

## 设计方案

### 文件变更总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `spider/wechat/async_utils.py` | 🗑️ 删除 | 986 行，整个文件 |
| `spider/wechat/pdf_utils.py` | 🛠️ 改造 | 移除 async 函数，新增单篇 PDF 生成函数 |
| `spider/wechat/scraper.py` | 🛠️ 改造 | 删除 AsyncBatchWeChatScraper 类，同步路径增加逐篇 PDF |
| `gui/workers.py` | 🛠️ 改造 | 删除 AsyncBatchScrapeWorker 类 |
| `gui/pages/unified_scrape_page.py` | 🛠️ 改造 | 改用 BatchWeChatScraper + BatchScrapeWorker |
| `WeChatSpider.spec` | 🛠️ 更新 | 移除 async_utils 隐藏导入 |
| `AGENTS.md` | 🛠️ 更新 | 移除 async 相关描述 |
| `README.md` | 🛠️ 更新 | 移除 async_utils 文件树条目 |

### 1. 删除 `spider/wechat/async_utils.py`

移除以下内容（全部 986 行）：
- `ImageBlockConverter` 类（`utils.py` 有原件，不受影响）
- `AsyncWeChatClient` 类（aiohttp 客户端）
- `format_time` 函数
- `async_scrape_account` 函数
- `async_scrape_accounts_batch` 函数
- `run_async_scrape` 函数

### 2. 改造 `spider/wechat/pdf_utils.py`

**删除：**
- `aiohttp` 导入
- `asyncio` 导入
- `download_images_for_pdf` async 函数
- `generate_article_pdfs` async 函数

**改造：**
- `generate_article_pdfs_sync` → 改为纯同步实现（使用 `requests` 下载图片，不再依赖 event loop）
- 新增 `generate_single_article_pdf(article, base_output_dir, font_path, headers)` → bool
  - 参数：单篇 article 字典（含 `content`, `title`, `name`, `publish_time` 等字段）
  - 内部流程：从 `article['content']` 提取 Markdown → 下载图片到 `.imgcache` → 渲染 PDF → 写入 `公众号/日期_标题.pdf`
  - PDF 生成失败只 `log.warning` 返回 `False`，不抛出异常

### 3. 改造 `spider/wechat/scraper.py`

**删除：**
- `import asyncio`
- `from spider.wechat.pdf_utils import generate_article_pdfs, find_chinese_font`（顶部 async 版导入）
- `AsyncBatchWeChatScraper` 整个类（约 759-1027 行）

**改造 `BatchWeChatScraper`：**

#### `_scrape_single_account()`（约 628 行）

```
改前: 获取内容 → sleep(1-1秒) → 下一篇 → ... → 全部完 → 批量 PDF
改后: 获取内容 → 生成单篇 PDF → sleep(1-3秒) → 下一篇
```

- 在 `article = self.scraper.get_article_content_by_url(article)` 之后
- 检查 `config.get('generate_pdf', True)`，调用 `generate_single_article_pdf`
- `find_chinese_font()` 只在第一次调用，结果缓存
- PDF 失败不中断循环
- sleep 缩短为 `random.uniform(1, 3)`（兜底间隔，PDF 生成本身已消耗时间）

#### `start_batch_scrape()`（约 467 行）

- 删除末尾的批量 PDF 生成代码块

#### 修复 `request_interval`

`random.uniform(1, config.get('request_interval', 60) / 10)` 改为 `random.uniform(1, config.get('request_interval', 60))`

### 4. 改造 `gui/workers.py`

删除 `AsyncBatchScrapeWorker` 整个类（约 150-270 行）。
`BatchScrapeWorker` 保持不动。

### 5. 改造 `gui/pages/unified_scrape_page.py`

- 导入改为 `from spider.wechat.scraper import BatchWeChatScraper`
- `self.batch_scraper = BatchWeChatScraper()`
- 改用 `BatchScrapeWorker`

### 6. 配置更新

- `WeChatSpider.spec`: 移除 `'spider.wechat.async_utils'`
- `AGENTS.md`: 移除 async_utils 和 AsyncBatchWeChatScraper 描述
- `README.md`: 移除 async_utils.py 条目

## 边界情况

- PDF 字体不存在：`find_chinese_font()` 失败时仅 log.warning，`generate_pdf` 配置视为 False，正常爬取不生成 PDF
- 单篇 PDF 生成失败：log.warning 后继续下一篇，不中断整批爬取
- `generate_pdf: false`：不走 PDF 生成逻辑，保持现有纯 sleep 间隔
- `.imgcache/` 目录：图片下载仍写入同一缓存目录，不同文章间共享缓存

## 不改的文件

`run_gui.py`, `gui/app.py`, `gui/main_window.py`, `gui/pages/login_page.py`, `gui/pages/settings_page.py`, `gui/utils.py`, `gui/styles.py`, `gui/widgets.py`, `gui/history_manager.py`, `spider/wechat/login.py`, `spider/wechat/run.py`, `spider/wechat/utils.py`, `spider/wechat/__init__.py`
