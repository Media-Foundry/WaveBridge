# 实验协议

当前只提供协议模板，没有 GPU runner、测量结果或自动解析这些模板的调度器。

`configs/pilot.toml` 定义首轮比较的输入条件；`configs/devices.example.toml` 列出待探测平台。复制到忽略的 `local/` 后再填写真实机器信息。不得把模板中的空值当成探测结果。

每次运行以唯一 ID 创建 `artifacts/<run-id>/`，保存实际配置、源与候选、检查报告、编译/执行日志、原始时间样本和 `result.json`。`result.template.json` 给出结果字段，所有 `null` 表示未测量，禁止用零填充缺失结果。

正式执行前冻结语料拆分、基线配置、正确性协议、调优预算、计时方式、warmup、重复次数和汇总方法。失败和超时保留，重试产生新记录并关联前一次 run ID。

同一目标 GPU 上比较 logical32、候选 logical64 和人工实现；跨设备性能用于评估可移植性，不能直接作波宽因果归因。没有确认真实波宽前，不运行名义上的 wave32/wave64 对照。
