# 源码接入

计划提取源码位置、编译选项、宏/include 依赖、线程索引、intrinsic 和 kernel/launch 关联。必须固定源语义与目标工具链。遇到无法解析的调用不以普通算术代替。

当前实现：无。唯一可用入口是 `src/wavebridge/frontend/fixture.py` 的人工 JSON 模型。
