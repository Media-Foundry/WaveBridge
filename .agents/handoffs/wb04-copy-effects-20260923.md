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

没有新GPU执行、完整vLLM TU效果重放或源到目标适配闭环。下一步应把局部
访问分类与整函数引用闭合、源对象初始化连接成有明确前提的有限历史保持；
不允许把上述三个独立checked简单当作该结论。
