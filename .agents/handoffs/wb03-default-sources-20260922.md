# 构造默认实参来源交接

- 日期：2026-09-22；分支 `wb03-source-ast`，基线 `de8d237`。中文回复，直接提交及推送，不创建 PR。
- 实现：`constructor_arguments.py` 按已精确关联的直接构造声明及参数位置恢复
  无子节点默认实参的本地 literal 来源；不修改原调用点 AST。来源 ID 唯一性、
  重声明及不支持表达式检查失败时 unknown。已有带子节点路径保持原行为。
- 检查：`constructor_values.py` 独立核对报告内部参数/字段位置与 ID、声明
  initializer、类型、转换证据及括号类型连续性；显式 ABI 下检查值保持。
  不重新扫描完整 TU，前端来源真实性/唯一性仍为报告列明的可信前提。
- 回归：真实 Clang C++20 fixture 使用默认 7/13，而非只测 1；覆盖调用、
  consteval、重声明、窄化、缺失/共享来源、绑定篡改及异常括号类型。
- 实际命令：`make check`（537 项通过）、`make demo`（通过）、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'`
  （70 项通过）。AOCC Clang 17。ROCm Clang 23 下 defaults/direct 定向
  11 项中 9 项通过、2 项跳过：新版 AST 直接提供默认子节点，不经过补全路径。
- Sol 子代理只读复核后，补充显式前提及括号类型检查；没有签发整核保证。
- 完整 TU 最终命令：`PYTHONPATH=src python3 artifacts/wb03-default-final-3hy7UB/run.py`。
  工件 `artifacts/wb03-default-final-3hy7UB/report.json`，SHA-256
  `f605b190504984a364dd59c779d1bcd8e9a644b76a593530f243a291fc993f1b`。
  输入固定 AST SHA-256 为
  `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`，
  3,705,324 节点、显式 400 万预算；三个实现文件前后哈希一致。未用投影替代 root。
  原 block 构造参数 1/2 分别绑定 `0x248fac90`/`0x248fad10`，得到字面量 1；
  参数 0 的 min 仍 `unsupported_argument_expression`，整体参数和值检查 unknown。
  launch copy 身份 inspected、字段值 unknown。四个相同 launch AST 出现不是四次执行。
  本次是既有 development TU 重放，不是新的独立 holdout 成功。
- 未执行：GPU、性能评测、新 holdout、真实适配候选部署。
- 下一步：连接真实动态 block 首实参的受限值语义，并单独处理复制与初始化到
  launch 的保持性；不能将两个默认常量恢复视为实际 launch 域通过。
