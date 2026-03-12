# 迭代设计：交互式命令行多轮对话

> 基于 `dpskv32_mtc_demo0211.py`，将固定输入的 Demo 改为命令行交互式任意轮次对话

## 1. 当前问题

`dpskv32_mtc_demo0211.py` 的 `__main__` 部分使用**硬编码指令**运行固定的 Turn1/Turn2：

```python
# 当前方式：固定输入
user_query_1 = "帮我在店铺 store_001 上架一款时尚帆布包..."
messages = [{"role": "user", "content": user_query_1}]
run_with_dynamic_tools(user_query_1, messages)

user_query_2 = "再帮我在 Instagram 和 Facebook 上发一条推广帖子..."
messages.append({"role": "user", "content": user_query_2})
run_with_dynamic_tools(user_query_2, messages)
```

**局限性**：无法演示真正的交互体验，演示者不能根据前一轮的执行结果灵活调整下一轮指令。

---

## 2. 目标

改为 **REPL 风格的命令行交互**：
- 演示者通过 `input()` 输入任意指令
- 系统执行完整的 "工具筛选 → 边思考边调用 → 输出结果" 流程
- 等待下一轮输入，轮次无限制
- 支持特殊命令（退出、重置对话、查看状态等）
- 多轮对话共享 `messages` 上下文，保持连贯性

---

## 3. 变更范围

**只改动 `__main__` 部分**（第 800-835 行），其余模块（工具注册表、筛选函数、执行函数等）完全不动。

---

## 4. 实现方案

### 4.1 交互式主循环

```python
# ============================================================
# 10. 主程序 —— 交互式命令行多轮对话
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  电商 SaaS 动态工具选择 — 交互式 Demo")
    print(f"  已注册工具: {len(org_tools_registry)} 个（7大类）")
    print("=" * 60)
    print("输入你的指令开始对话，支持以下特殊命令：")
    print("  /quit  或 /exit  — 退出程序")
    print("  /reset           — 清空对话历史，开启新会话")
    print("  /history         — 查看当前对话轮次数")
    print("  /tools           — 列出所有可用工具摘要")
    print("=" * 60)

    messages = []
    turn = 0

    while True:
        # ===== 等待用户输入 =====
        try:
            user_input = input(f"\n[Turn {turn + 1}] 你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # ===== 特殊命令处理 =====
        if user_input.lower() in ("/quit", "/exit"):
            print("再见！")
            break

        if user_input.lower() == "/reset":
            messages = []
            turn = 0
            print("[系统] 对话已重置，你可以开始新的会话。")
            continue

        if user_input.lower() == "/history":
            user_turns = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
            print(f"[系统] 当前会话已进行 {user_turns} 轮对话，messages 共 {len(messages)} 条。")
            continue

        if user_input.lower() == "/tools":
            print("[系统] 可用工具列表：")
            for i, t in enumerate(tools_summary, 1):
                print(f"  {i:2d}. {t['name']}: {t['description']}")
            continue

        # ===== 正常对话流程 =====
        turn += 1

        # 非首轮时清除历史 reasoning_content 节省上下文
        if turn > 1:
            clear_reasoning_content(messages)

        messages.append({"role": "user", "content": user_input})

        print(f"\n{'#' * 60}")
        print(f"# Turn {turn}")
        print(f"{'#' * 60}")

        try:
            run_with_dynamic_tools(user_input, messages)
        except Exception as e:
            print(f"\n[错误] 执行过程中出现异常: {e}")
            print("[系统] 你可以继续输入新指令，或输入 /reset 重置对话。")
```

### 4.2 交互流程图

```
┌──────────────────────────────┐
│      启动程序，显示欢迎信息     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│   input() 等待用户输入         │◄──────────────────────┐
└──────────────┬───────────────┘                        │
               │                                        │
               ▼                                        │
        ┌──────────────┐                                │
        │  是特殊命令？   │──── /quit ────► 退出程序       │
        └──────┬───────┘                                │
          否   │   是                                    │
               ├── /reset ──► 清空 messages ──────────► │
               ├── /history ─► 显示轮次信息 ────────────► │
               └── /tools ───► 列出工具摘要 ────────────► │
               │                                        │
               ▼                                        │
┌──────────────────────────────┐                        │
│ turn > 1 时:                  │                        │
│  clear_reasoning_content()   │                        │
│ messages.append(user_input)  │                        │
└──────────────┬───────────────┘                        │
               │                                        │
               ▼                                        │
┌──────────────────────────────┐                        │
│  run_with_dynamic_tools()    │                        │
│  · 阶段一：LLM 筛选工具       │                        │
│  · 阶段二：边思考边调用        │                        │
│  · 运行时增补（如需）          │                        │
│  · 输出最终回复               │                        │
└──────────────┬───────────────┘                        │
               │                                        │
               └────────────────────────────────────────┘
```

---

## 5. 关键设计点

### 5.1 对话上下文连续性

`messages` 列表在所有轮次间共享，LLM 能感知前几轮的对话内容和工具执行结果。例如：

```
Turn 1: "帮我上架一个帆布包"           → create_physical_product → 返回 prod_abc123
Turn 2: "给刚才那个帆布包做个八折活动"  → LLM 从上下文知道 prod_abc123 → create_product_discount
Turn 3: "看下今天的店铺数据"            → 工具重新筛选 → daily_report
```

### 5.2 每轮工具独立筛选

每轮输入都会**重新调用 `select_tools_by_llm`** 筛选工具，因为用户可能在不同轮次中涉及完全不同的业务领域。这与 `dpskv32_mtc_demo0211.py` 中 Turn1/Turn2 分别调用 `run_with_dynamic_tools` 的逻辑一致。

### 5.3 上下文裁剪时机

从第 2 轮开始，在 append 新用户消息前调用 `clear_reasoning_content(messages)`，与原始设计保持一致，节省网络带宽。

### 5.4 异常容错

`run_with_dynamic_tools` 外层包裹 `try/except`，API 调用失败或 JSON 解析错误不会导致程序崩溃，演示者可以继续下一轮或 `/reset`。

---

## 6. 演示效果预览

```
============================================================
  电商 SaaS 动态工具选择 — 交互式 Demo
  已注册工具: 25 个（7大类）
============================================================
输入你的指令开始对话，支持以下特殊命令：
  /quit  或 /exit  — 退出程序
  /reset           — 清空对话历史，开启新会话
  /history         — 查看当前对话轮次数
  /tools           — 列出所有可用工具摘要
============================================================

[Turn 1] 你> 帮我在 store_001 上架一款手机壳，售价 39 元

############################################################
# Turn 1
############################################################

============================================================
[阶段一] 正在根据用户指令筛选工具...
[阶段一] 初始筛选结果: ["create_physical_product"]
[阶段一] 已加载工具: ["create_physical_product", "select_tools_by_llm"]
============================================================

--- Sub-turn 1 ---
[思考] 用户想创建一个实物商品...
[工具调用] create_physical_product
[参数] {"store_id": "store_001", "title": "时尚手机壳", "price": 39}
[执行结果] {"status": "success", "data": {"product_id": "prod_x7k9m2"...}}

--- Sub-turn 2 ---
[回复] 已成功上架手机壳商品（ID: prod_x7k9m2），售价 39 元。

[Turn 2] 你> 给这个手机壳搞个限时八折

############################################################
# Turn 2
############################################################
...（工具筛选 → 增补/调用 → 输出结果）...

[Turn 3] 你> /history
[系统] 当前会话已进行 2 轮对话，messages 共 8 条。

[Turn 3] 你> /quit
再见！
```

---

## 7. 变更对比总结

| 维度 | 0211 版（当前） | 0224 版（目标） |
|:---:|:---:|:---:|
| 输入方式 | 硬编码固定指令 | `input()` 命令行交互 |
| 对话轮次 | 固定 2 轮 | 无限制 |
| 灵活性 | 每次修改需改代码 | 运行时任意输入 |
| 特殊命令 | 无 | `/quit` `/reset` `/history` `/tools` |
| 异常处理 | 无（崩溃退出） | `try/except` 容错继续 |
| 代码改动范围 | — | 仅 `__main__` 部分（~50行） |
| 上游模块 | — | 完全不变 |
