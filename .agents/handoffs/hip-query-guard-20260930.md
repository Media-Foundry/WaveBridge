# 交接

- 日期、分支、基线：2026-09-30，wb03-source-ast，9f6dbb4；开始时工作树干净。
- 目标：继续真实源码门控；中文回复、直接 commit、稳定后推送当前分支，无 PR。
- 实现：normal_return_guard.check_call 从同一原始 AST 绑定直接嵌套调用与包装
  参数，fresh 调用原 guard checker。driver 新增 query_result_check；原 wrapper_check
  引用同次子报告。报告增加 selection/policy 哈希。
- 定向验证：真实 Clang 6 项通过；完整 make check 1318 项/99.534 秒，无跳过；
  /tmp/wb-query-guard-check.log；make demo、git diff --check 通过。
- 审阅：GPT-5.6 Sol 只读复核无阻断项。直接内层调用可为任意同型函数，报告
  按精确声明区分，绝不因 query 名称/位置就赋予 API 语义。
- 未执行：GPU、性能、native64 适配和远端实验。
- 条件：调用执行所选包装定义、有效普通 C++ 执行、noreturn 声明被遵守、
  无异步/非局部干扰；只在调用正常返回时约束该次 query 结果的转换后比较。
  API 成功、query 输出写入、输入有效性、调用返回与运行库链接均未验证。
- 下一步：把 query 实参中的精确对象地址/设备 ID 与已有字段快照连接；为
  enum-to-int 转换及 API 成功输出建立冻结外部 ABI/API 协议。不要把枚举常量
  名单或历史设备观察自行升级为运行时完整值域。
- 本地 SDK 头文件注释与哈希见 experiments/hip-query-guard-evidence-20260930.md。
- 重放工件及推送状态以最终验收补记和 Git 为准。
- 实际重放：artifacts/wb-hip-query-guard-20260930-01/report.json，SHA256
  4daf978256ecf72e1a1c329dba9ffb86b501af6c52cb4f4855dad3609cb956f8；
  两个 query_result_check=checked，inputs_unchanged=true，细节见实录。
