# PDF 生成修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** 修复 EXE 运行时 PDF 全部失败但 GUI 误报"完成"的问题

**Architecture:** 两处独立修复：(1) 构建层——Pillow 加入依赖并从 spec excludes 移除；(2) 运行时层——爬虫追踪 PDF 成功/失败计数并通过回调→信号→GUI 展示

**Tech Stack:** Python, PyInstaller, PyQt6, fpdf2, Pillow

---

### Task 1: 修复 Pillow 排除

**Files:**
- Modify: `requirements.txt:29` — 添加 Pillow
- Modify: `WeChatSpider.spec:137-138` — 移除 PIL/Pillow 排除

- [ ] **Step 1: requirements.txt 添加 Pillow**

在文件末尾添加一行 `Pillow>=10.0.0`。

- [ ] **Step 2: spec 排除列表中移除 PIL/Pillow**

删除 `WeChatSpider.spec` 第 137-138 行的 `'PIL',` 和 `'Pillow',`。

---

### Task 2: 爬虫追踪 PDF 状态

**Files:**
- Modify: `spider/wechat/scraper.py:575-658` — `_scrape_single_account()` 方法

- [ ] **Step 1: 在 `_scrape_single_account()` 中添加 PDF 计数器**

在 `articles_in_range` 过滤之后（`config.get('include_content', False)` 之前），添加 `pdf_success` / `pdf_fail` 变量：

```python
        # 获取文章内容
        if config.get('include_content', False) and articles_in_range:
            total_content = len(articles_in_range)
            pdf_success = 0
            pdf_fail = 0
            self._trigger_account_status(account_name, "content", ...)
```

- [ ] **Step 2: 检查 PDF 返回值并计数**

将 PDF 生成部分改为：

```python
                    if config.get('generate_pdf', True):
                        try:
                            from spider.wechat.pdf_utils import generate_single_article_pdf, find_chinese_font
                            font_path = find_chinese_font()
                            output_dir = config.get('output_dir', '')
                            if output_dir:
                                result = generate_single_article_pdf(article, output_dir, font_path, headers=config.get('headers'))
                                if result:
                                    pdf_success += 1
                                else:
                                    pdf_fail += 1
                        except FileNotFoundError as e:
                            logger.warning(f"PDF生成跳过（字体未找到）: {e}")
                            config['generate_pdf'] = False
                        except Exception as e:
                            logger.error(f"PDF生成失败: {e}")
                            pdf_fail += 1
```

- [ ] **Step 3: 触发 PDF 进度回调**

在文章循环结束后（`return articles_in_range` 之前），触发 PDF 状态回调：

```python
            # 通知 PDF 生成状态
            self._trigger_pdf_progress(account_name, pdf_success, pdf_fail)
        
        return articles_in_range
```

- [ ] **Step 4: 添加 `_trigger_pdf_progress` 方法**

在 `BatchWeChatScraper` 的 `_trigger_*` 方法组中（第 727 行附近）添加：

```python
    def _trigger_pdf_progress(self, account_name, pdf_success, pdf_fail):
        """触发PDF生成进度回调"""
        if self.callbacks.get('pdf_progress'):
            self.callbacks['pdf_progress'](account_name, pdf_success, pdf_fail)
```

- [ ] **Step 5: `set_callback` 初始化时添加 `pdf_progress` 键**

确保 `set_callback` 方法或 `callbacks` 初始化包含 `'pdf_progress': None`。

---

### Task 3: Worker 传递 PDF 状态信号

**Files:**
- Modify: `gui/workers.py:37-143` — `BatchScrapeWorker`

- [ ] **Step 1: 添加 `pdf_progress` 信号**

在信号定义区（第 57-62 行）添加：

```python
    pdf_progress = pyqtSignal(str, int, int)
```

- [ ] **Step 2: 连接回调**

在 `run()` 方法的回调设置区域（第 123-128 行）添加：

```python
            def pdf_progress_callback(account_name, pdf_success, pdf_fail):
                if not self.is_cancelled:
                    self.pdf_progress.emit(account_name, pdf_success, pdf_fail)
            
            self.batch_scraper.set_callback('pdf_progress', pdf_progress_callback)
```

---

### Task 4: GUI 显示 PDF 统计

**Files:**
- Modify: `gui/pages/unified_scrape_page.py:420-514` — `_on_start_scrape` 和 `_on_scrape_success`

- [ ] **Step 1: 初始化 PDF 统计变量**

在 `_on_start_scrape` 中（第 426-428 行附近）添加：

```python
        self._pdf_success = 0
        self._pdf_fail = 0
```

- [ ] **Step 2: 连接 pdf_progress 信号**

在 `_on_start_scrape` 信号连接区（第 433-438 行）添加：

```python
        self.scrape_worker.pdf_progress.connect(self._on_pdf_progress)
```

- [ ] **Step 3: 实现 `_on_pdf_progress` 槽函数**

```python
    def _on_pdf_progress(self, account_name, pdf_success, pdf_fail):
        """累计PDF生成进度"""
        self._pdf_success += pdf_success
        self._pdf_fail += pdf_fail
```

- [ ] **Step 4: 修改 `_on_scrape_success` 显示 PDF 统计**

将第 497-499 行改为：

```python
        self.progress_widget.set_complete(f"爬取完成！")
        if self._pdf_fail > 0:
            self.status_hint.setText(f"完成！共 {len(articles)} 篇文章，PDF 成功 {self._pdf_success} 篇，失败 {self._pdf_fail} 篇")
            self.status_hint.setStyleSheet(f"color: {COLORS['warning']};")
        else:
            self.status_hint.setText(f"完成！共 {len(articles)} 篇文章，PDF 全部生成成功")
            self.status_hint.setStyleSheet(f"color: {COLORS['success']};")
```
