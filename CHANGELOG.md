# Changelog

## [1.2.0] — 2026-04-10

### Added

- **因子截面**：`src/factors/cross_section.py`（`compute_cross_section_row`）、`GET /api/factors/cross-section`、`scripts/export_factor_cross_section.py`（批量窗口拉数、legacy / auto-fallback）。
- **看板**：`frontend/src/composables/crossSectionOverviewLink.js`；行情侧栏与因子预览页眉链至截面 JSON。
- **栈探测**：`scripts/verify_stack.py` 在 `dashboard/overview` 有指数日期时烟囱截面接口（否则 `[SKIP]`）。
- **测试**：`tests/test_factors_cross_section.py`、`tests/test_export_factor_cross_section.py`、因子 HTTP 截面用例、`verify_stack` 响应形态用例。
- **文档**：`docs/FACTORS.md` 截面 HTTP；`docs/PHASE_B_GAP_AND_NEXT.md`、`experiments/README.md`；`FIRST_STEPS.md` / `README.md` / `.env.example` 同步说明。
- **趋势 v0 / 回测等**：仓库内相关脚本、契约文档与配置样例（与本版本一并归档）。

### Changed

- **OpenAPI**：`docs/openapi.json` 含截面路由与模型。
- **前端**：回测面板、E2E 固件与 Playwright 配置等与当前 API 契约对齐。
