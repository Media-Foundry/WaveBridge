# softmax 启动对象的具体模板实例绑定

2026-09-27，基线 `e225c10`。本次仅解除受限具体函数实例的作用域门槛，
不是建立启动维度。默认非模板接口不变，不删除其他 checker 的保守检查。

## 实现与回归

三个 fresh 层通过 opt-in `instantiated_function_id` 精确绑定同一 FunctionDecl、
唯一函数体、mangled identity 和具体 scalar/integral 模板实参；输入摘要绑定 ID。
声明与构造式的全 TU 唯一性要求保留，不能借此接受歧义共享节点或未支持的
替换表达式。默认路径、旧条件对象接口不扩展。

GPT-5.6 Sol 编写 6 项真实 native Clang 测试并只读复核；覆盖字面量/minimum
三层组合、默认拒绝、错实例、模板本体、依赖/重复/缺失实体、错误模板类型、
缺失 mangled identity、共享 constructor ID，以及动态直接参数仍 unknown。
主代理复跑这 6 项通过（0.287 秒）。完整验收与 demo 日志位于
`artifacts/wb-object-template-check-Xt4l2i/`。
全量执行时测试发现已冻结为 1153 项，92.558 秒通过，native 启用、无跳过；
此后新增的共享 ID 方法包含在最终 6 项专项复跑中。不是声称已全量重跑
最终 1154 项。`make demo` 和 `git diff --check` 通过。

## 真实输入重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-object-template-check-Xt4l2i/replay.json --threads-object
```

报告 SHA256：`12c97b3e46973677127a6a8db278a788b8a84553d10e9533c01aead013d03911`。
`inputs_unchanged=true`，结束后逐文件核对实现和 driver 依赖哈希一致。
launch 绑定仍 checked；**threads_object_check 为 unknown**，不可只看顶层
launch 状态而宣布对象检查通过。

实际实例 `0x30a41828`、body `0x30d7b9b0` 已绑定；其模板实参为
float/float/float/0/0，函数摘要
`9e7e96f7da53810603ae2524d18038eb057c4eda5f7be804d814a0bc4823268e`。
初始化越过原先的 ordinary-nontemplate 限制，停在
`fresh_constructor_value_or_effect_chain_not_checked`；构造来源子报告原因是
`selection_domain_missing`。实际首个读取是 warp_size 声明 `0x30d691d8`，
不把其初始化或函数名当成构造时已知值。

下一步需连接真实 host API、warp_size 更新以及 warps_per_block 的求值历史；
不得添加手填成功字段域绕过这一义务。复制前值保持、可达性、完整 lane 家族、
store 参与、完整覆盖和设备执行均未建立。本次没有 GPU 或浮点保证升级。
