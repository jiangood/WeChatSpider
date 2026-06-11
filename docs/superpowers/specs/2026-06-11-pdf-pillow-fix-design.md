# PDF 生成修复设计

## 问题

1. PyInstaller EXE 中 Pillow 被显式排除，导致 `fpdf2` 无法插入图片，PDF 生成全部失败
2. PDF 生成失败被各层 catch 吞噬，GUI 仍显示"完成"，用户无法感知

## 修复方案

### Bug 1: Pillow 缺失

**修改文件：**
- `requirements.txt` — 添加 `Pillow>=10.0.0`
- `WeChatSpider.spec:137-138` — 从 `excludes` 列表中移除 `'PIL'` 和 `'Pillow'`

**效果：** PyInstaller 自动打包 Pillow，`fpdf2` 可正常处理图片。

### Bug 2: GUI 感知 PDF 失败（基础版）

在爬虫中跟踪 PDF 成功/失败计数，通过回调系统上报到 GUI，在完成提示中展示统计。

#### 数据流

```
generate_single_article_pdf() → 返回 pdf_path (成功) 或 None (失败)
    ↓
_scrape_single_account() 跟踪 pdf_success/pdf_fail 计数器
    ↓ 通过回调
BatchScrapeWorker.pdf_progress 信号 (account_name, pdf_success, pdf_fail)
    ↓
UnifiedScrapePage _on_scrape_success() 汇总显示
```

#### 具体改动

**`spider/wechat/scraper.py`** — `_scrape_single_account()`：
- 新增 `pdf_success = 0` / `pdf_fail = 0` 计数器
- 检查 `generate_single_article_pdf()` 返回值，递增对应计数器
- 调用 `self._trigger_callback('pdf_progress', account_name, pdf_success, pdf_fail)`
- 将 `pdf_success` / `pdf_fail` 计入每篇文章的返回数据中

**`spider/wechat/scraper.py`** — `BatchWeChatScraper`：
- `start_batch_scrape()` 返回 `(articles, pdf_stats)` 元组，或 articles 中嵌入 PDF 状态

**`gui/workers.py`** — `BatchScrapeWorker`：
- 新增 `pdf_progress = pyqtSignal(str, int, int)` 信号
- run() 中连接 `pdf_progress` 回调
- 累计最终 `self.pdf_success_total` / `self.pdf_fail_total`
- `scrape_success` 信号或新增信号传递 PDF 统计

**`gui/pages/unified_scrape_page.py`**：
- 连接 `pdf_progress` 信号
- `_on_scrape_success()` 改为显示 `"完成！共 N 篇文章，PDF 成功 S 篇，失败 F 篇"`
- 有 PDF 失败时，完成文字用黄色（警告色）
