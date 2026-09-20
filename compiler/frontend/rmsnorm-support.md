# WB-03 首例源码接入边界

对象是 WB-02 的真实来源手工 standalone，不是自动提取的上游模板实例。
此阶段先取得真实 Clang AST；尚不签发关系检查或可部署候选。

## 编译视图

本机已安装 HIP 工具链可用 `-fsyntax-only -Xclang -ast-dump=json`
解析该文件。HIP 默认同时编译 host/device，可能输出多个相邻 JSON 根。
设备分析必须显式指定 `--cuda-device-only` 并保存完整参数；不能把两个视图的
同名声明拼成一个执行模型。host launch 的提取需要独立 host 视图。

`-ast-dump-filter` 是过滤入口，不是分析算法。筛出同名函数不代表已取得
完整调用闭包、所有全局常量定义或 include 依赖；宏的 spelling/expansion
位置也不能混淆。AST 工件绑定源码与编译器，但仅这些哈希尚不足以构成
可缓存的完整 SourceBundle。

## 关系恢复必须实际解决的义务

| 源码结构 | 需要恢复的关系 | 当前不能直接假定的前提 |
| --- | --- | --- |
| `col = tid; col < ncols; col += kBlockSize` | 输入列覆盖、每线程局部平方和 | 常量定义及 launch block 与步长一致 |
| XOR shuffle 循环 | 每阶段从哪个 lane 取哪个值，重复贡献数 | intrinsic 的 width、物理能力与参与收敛 |
| `shared_values[logical_group] = value` | 每逻辑组的 partial 与 writer | 无冲突、共享数组容量足够 |
| barrier 后按 lane 读取 partial | 共享存储阶段、归约与广播对象 | 所有相关线程到达 barrier，读取前已写入 |
| `dst[col] = scale * x[col]` | 输出行列归属与 scale 的数据依赖 | 指针范围、别名与外部合法输入域 |
| host launch | block/grid/shared bytes 与 kernel 的对应 | 不依赖人工 oracle 补填源码事实 |

以上是人工列出的分析验收义务，不是工具自动恢复结果。后续必须由 AST
声明引用、表达式和控制流推导，并保留源码来源；遇到不支持的控制流、别名
或调用应返回未知，而不是使用函数名或预设 RMSNorm 关系补全。

## 下一次验收

先在现有 standalone 上获得 kernel 与两个 helper 的设备 AST，再建立
常量/调用闭包和运算依赖。需要同时加入改名、改变 shuffle 路由、改变
列步长和不支持调用的源码测试。获得 AST 不代表这些测试已满足；跨谱系
恢复、目标源码重提取和 Polygeist/CKTI 共同案例比较均仍未完成。
