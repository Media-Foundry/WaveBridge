# 复制构造局部效果

- 日期：2026-09-23，分支 `wb03-source-ast`，基线 `716dd9d`。
- 中文回复、直接commit/push，不创建PR、不合并master。
- 上轮为实际进展：完整TU终态、实现和测试已提交；本轮先核验远端
  CI `35767829492` 为success。

## 实现与边界

`record_copy_check.py` 在独立完成原字段值关系检查后，追加局部效果分类。
不改变原schema/v1主status语义；未支持属性仅使效果unknown。
精确构造/初始化/源参数读取的旧检查仍必需，新门控限制constructor属性、
record直接属性、field/parameter children、参数默认标志及deleted/invalid标志。
只接纳childless CUDAHostAttr/CUDADeviceAttr，不以名称后缀放行任意属性。

Sol只读审阅指出不能混淆AST角色与动态存储：目标和源的nonoverlap未建立，
因此只记录源参数角色读取、目标角色初始化、绑定之外未观测到地址发布。
先前别名/并发、目标分配与lifetime、外围清理/析构、源历史保持仍未知。
没有新加“源存储只读”保证；消费者没有自动解除历史义务。

## 验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
make demo
PYTHONPATH=src python3 -m unittest tests.test_record_copy_clang
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
```

完整644项CPU与demo退出0，定向16项通过。日志保存于
`artifacts/wb-copy-effects-42cMpV/`。
Clang专项168项通过。Sol复查后还补了子报告自身的源码/部署false与有效源码、
字段可读、正常返回前提，以及参数pack/invalid、constructor variadic与字段
invalid标志门控；最终全套重跑记录为 `final-check.log`、`final-demo.log`。
真实Clang源例覆盖普通/隐式/参数/捕获复制、历史已被修改仍只建立局部效果、
CUDA host/device属性正例及参数unused属性效果unknown。
未知属性/隐藏子节点/default/deleted标志测试是合成元数据变体，不是编译运行
成功的攻击程序，也不宣称unused属性有运行时副作用。

## 未完成

没有新GPU执行或源到目标适配闭环。完整TU后续重放见下节。下一步应把局部
访问分类与整函数引用闭合、源对象初始化连接成有明确前提的有限历史保持；
不允许把上述三个独立checked简单当作该结论。

## 固定完整 TU 后续验收

基线 `307bd44`，远端CI `35768426610` 已success。实际命令：

```bash
WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src \
  python3 artifacts/wb-copy-effect-native-gqbATs/check.py
```

独立exec session35192正常退出0；耗时120.7019655秒，77个实现文件前后哈希一致。
输入仍为 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json`，SHA-256：
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`。
同一vLLM固定来源和nvptx device-only编译视图，未重采集或引入新代码谱系。
全部三个copy ID `0x37382628`、`0x37388288`、`0x3738de68` 的字段关系及
`local_copy_effects` 均checked；完整root摘要全部为
`ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba`。
字段ID为 `0x20c736b8`、`0x20c73720`、`0x20c73788`。

输出 `artifacts/wb-copy-effect-native-gqbATs/report.json` SHA-256：
`928b5088be50385eb2902c0d65206e86b31b6c9aa6fa5a1fb5752e1957bb133c`。
记录one-shot模式；未对相同完整检查任务做流式对照，因此不报告加速比。
此前1445秒任务为不同的全组合检查，不能相除制造收益。

外围语法观察确认：全部copy直接位于配置CallExpr，外层为CUDAKernelCallExpr。
每个ID因lambda重复body有4份相同语法出现，不是4个运行事件。先前提出的
“仅绑定普通自动target VarDecl”不足以覆盖这些真实临时配置实参，不应将其
当成此案例的下一阶段验收。所需的是精确实参位置、callee声明及by-value形参
绑定；仍不能仅凭名字或当前局部报告宣布source/target非重叠。

Sol未发现满足现有全部前提且不依赖UB/伪造AST/实现特有裸内存访问的修改
反例，但这不是完整证明。未来non-escape论证应区分源码可检查义务与外部
same-activation/alive、无未跟踪alias/栈扫描/并发修改前提，不必把Torch调用
全部假设成纯函数。当前history、storage nonoverlap、整核和部署均未建立。

### 配置目标的精确语法观察

独立命令 `PYTHONPATH=src python3 artifacts/wb-copy-effect-native-gqbATs/inspect_targets.py`
正常退出0，完整输入文件哈希已核对。三个配置CallExpr为
`0x37382568`、`0x373881c8`、`0x3738dda8`；上述copy都处于从0开始的实参位置1。
均为 `constructionKind=complete`、`valueCategory=prvalue`，record alias ID
`0x20c74bc0`。callee精确关联唯一FunctionDecl `0x2135cd60`，位置1对应
ParmVarDecl `0x2135ca90`，类型与copy相同、为按值 `dim3`，非引用。
callee的名字是 `__cudaPushCallConfiguration`，但没有按名字签发任何语义保证。

原始观察报告 `target-observations.json` SHA-256：
`b65ff7f6a6c9bfd1a36714e885fffaddd75eb84c62a7638395231e4e4fa48b9f`。
这只是来自当前AST的语法记录，尚不是独立检查器的target绑定结论，尤其
callee没有body，ABI实现/实际launch行为不能从声明推出。
下一个实现应从完整AST重新关联copy→唯一语义CallExpr→实参位置→精确callee
与by-value形参；覆盖引用形参、间接调用、错误位置、重复冲突及placement
等拒绝/未知边界。需先建立该真实路径，而非仅自动VarDecl目标的较易子集。
