# nanoshopagent

Nano Shop Agent: 电商 SaaS 动态工具选择 + LLM Loop（Plan/Act/Observe）demo 的工程化重构。

## Quickstart

```bash
export DEEPSEEK_API_KEY=...
export DEEPSEEK_BASE_URL=...
python -m nanoshopagent.cli.chat
```

## Notes

- 默认使用 OpenAI-compatible client（DeepSeek）。
- 支持工具注册表、mock/real executor、上下文剪裁与轨迹落盘。
