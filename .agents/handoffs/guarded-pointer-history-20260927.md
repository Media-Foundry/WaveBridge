# 交接

- 日期/分支/基线：2026-09-27，`wb03-source-ast`，`f19281c`；中文回复，直接 commit/push。
- 已完成真实证据：上一项相对 store 重放 checked，两个互斥静态 store，每
  work 路径计数 `[1]`；报告 `artifacts/wb-softmax-store-cast-wsoFEy/replay.json`，
  SHA256 `54f69184c333675a3e45abd693df8f9b70e57ea18ebefa7301a27f566a9307eb`。
  inputs_unchanged=true，移入新代码前核对旧实现逐文件哈希一致。
- 新实现：`guarded_stores.check_entry_pointer`，完整 fresh store 链后绑定
  offset 自动声明、typed row*stride+source、唯一指针更新、直接语句顺序，
  并审计全部 dst/offset 引用（包含 array_filler）。引用/地址逃逸与未知控制拒绝。
- 开发过程：隔离树 `/tmp/wb-pointer-dev-rhMgXx` 保持主重放输入不变；旧重放
  结束后通过 apply_patch 移入主树，核心和测试 cmp 一致。隔离树仍保留，
  其中只有本轮已移入的代码/测试，不是新的待合并用户修改。
- 验证：GPT-5.6 Sol 独立测试/复核；隔离树 1148 项通过、92.048 秒；
  主树同样 1148 项通过、91.888 秒，native 启用、无跳过，demo/diff 通过。
  日志 `artifacts/wb-pointer-history-check-q532dC/`。旧提交 f19281c 的远端
  CI 36279805954 completed/success；不是新提交远端 CI 证据。
- 正在运行：新 pointer-history 真实重放 exec session **67233**，日志/报告
  `artifacts/wb-softmax-pointer-history-0KgDSq/{run.log,replay.json}`。已进入
  protocols_bound，尚无终态。源码与 driver 冻结，勿改动或重启；用原 session 轮询。
- 新外部前提：pointer-domain 协议 row `[0,4095]`、stride `[0,128]` 表示
  offset initializer 时的开发分析窗口，非恢复的 launch 或实际 GPU 范围。
  stride 与 count 不合并，同一数组有效性、无非局部控制等仍条件性。
- 未建立：真实新 pointer 层终态、完整 lane/覆盖、动态分配/别名、FP、整核与部署。
  本轮没有 GPU。下一步取得重放终态/哈希，再依据真实拒绝或通过决定连接
  row/lane/launch；不能仅凭指针变量历史 checked 宣布完整输出覆盖。
- 提交状态：验收后当前代码/协议/文档一起提交推送，以 git 终态为准。
