# 交接：整函数显式源对象引用闭合

- 日期/分支/基线：2026-09-23，`wb03-source-ast`，
  `e0e73a7d14aa18583e5b0854e1b5d50b60553037`；开始时工作树干净。
- 用户约定：始终中文；验收后直接commit/push当前分支，不创建PR或合并master。
- 分工：Sol实现新checker；主代理编写真实fixture/回归、审阅、位置元数据窄修复、
  本地验收、完整TU runner及文档。本轮无GPU。

## 实现

`verification/object_use_closure.py` 从同一完整 native envelope fresh 检查初始化，
再要求所属普通函数内所有显式源 DeclRef 完整归类为受支持引用捕获或直接复制。
对普通copy fresh `record_copy_check`；lambda内copy fresh `capture_source_check`，
外部协议键集合必须精确覆盖所有分支。所有native源捕获必须被完整copy chains
覆盖；相关lambda fresh `lambda_invocation`。任何额外源写入、地址/引用转出、
按值/init-capture、具名/传出closure、未覆盖分支、元数据冲突或内联汇编不能通过。
失败仍保留已经运行的子checker报告。

源码SHA-256：`278294d6cc56f4d3e8b0bbd9bb7a1ccc2ba97a49ba1ed08a047fde704d0acbfe`。

闭合不是一般no-escape或值保持：先前alias、未跟踪memory effects、opaque calls、
历史执行顺序和launch均未建立；子协议中的lifetime/activation等仍是显式外部假设。
不含显式源引用的不透明普通调用有正例，报告仍明确effect/history未知。

## 真实回归与修复

- `tests/fixtures/object_uses.cpp` 和 `tests/test_object_use_closure_clang.py`：
  普通copy与三分支正例；后者准确得到7refs/4captures/3copies/4lambdas。
  负例包括另一个分支的写入、using隐藏引用、cast、取址、按值/initcapture、
  具名/传出closure、static/TLS、assembly和缺失/多余/错绑定协议。
- 真实AOCC17三分支AST使旧lambda checker误拒绝。精确diff显示，同ID outer
  CompoundStmt仅在一份`range.begin`中有`line:12`，另一份省略；不是body内容不同。
  新`lambda_invocation._same_ast`只忽略loc/range里的line显示字段，保留offset、
  file、col、token、ID与所有语义结构比较。完整root哈希仍绑定原始line。
  新测试区分line省略、offset冲突与非location的同名字段，后两项不能通过。
  不通过跳过嵌套closure或任意删除range来规避冲突。
- 修改后的lambda checker SHA-256：
  `8b1e88d6653a6b109143d62757c86cd3dd4a8b74835b4cb51ba3f2e9fda1608c`。

## 本地验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
make demo
```

628项CPU、161项Clang专项与demo通过；日志位于
`artifacts/wb-object-use-closure-N4Xis6/{check-tests,clang-tests,demo}.log`。
插件与AOCC Clang17匹配，新增native测试实际运行，不把未加载插件的skip记为通过。

## 完整 TU 后台任务：已收取终态

原任务正常退出0，结果为条件 `checked`；耗时1445.242809秒，77个Python实现
文件前后哈希一致。计数为7个显式源引用、4次捕获、0次普通复制、3次捕获复制、
4个lambda。`source_program_checked=false`、`deployable=false`，未运行GPU。
报告 `artifacts/wb-object-use-closure-N4Xis6/report.json` SHA-256：
`d1bf2f0d86b4c90d02c7e782775e7fce588ec630fb4fbb4b25e40d596403a084`。
以下启动记录保留供追溯；原进程已结束，不应再重启该输出目录的脚本。

```bash
PYTHONPATH=src python3 artifacts/wb-object-use-closure-N4Xis6/check.py \
  > artifacts/wb-object-use-closure-N4Xis6/run.log 2>&1
```

实际启动的exec session为`40778`；Python PID `426259`，父shell PID `426256`。
运行期间先检查这些句柄/进程和日志，未因观察超时重启。测试/文档和commit不会
改变冻结的`src/wavebridge`实现；运行前后会核对全部Python实现哈希。

输入为固定完整 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json`，SHA-256
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`；root hash
`ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba`。
固定source VarDecl为`0x373701f0`。caller自动选择该source的3个原始copy表达式，
提供显式外部hidden_size∈[1,4096]、整数ABI及capture lifetime/activation假设；
不提供任何预先成功的子报告。checker内部独立恢复集合并重新运行全部子检查。

完整重放包含多次完整AST hash/scan；终态结果已保存为同目录
`report.json`。没有结果文件或只有进程运行不代表checked。没有重采集、GPU、
性能或整核证明。实际终态与范围见本节开头，下一步推进初始化至复制
之间的有限路径保持；当前显式集合闭合本身不能替代那项保证。

## 等待期间的独立成本诊断（不修改正式运行）

命令：`PYTHONPATH=src python3 artifacts/wb-hash-cost-X3no77/check.py`。
输入仍是上述固定完整native AST；新进程只读输入，没有重启PID426259，也没有
修改任何`src/wavebridge`文件。使用与现有hash一致的sort_keys、紧凑separators、
allow_nan=False参数，改用一次性`json.dumps`生成字符串再UTF-8编码并SHA-256。

实际加载24.90秒，序列化14.84秒，UTF-8与哈希2.01秒；结果精确等于已记录的
`ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba`。
canonical字符串为1,849,557,363字符。Linux进程ru_maxrss在加载后/一次性哈希后
均为12,735,492 KiB：这是累计高水位，不证明序列化没有额外分配；该路径明确创建
完整字符串和完整字节缓冲区。未在本次重跑流式基准，不能报告受控加速比。

报告 `artifacts/wb-hash-cost-X3no77/report.json` SHA-256：
`f6bffd115b72b607b12bab4cb1175fde20084ab5b43d4b42428268d87fe26d68`。
它是下一轮可选加速路径的工程依据，不改变保证范围。未来若实现，应保留内存
受限的流式默认路径，并验证两种模式的canonical摘要和失败行为一致；正在运行
任务必须先收取终态，不能为了加速丢弃或暗中重启。

## 复制效果只读审阅与排除的候选反例

现有copy核心shape只读取const Record&的直接整数字段、逐字段初始化目标且body
为空，适合追加局部source写入/地址发布检查。但现有报告没有该效果保证；任意
constructor/field `*Attr`以及ParmVarDecl的未门控children仍需明确支持边界。
不应把现有逐字段值关系直接重命名为无副作用，也不能从中消除capture协议的
alive/closure来源/same activation等外部前提。

Sol在`artifacts/wb-copy-attr-d3SUgE`测试参数和字段上的cleanup属性；AOCC17均
发出“only applies to local variables”的ignored-attributes警告，AST不含该属性。
主代理另实际编译、链接并执行param.cpp和field.cpp：两者成功构建，程序均按
源码`return x`返回退出码3；cleanup函数仅声明而无定义，未产生运行时调用。
因此这不是已证实漏洞，不列入负例发现或修复成果。下一效果门控应基于确切
支持子集，而不是把这个被编译器忽略的语法当成实际攻击。
