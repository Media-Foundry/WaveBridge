# 交接

- 日期、分支、基线：2026-09-30，wb03-source-ast，e511771，开始时工作树干净。
- 目标：持续推进源码门控；中文、直接commit、稳定后push当前分支，无PR。
- 发现：原native命令为hipcc device-only，旧独立host ABI探针不能直接复用。
- 实现：hip_api_abi_probe.py增加hip_context_source，显式pilot flags加force-include
  原harness；前后hash与同次唯一dependency匹配。未从工件执行命令。
- 实际02报告：artifacts/wb-hip-api-device-context-20260930-02/report.json，SHA256
  9631a36b59af3ef3edf0b078d679c72f4850d9faf6832d6f1da6ea06a1d328c4。
- 新trace amdgcn-amd-amdhsa/gfx1100；旧334个依赖全部同hash，仅新增probe文件。
  八项观测与host相同，但不证明TU上下文/运行时语义相同。
- 保证边界：forceinclude改变includelevel/basefile，旧native插件未使用，
  original_kernel_TU_ABI_binding仍false。无GPU、程序、性能运行，不修改checker接受能力。
- 验证：6项fixture、demo/diff通过；Sol复核无阻断，完整全测见最终补记。
- 下一步：为原TU同次采集增补原生类型/转换观测，再绑定API输出协议；勿跨TU复用ID。
- 命令与证据说明见experiments/hip-api-device-context-evidence-20260930.md。
- 全测补记：1327项/98.606秒，无跳过，/tmp/wb-api-device-context-check.log。
