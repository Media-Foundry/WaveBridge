# 交接：vLLM 同次原生捕获与完整 AST

- 时间：2026-09-22 采集，09-23 整理；分支 `wb03-source-ast`，基线 `b67e511`。
- 用户目标：继续真实源码关系链，中文回复；验收后直接提交推送，不创建 PR。
- 本轮完成：不改分析实现，用原生插件重采集固定完整 vLLM TU，并在新 AST
  上重新定位 float RMSNorm launch、检查 block 复制与提取相关捕获候选。
- 来源：vLLM `f49777ba62b4926d0f8c100ab06edb03c5c10098` 的
  `csrc/layernorm_kernels.cu`，源码 SHA256
  `57d5d4e2912e0661d57a0eab4a837ea7a8cab794b7e4cf10b7d5f42dd31ef2d8`。
  冻结既有 `artifacts/wb03-vllm-holdout-GqLQJo/attempt-06.json` 的源码及编译参数，
  该报告 SHA256 `f75e566c7443bd4ab69acd5a3e7c5c89af80d75c30f3892d779dfaf81f2a38f7`。
  它是既有开发输入与编译视图，不是新 holdout、无修改通用工具链支持或原生适配成功。
- 命令：`PYTHONPATH=src python3 artifacts/wb-vllm-native-Rw42Hh/run.py`。
  runner SHA256 `642697bc2bcb7e8e4c8506309d7922b1063eb6cefa13e9944c68a4d060a293f8`。
  其调用 `native_captures.collect`，复用冻结 command 的原始编译参数，替换原
  AST dump/filter action；timeout=240 秒，复制检查 max_ast_nodes=4,000,000。
  插件为上一轮 `artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so`，
  SHA256 `d777ff4bb1ae3baa822c9c48e5fa9d885c91602580942ce993db9e4cdf3675db`。
- 实际结果：collected；目标 `nvptx64-nvidia-cuda`，依赖 5,456 个文件，捕获
  296 项；capture coverage 明确非穷尽。总耗时 339.41 秒，11 个实现文件
  前后哈希一致。AST/采集报告 `artifacts/wb-vllm-native-Rw42Hh/ast.json`（约 5.3 GiB），
  SHA256 `c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`；
  诊断 `report.json` SHA256
  `8d2e99f9a7f935f017c8c1de18cc46057d8f01dd190d5367eee7f337e9974e77`。
  大型本地工件不入 Git；编译器命令、诊断、输入哈希和依赖原文保存在 ast.json。
- 新树中的定位：kernel `0x38e575a8`，launch `0x38e57818`（4 个完全一致 AST
  出现归一，不是执行次数），block 复制 `0x38e56348`，词法源 `0x38e43f10`。
  复制检查 checked，字段 `0x22738908/0x22738970/0x227389d8` 分别同字段保值。
- 原生捕获候选：该源共有 4 条，包含目标 launch 的两个 lambda 为：
  - 外层 `0x38e671e0`、closure `0x38e51d80`、field `0x38e66d58`、
    initializer `0x38e66d18`，by_reference，enclosing=[]。
  - 内层 `0x38e58010`、closure `0x38e55d00`、field `0x38e57ae0`、
    initializer `0x38e57aa0`，by_reference，enclosing=[外层 lambda]。
  两条都是普通隐式捕获；ID 仅用于此同次采集，不能拼接到旧 AST。
- 已执行回归：启用上述插件和 AOCC Clang 17 的 `make check` 574 项无跳过；
  `make demo` 通过。默认不启用插件时同命令为 574 项、跳过 8 项，未将跳过算通过。
- 未执行：GPU、性能、候选生成、数值域从初始化转移到 launch、运行时对象身份证明。
- 保证范围：诊断通过完整 lambda 子树包含 launch 来筛候选，尚非 fresh body-path
  checker；不能以此断言捕获链完备。源有效性、动态 activation、closure 实例来源、
  生命周期与无写历史均未建立；`runtime_source_identity`/`launch_semantics`
  保持 not_established，deployable=false。
- 下一项：从复制表达式重新恢复 lambda body 路径，排除初始化式和 closure
  声明副本的错误路径；逐层匹配原生捕获边，缺失/重复/歧义 unknown。全引用链
  仍需外部精确生命周期/closure 来源协议，任意按值层不得升级为原始对象身份。
  这一步与对象值未变分开，不把捕获检查替代无写分析。
- 提交/推送：本轮仅更新证据记录与状态，按用户授权推送当前工作分支。
