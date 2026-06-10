# PDF 导出功能设计文档

## 概述

在爬取公众号文章的同时，自动将每篇文章导出为 PDF 文件，目录结构为 `公众号名称/年月/文章标题.pdf`。保留现有 CSV 导出，PDF 为新增输出。

## 依赖

- `fpdf2` — 纯 Python PDF 生成库，无系统级依赖
- 中文字体：自动检测系统 `msyh.ttc`（微软雅黑），找不到则提示用户

## 架构

新模块 `spider/wechat/pdf_utils.py`，纯函数设计，不含 GUI 依赖。

### 数据流

```ascii
爬取文章列表 → 获取内容(Markdown) → 下载图片缓存 → 生成 PDF → 保存 CSV
                                        ↑
                                   缓存检查去重
```

### 图片缓存

- 缓存目录：`{output_dir}/.imgcache/`
- 文件名：`{md5(url)}.{ext}`
- 下载前检查文件是否存在，存在即跳过
- 使用 `aiohttp` 并发下载，控制在 `max_concurrent_requests` 内

### PDF 生成

核心函数：

```python
def generate_article_pdfs(
    articles: list[dict],
    base_output_dir: str,
    font_path: str,
    img_cache_dir: str | None = None,
) -> list[str]:
    """为每篇文章生成独立 PDF，返回生成的文件路径列表"""
```

每篇文章的 PDF 路径：

```
{base_output_dir}/{account_name}/{YYYY-MM}/{sanitized_title}.pdf
```

### Markdown → PDF 渲染对照

| Markdown | fpdf2 |
|---|---|
| `# 标题` | `set_font(size=18, style='B')` + `multi_cell` |
| `## 子标题` | `set_font(size=15, style='B')` + `multi_cell` |
| `###` 及以下 | 递减字号 |
| 段落 | `set_font(size=11)` + `multi_cell` |
| `**加粗**` | A 字体 + B 样式分片渲染 |
| `![alt](path)` | `image(path, w=170)`，居中或左对齐 |
| `> 引用` | 缩进 + 斜体 |
| 空行 | `ln(4)` |

Markdown → 可渲染元素的转换使用简化的行解析器（不引入 `markdown` 包，减少依赖）。

### 集成点

修改 `spider/wechat/scraper.py`：

在 `AsyncBatchWeChatScraper._async_scrape_all()` 中，内容获取完成后、CSV 保存之前：

```python
# 保存 CSV（现有）
if output_file:
    save_to_csv(all_articles, output_file)

# 生成 PDF（新增）
if config.get('generate_pdf', True):
    generate_article_pdfs(
        all_articles,
        base_output_dir=config.get('output_dir', DEFAULT_OUTPUT_DIR),
        font_path=find_chinese_font(),
        img_cache_dir=img_cache_dir,
    )
```

### 进度回调

PDF 生成阶段的进度通过已有回调机制上报：

```python
callback('pdf_progress', {
    'current': i,
    'total': n,
    'article': article['title'],
})
```

### 字体检测

```python
def find_chinese_font() -> str:
    """自动检测系统可用的中文字体路径"""
    candidates = [
        # Windows
        r'C:\Windows\Fonts\msyh.ttc',       # 微软雅黑
        r'C:\Windows\Fonts\msyhbd.ttc',     # 微软雅黑加粗
        r'C:\Windows\Fonts\simsun.ttc',     # 宋体
        r'C:\Windows\Fonts\SIMHEI.TTF',     # 黑体
        # 可扩展
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError('未找到中文字体，请安装微软雅黑或宋体')
```

## 错误处理

- 单篇文章 PDF 生成失败不影响其他文章
- 失败日志记录文章标题和错误原因，继续处理下一篇
- 图片下载失败跳过，PDF 中对应位置留空或显示占位符

## GUI 调整

设置页面（`gui/pages/settings_page.py`）增加一个开关：

- "导出 PDF"（`FluentSwitch`）
- 对应 config.json 的 `generate_pdf` 字段

爬取页面进度表格增加 "PDF" 状态列（可选）。
