# mission

本仓库包含一个本地优先的 TodoList / 任务成长系统需求文档，以及一个 Windows 桌面端原型应用。

## 需求文档

- [本地部署 TodoList / 任务成长系统详细开发需求清单](docs/todolist-requirements.md)

## Windows 端原型

该原型使用 Python 标准库 `tkinter` + `sqlite3` 实现，默认数据保存在用户目录的 `.mission_todolist/mission.db`。

### 功能覆盖

- 今日任务列表与最小任务完成确认。
- 项目任务树与父任务进度自动加权计算。
- AI / 本地规则任务拆分入口，支持配置 OpenAI 兼容 API 或本地大模型服务。
- 代币奖励流水与余额展示。
- Anki 类型记忆卡片基础管理、复习、CSV/APKG 导入导出。
- Markdown 杂记保存与 JSON 备份导出。

### 运行

```bash
python -m mission_app
```

### 测试

```bash
python -m pytest
```
