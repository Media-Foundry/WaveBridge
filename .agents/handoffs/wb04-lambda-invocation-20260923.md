# 交接：立即调用 lambda 的接收者绑定

- 日期/分支/基线：2026-09-23，`wb03-source-ast`，
  `a34cc1fdacd9b6509ff759d96519089aae555e14`；开始时工作树干净。
- 用户约定：中文、直接 commit/push 当前分支、不创建 PR。
- 分工：沿用 Sol 子代理实现 `verification/lambda_invocation.py`；主代理核对
  真实路径、补测试/CPU 反例、完整 TU 重放、审阅和文档。无 GPU 作业。

## 本轮解除的局部义务

固定案例的四个捕获闭包原来只有父表达式清单，没有检查它们如何成为实际调用
接收者。新 checker 从完整 AST 关联 LambdaExpr、closure record、物化临时量、
可选 const NoOp 转换、二实参节点的 CXXOperatorCallExpr（callee+receiver）、
精确零参非 static 非模板 operator() 及相同 body。名字只用于 AST 形状约束，
不能代替声明 ID 和所属 record 绑定。

完整索引先拒绝同 ID 的不一致节点，再在跳过 closure record 重复 body 的语义
遍历中要求唯一原始表达式路径。普通/嵌套/mutable/括号/尾置返回类型有真实正例；
具名、返回、传参、generic、显式/默认调用参数、显式成员调用等保持 unknown。
真实 vLLM 的 `auto () const -> void` 不能用简单 `endswith(" const")` 识别；
本轮经真实尾置返回测试修复这一拒绝，不放宽精确 callee 类型匹配。

实现 SHA-256：`db43a4d433710feb2db458be898456ffc5e04ba574cbedee0afb0cdb2b610086`。

## 不能直接组合成历史值保持

新 fixture 中 source 初始化为3，立即 lambda body 将 x 改成99再复制。
真实 native AST 上初始化、捕获身份（带显式测试前提）、调用接收者三个局部检查
均为 checked；真实 CPU 程序复制结果仍为99。另一个调用位于恒假分支，正确
接收者绑定也不证明可达性。测试明确保留这些 not_established 字段。

source 的 typedef 锚点用于满足已有构造身份检查的受限输入子集，不代表已经
支持所有普通 struct 声明；本轮没有扩展该旧检查器。

## 验证命令与工件

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
make demo
PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_lambda_invocation_clang
PYTHONPATH=src python3 artifacts/wb-lambda-invocation-JzwjNu/check.py
```

Clang23 的新增8项中7项通过、native组合项跳过（不可加载Clang17插件）；
AOCC17匹配插件环境中该组合项实际运行。日志保存于
`artifacts/wb-lambda-invocation-JzwjNu/`。
最终619项CPU、152项Clang专项及demo通过；新增8项在AOCC17原生插件下均执行。
最终断言版本的日志为 `check-tests-final.log` 与 `clang-tests-final.log`。

完整 TU 输入为上一轮原生采集的 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json`，
SHA-256 `f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`。
源码、工具链和插件来源见上一轮初始化交接。本轮没有重采集，也没有用源码切片
代替完整 TU；固定 VarDecl `0x373701f0` 的4条捕获记录仅用于选择诊断目标。
每个 worker 从完整 AST 独立扫描/hash 和检查；不复用其他 worker 的成功结果。

四个点均 checked，耗时193.56秒，76个实现文件前后哈希一致；四次独立 root
哈希均为 `ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba`。
最终 `report.json` SHA-256：
`cf03c0a5c8796e7f1b1debf3446e6186a5cfdbbb00fc0efbf829d19f3b146833`。

| LambdaExpr | CXXOperatorCallExpr | operator() 声明 |
| --- | --- | --- |
| `0x373934c0` | `0x37393758` | `0x3737e1a0` |
| `0x373842f0` | `0x37384588` | `0x37382120` |
| `0x37389ed0` | `0x3738a168` | `0x37387e30` |
| `0x3738fab0` | `0x3738fd48` | `0x3738da10` |

## 局限与下一步

结论条件是所选调用被求值；没有证明可达性、调用次数、正常返回、capture init、
body 或外围清理的效果，没有证明闭包 body 不发布所捕获对象地址。
初始化/capture/复制子报告的既有未知项不变，没有解除其外部动态身份前提。
GPU、性能、代码生成和部署均未运行或建立，WB-03/04整体不据此验收完成。

下一项：审计同一源对象所有引用及关联闭包中的读写/发布，结合已检查的构造与
复制规则，建立从初始化至复制点的有限路径保持关系；不能只扫描几个 DeclRef
就忽略别名、其他分支、闭包传出、隐式操作或不透明效果。
