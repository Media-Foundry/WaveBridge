# 原始 HIP TU 的同次原生枚举观测

基线`b52417f`，分支`wb03-source-ast`。没有GPU或编译产物运行。

此前独立host/force-include探针不是原TU。本轮扩展现有native插件，在遍历
原TU时观察完整、非依赖上下文EnumDecl，并与同次JSON AST一起输出。原harness
没有修改、没有强制include探针、没有改写源代码。插件是可信前端，不是独立证明。

新增可选enum_types包含底层类型/Clang存储的提升类型、位宽/符号、fixed/scoped
及枚举常量十进制值和精确声明ID。APSInt直接转十进制字符串，避免负值或超过
INT64的值被宿主整数截断。opaque及未实例化依赖枚举不观测；coverage非穷尽。
Clang可以为scoped enum填写promotion字段，不得据此推断允许隐式转换。

## 构建与采集

SDK Clang23插件使用既有匹配源码/生成头文件，最终库：
`artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so`，
SHA256 `92622342b445dc99e03bb48c11eea8454051acc698de2c0cdfa4d6608a4f6307`。
AOCC Clang17匹配库：
`artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so`，
SHA256 `062e0e529f3fc1f2b997116012432a5780b0cfe7cac70c78e70dc859c28aa608`。
插件源码SHA256：`505b067943318942df3a81e8794b336bafc59fb7055cab1833778482aadb90ac`。
早期Clang23构建因删除的类型访问API失败，build.log/build-02.log保留；最终改用
声明上下文判定依赖性，build-03.log成功。不能交叉加载17/23插件。

```bash
PYTHONPATH=src python -m wavebridge.frontend.native_captures \
  artifacts/wb-softmax-hip-pilot-20260927-10/pytorch-softmax-hip.hip.cpp \
  --compiler artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc \
  --plugin artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
  --compiler-arg=-std=c++17 --compiler-arg=-O2 \
  --compiler-arg=--offload-device-only --compiler-arg=-DWB_COMPILED_COOP_WIDTH=32 \
  --compiler-arg=-I/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-softmax-hip-pilot-20260927-10 \
  --timeout 120 --output artifacts/wb-hip-native-enum-20260930-01/native.json
```

## 实际结果

collected，inputs_stable=true，334个编译后依赖记录。
报告SHA256：`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
源harness前后SHA256仍为
`fcfa6606452f25ce85508267bffff7ba743148ffef0b600e05b9b54f8bac3cc0`。
原TU目标`amdgcn-amd-amdhsa`，int32，共观察206个枚举定义。

在新AST中，包装函数`0x3b52b8d0`的参数`0x3b52b7c0`引用typedef
`0x3a80ae48`；该typedef中的EnumType精确指向`0x3a807358`。同一ID的native
枚举记录：非fixed、非scoped，底层unsigned int32，存储的promotion为signed int32。
hipSuccess枚举声明`0x3a8074a8`值为0，hipErrorTbd声明`0x3a80a5b0`值为1055。
上述关联按新AST精确ID核对；没有把旧AST的ID复制到新报告。

这一步补上原TU同次类型观测，不代表查询成功、输出初始化、运行时域或任意
转换均已证明。现有高层driver仍固定旧工件；尚未让它消费新记录或提升接受状态。

## 验证

Clang23与Clang17各3项真实原生回归通过：同AST ID/常量值、opaque/dependent
边界、signed及大于INT64的常量、underlying/promotion区别、非穷尽/非部署标志。
补充全局唯一性断言后重新执行专项；完整CPU回归在补记记录。Sol只读复核无阻断。

补记：完整1330项CPU回归98.193秒通过、无跳过，日志`/tmp/wb-native-enum-check.log`。
其中enum专项用新SDK23插件，旧native专项用新AOCC17插件，一元builtin用新SDK23
插件；其它工具链保持前轮设置。回归启动后补充的唯一性断言，在23/17上分别
重新跑3项专项通过。make demo和git diff --check通过，没有GPU执行。
