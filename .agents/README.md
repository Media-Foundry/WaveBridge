# 协作目录

本目录保存项目协作规范。根 `AGENTS.md` 是统一入口；这里的角色文件需要按任务显式读取，不依赖任何工具自动发现或自动启动 agent。

始终用中文向用户说明结果、证据和局限。代码标识符使用英文。

## 任务路由

| 任务 | 先读 | 主要产物 |
| --- | --- | --- |
| 核实研究差异、纳入真实案例 | `roles/research.md` | 有来源的能力表、共同案例和主张状态 |
| 源码接入、关系 IR、自动恢复 | `roles/semantics.md` | 支持子集、带来源的关系与 oracle 对照 |
| 检查算法、保证边界、负例 | `roles/verification.md` | 独立 checker、范围声明和回归样例 |
| 候选生成、kernel/launch 改写 | `roles/transforms.md` | 未签发结论的完整候选工件 |
| 语料、基线、设备执行、统计 | `roles/evaluation.md` | 可复现原始证据和协议内指标 |
| 架构集成、版本、CI、交接 | `roles/integration.md` | 一致的接口、验证记录和状态更新 |

所有任务使用 `workflows/change.md`。研究能力从提案进入实现时同时使用 `workflows/research-gates.md`。

这些是职责而非必须并行运行的机器人。单个执行者可以依次承担多个角色；只有用户或适用规则明确要求时才委派子代理。生成器与 checker 的实现依赖和验收证据仍需分开。

## 文件约定

- `templates/task.md`：有范围、验收和依赖的任务定义。
- `templates/handoff.md`：中文交接，绑定实际产物和验证。
- `templates/review.md`：审查语义、测试和研究表述。
- 临时执行记录放在 `artifacts/`；长期有效的状态更新到 `docs/status.md`。
- 不在本目录保存访问令牌、机器密码或未经核实的“通过”记录。
