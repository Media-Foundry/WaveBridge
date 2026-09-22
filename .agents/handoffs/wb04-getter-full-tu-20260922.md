# 交接：完整 TU getter 检查预算

- 日期、分支、基线：2026-09-22，wb03-source-ast，b2999e0；中文回复，直接提交推送。
- 用户目标：将条件检查推进到完整真实翻译单元，不把 AST 投影当作完整源码。
- 已完成：固定 vLLM AST 全量扫描计数 3,705,324，目标 getter/leaf 各唯一；
  原默认 1,000,000 不足。getter 两入口现支持显式正整数预算，默认不变，
  硬上限 10,000,000。仍完整扫描、严格声明唯一性、相同调用/表达式深度门控。
- 预算扫描：`PYTHONPATH=src python3 artifacts/wb04-getter-budget-iaDVzt/inspect.py`。
  原始报告 SHA256：8ca2e033faa9b8778c180df7a8d5047be0b03a6930c1d2ca5e47fb969bfc3cd1。
  加载约23.76秒，计数约1.80秒；这是单次工程观测，不是性能实验。
- 实际本地验收：make check 506 项、make demo、48 项 Clang 专项测试通过；预算精确边界、布尔/越界拒绝、
  放宽预算后同ID重复声明仍拒绝均有回归。
- 历史 CI：b2999e0 的 run35734829006 success；不代表本轮新提交的 CI。
- Sol 只读复核：receiver 求值仍未建立，不能直接将 initializer_value.link 与
  wrapper 无写结论组合为完整属性无写。receiver 声明唯一性、存储期、调用点和
  实际坐标域仍需检查，column_loops 不放宽。
- 资源边界：节点参数不限制前置解析/哈希成本，不是总内存或时间沙箱。
- 没有执行：GPU、候选生成、整核关系验收；原 vLLM holdout 拒绝不变。
- 完整 TU 最终诊断：`PYTHONPATH=src python3 artifacts/wb04-getter-full-check-qneVC9/check.py --replay`。
  权限切换后旧进程句柄丢失，沙箱外 pgrep 确认无进程且无 final.json 后才重启。
  最终进程退出0；报告 `artifacts/wb04-getter-full-check-qneVC9/final.json`，SHA256
  185d284b2a968883918e4eea1ae7db2ebcad0da581f3c62468634a172b047187。
  实现 SHA256 73a79f12481e0fc8017dff771daf792cb9eeee0ba213b0ec2ae5bf8c72cf4aa9
  运行前后一致。显式400万预算下仍 unknown / unsupported_callee_cast：真实调用
  使用 BuiltinFnToFnPtr，不是当前支持的 FunctionToPointerDecay。
- 诊断域 [0,2147483647]、int/unsigned int 32位以及外部叶无写/正常返回均是显式
  诊断前提，未从host launch恢复；没有因此签发适配或源码正确性结论。最终失败
  报告保留effect协议哈希。原始AST/报告/runner本地保留，默认不随Git上传。
- 下一项：先核验 BuiltinFnToFnPtr 支持条件，再将实际 launch 域与 leaf 数值契约连接，单独处理 exact receiver
  的求值义务；不能为本案例赋予未建立的坐标或 body 保持性。
- 提交安排：验收及完整 TU 诊断完成后随本文件一起 commit/push；无 PR。
