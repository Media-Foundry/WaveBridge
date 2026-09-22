# 交接：同 ASTContext 的原生捕获证据

- 日期/分支/基线：2026-09-22，`wb03-source-ast`，`6f76787`。
- 用户目标：继续真实源码关系链；中文回复，直接 commit/push，无 PR。
- 已完成：原生 Clang 插件、Python 可选采集入口、fixture/真实集成测试、
  Clang 18 专项 CI 构建、前端文档与 ADR 0002。Sol 实现插件，主代理负责
  采集编排、交叉检查、测试、CI 与证据边界。
- 实际构建：AOCC `/opt/AMD/aocc-compiler-5.1.0/bin/clang++`，
  `-std=c++17 -fPIC -fno-rtti -shared compiler/frontend/native/capture_plugin.cpp`
  `-I/opt/AMD/aocc-compiler-5.1.0/include -o <new-directory>/libwavebridge_capture_plugin.so`。
  最终插件 `artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so`，SHA256
  `d777ff4bb1ae3baa822c9c48e5fa9d885c91602580942ce993db9e4cdf3675db`；
  C++ 源码 SHA256 `92b2c99f863921f57ca0a1a6ae259ba83445937d7fb80742e2d095c1450dde3e`。
- 实际验收：设 `WB_NATIVE_CAPTURE_PLUGIN` 为上述插件绝对路径、
  `WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++`：
  `make check` 574 项无跳过、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 107 项通过。
  原生新增 11 项通过；未拿 Clang 17 插件加载到 Clang 23。
- 采集命令：`PYTHONPATH=src python3 -m wavebridge.frontend.native_captures`
  `tests/fixtures/native_captures.cpp --compiler /opt/AMD/aocc-compiler-5.1.0/bin/clang++`
  `--plugin artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so`
  `--compiler-arg=-std=c++17 --output artifacts/wb-native-capture-6gG4DG/final-report.json`。
  collected，输入前后哈希一致，依赖 observed，版本 17.0.6，target x86_64。
  10 项捕获记录（3 项 unsupported）；报告 SHA256
  `95584c48ab96fb208f1bf0104229edd694a4723c97bfc6df938e07a3f85b30a9`。
- 工程失败保留：初始 RTTI/整体 libclang-cpp 链接不兼容 AOCC；无显式链接并
  禁用 RTTI 后成功。初版 pointer format 固定补零/大写，与 JSON ID 不同，被
  同 AST 解引用回归拦截；最终统一小写无补零。不覆盖旧产物。
- 范围：插件是可信前端观察器，不是 checker。完整 TU 但 capture 观察不完备；
  不证明 runtime source identity、对象历史、输入快照、launch、GPU 等价或新颖性。
  初始化式的 lambda 在外部环境遍历；嵌套 body 路径与执行次数严格分开。
- 未执行：新的生产 TU 采集、GPU、native64、性能或新 holdout 验收。
- 下一项：用匹配工具链对固定 vLLM 编译输入重新采集同次 AST/捕获证据，
  不与旧 TU 裸 ID 混用；随后检查精确 enclosing capture 路径，再组合对象无写历史。
- 提交/远端：随本轮验收提交推送当前分支；CI 状态按实际提交工作流核对。
