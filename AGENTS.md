# WeChatSpider — Agent Guide

## Quick start

```bash
pip install -r requirements.txt
python run_gui.py             # dev run
cd script && build.bat        # PyInstaller build (Windows only)
```

## Architecture

- `run_gui.py` — single entrypoint. Sets `sys.path`, checks deps, launches PyQt6 app.
- `gui/` — PyQt6 + qfluentwidgets (Fluent Design) UI. Dark theme only. WeChat green `#07C160`.
- `spider/` — core library, no GUI dependency. Can be imported standalone.
  - `spider.wechat.login` — Selenium-based QR login to mp.weixin.qq.com, caches token+cookies.
  - `spider.wechat.scraper` — three scraper classes: `WeChatScraper` (single), `BatchWeChatScraper` (ThreadPoolExecutor), `AsyncBatchWeChatScraper` (aiohttp).
  - `spider.wechat.utils` — sync HTTP + HTML parsing (requests + BeautifulSoup + markdownify).
  - `spider.wechat.async_utils` — async HTTP (aiohttp). Parallel copy of image/article logic.
  - `spider.log.utils` — loguru-based, auto-adapts to dev/frozen env.
- `config.json` — runtime config: `request_interval`, `max_workers`, `include_content`, `cache_expire_hours`.

## Key quirks

- **Import order matters**: `QApplication` must be created before `qfluentwidgets` is imported. Both `run_gui.py` and `gui/app.py:run_app()` enforce this.
- **Label transparency bug**: `qfluentwidgets` labels show white background in dark mode. Workaround in `gui/app.py:apply_label_transparent_background()`. Apply via `QTimer.singleShot(100, ...)` after page creation.
- **Two parallel scraper implementations** (sync + async). They share some but not all features (e.g., content keyword filtering differs). Keep both in sync when adding features.
- **Cross-module import**: `spider.wechat.login` imports `gui.utils.get_wechat_cache_file()`. The `gui` module must be importable when using login.
- **No tests, no CI, no linter, no formatter** — all absent. Add them if needed; nothing exists to break.
- **`async_utils.py` duplicates** `ImageBlockConverter` from `utils.py`. Both files have their own copy.
- **Cache dirs**: login token → user app data dir (cross-platform via `gui/utils.py`); article cache → `.cache/` in project root.

## Build

- Windows-only: PyInstaller via `WeChatSpider.spec`. Run `cd script && build.bat` or `build_installer.bat`.
- NSIS installer creation is part of the build scripts. UPX compression optional.
- Audio files (`mic/*.mp3`), `config.json`, and icon are bundled via spec file.

## Conventions

- All docstrings are in Chinese. Code comments follow the same language.
- Convention-based commit prefixes used in history: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:`.
- Python 3.8+ target, no type checking enforced (typing imports exist but are partial).
