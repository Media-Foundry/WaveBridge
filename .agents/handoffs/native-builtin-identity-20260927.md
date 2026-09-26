# 原生 builtin 身份交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，37c812b。
- 用户约定：中文；验收后直接 commit/push 当前分支，不创建 PR。
- 完成：现有 native 插件 builtin_calls 可选扩展、采集器局限说明、真实 Clang
  同次身份和参数测试；GPT-5.6 Sol 实现测试并在新构建插件上运行通过。
- 实际采集：AOCC Clang17 同配置 CUDA 合成探针 collected；全部命令、哈希、
  首次构建未完成导致的 input_unreadable 均保留，见
  experiments/native-builtin-evidence-20260927.md。
- 未执行：GPU、原生产 softmax 重采、远端 CI；未改变核心语义门控。
- 验收：新构建插件下 make check 978 项、66.472 秒、无跳过；最终 3 项
  定向测试再次通过；make demo/diff 通过。日志在 artifacts/wb-native-builtins-JR99CL/。
- 局限：非穷尽静态访问，compiler builtin 身份不等于纯度/返回值语义；数字
  ID 不跨版本复用，指针 ID 不跨 ASTContext 连接。
- 下一步：同次 AST 的 builtin 身份消费者与受限实参结构检查，明确外部语义
  协议后再接效果检查；不能用 builtin 名称或 metadata 存在直接接受循环。
- 提交/推送：随本轮验收后完成，无须 PR。
