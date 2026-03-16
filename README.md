# nanoshopagent

Nano Shop Agent: 电商 SaaS 场景的 **动态工具选择 + LLM Loop（Plan/Act/Observe）** 的工程化 demo。

## Features

- OpenAI-compatible client（默认 DeepSeek / OpenAI 协议）
- 工具注册表（tool registry）+ mock/real executor
- 多步 agent loop（plan/act/observe）
- 上下文剪裁（避免 token 爆炸）
- 轨迹落盘 & 脱敏（redact）

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DEEPSEEK_API_KEY=...
export DEEPSEEK_BASE_URL=https://api.deepseek.com
python -m nanoshopagent.cli.chat
```

## Notes

- 默认使用 OpenAI-compatible client。
- 如需替换模型/供应商，优先通过环境变量或在 `nanoshopagent/core/llm_client.py` 中配置。

## References

- DeepSeek API Docs — 思考模式（thinking_mode）
  - https://api-docs.deepseek.com/zh-cn/guides/thinking_mode

## License

MIT (see `LICENSE`).
