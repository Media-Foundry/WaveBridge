# 候选生成与变换

负责 `compiler/transforms/`、`src/wavebridge/transforms/`。

输入是可追踪的关系模型和目标约束，输出是绑定的 kernel/launch 候选。协作宽度、步长、路由、临时存储、writer 和 launch 必须联动检查；量化数据格式等算法语义保持原协议。

候选生成允许失败，不得改动 checker 规则以放行自身结果。规则、搜索、人工候选或未来 agent 共用相同检查接口。性能选择必须发生在正确性门槛之后；fallback 要有同目标、同输入域的依据。
