# Polygeist host adapter 与实际 IR

- 日期：2026-09-20；分支 `wb03-source-ast`，基线 `1b61980`。
- Sol 实施案例 adapter、来源清单/补丁和五项回归；主代理扩展执行记录器，
  运行四次真实 cgeist 并检查 IR。中文回复、直接 commit，不创建 PR、不推送。
- 源码 `benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32_polygeist_adapter.cu`
  SHA-256 `9bd5e5d8bc9eb175b9b05f200a3db9840da013991d7f0e772197c6e765ece7bf`。
  三计算函数保持原样；人工移出host管理，并非自动转换或新谱系。

## 实际执行

均使用前轮 CUDA11.8/GCC11 头路径、同一 cgeist 和 resource-dir；完整命令与
stderr 在每个报告的 execution 中。默认和新增 `--cuda-lower` 分开记录。
以下目录前缀为 `artifacts/polygeist-frontend-`，文件均为 report.json：

| 后缀 | 选择及路径 | 报告 SHA-256 |
| --- | --- | --- |
| `zfwqd1_y` | host入口，默认O0 | `29e2043108f33e939c875441c8fbae980eb5c9720db41684e35e8d2f894144f0` |
| `aowronvz` | host入口，cuda-lower | `85e181b0f2c40ebd7ea0b826260eea2c8db34de446058f68d1af6c6081c4c399` |
| `01247e7_` | 全函数，默认O0 | `5f746b2d07812dd88b63fe4580bdd5d8195dc3763bbffbbf5106baa5c9944e41` |
| `x3hip7fu` | 全函数，cuda-lower | `3e8eeb3e7a742bd34900a5a0d2cd09488ee4cdaa80f8e24798e24b0f3a7717af` |

四次退出0，只记 emitted_unverified_ir。前两次kernel仅剩声明，不能计为
完整计算转换。后两次 output.mlir 分别171行/125行，其 SHA-256 为：

- 默认：`7a4bf9955897efc44f4111a77f2121d3e86ba5b05004d9369743a8d0b6555196`
- lowering：`8eb94f2244affdc63911ddf6e38051297bd1112c9a5bd06fbaa8f2a48fb2f306`

## 观察与检查义务

默认IR有kernel计算体、gpu.launch、block/thread索引、两层归约、barrier、
shuffle helper。lowering将launch转为按行/256线程的嵌套parallel，仍保留
两个shuffle循环；外部 `__nvvm_shfl_sync_bfly_f32` 和 `__nv_rsqrtf` 没有定义。
stderr明确警告无法发射shuffle builtin，不能把保留函数名当作支持其语义。

lowering IR第52行为 `memref.alloca() : memref<1xf32>`，线程循环57行范围
0～255；82行按thread/32写，90行按thread%32且小于8读。具体thread32会
满足writer条件并写索引1，thread1会读索引1，均超出该显式容量。
这是当前产物的容量/访问矛盾，不是最终机器码实验；源launch仍请求128字节
动态shared。后续需隔离动态shared lowering与shuffle处理，记录任何手工修改，
不能覆盖此失败产物或将其泛化成整个方法不支持。

## 验收及限制

主代理 `make check`：280项通过。新增runner两项mock只验证选项和状态隔离，
案例五项检查父源/补丁/协议/计算体与launch对应；不是语义等价证明。
核对源码与报告哈希、IR内容及 `git diff --check`。未单独运行CUDA syntax
检查、GPU数值、coarsening、后端、性能；头闭包哈希仍未建立。
没有完整原standalone支持、正确GPU重定向或创新性结论。G1仍未通过。
