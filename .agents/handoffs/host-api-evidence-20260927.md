# 交接

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`4b6e2ab`。
- 约定：中文；直接commit/push当前分支，不开PR或合并master。
- 完成：固定上游CUDAContext.cpp与许可证取证脚本；同一native精确API
  call/声明/局部初始化观察；5项真实Clang回归；来源边界与下一门槛记录。
- 实际结果：完整1197项通过（92.465秒，native启用、无跳过），demo/diff通过。
  GPT-5.6 Sol贡献回归、只读复核及历史W7900/softmax证据链分离检查。
- 工件：`artifacts/wb-softmax-host-api-KFKsOQ/report.json`，SHA256
  `601630306abaa91236b85411e21326178b73d0a095c86f6a5a443dfa0ecd6fdc`。
  取证57466、全量测试96635均正常结束，输入/driver哈希一致。
- 新证据：固定实现从当前设备属性读warpSize，路径含call_once与设备属性
  缓存初始化；不是常量32实现，也不能假定无写。现有TU同符号定义列表为空。
- 未建立：runtime链接、同一设备/进程API值、数值域、启动保证。未运行GPU。
- 提交状态：此文件随本轮验收变更提交；远端状态以git push终端结果为准。
- 下一项：明确实际执行视图并建立同一host/kernel/API链接工件。若采用
  本机W7900，需单独带来源和补丁的HIP输入，不能复用CUDA sm80的ID/哈希
  或把历史HIP探针32作为当前API返回域。详见本轮实录“下一门槛”。
