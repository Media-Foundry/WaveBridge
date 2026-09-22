# Native lambda-capture observation plugin

This optional Clang frontend plugin emits the full JSON AST and native
`CXXRecordDecl::getCaptureFields` relations from the same `ASTContext`.  It is
an observation mechanism only: it does not establish runtime source-object
identity, source validity, or deployment correctness.

Example build with the locally installed AOCC Clang 17:

```sh
AOCC=/opt/AMD/aocc-compiler-5.1.0
"$AOCC/bin/clang++" -std=c++17 -fPIC -fno-rtti -shared \
  compiler/frontend/native/capture_plugin.cpp \
  -I"$AOCC/include" \
  -o /tmp/libwavebridge_capture_plugin.so
```

Run it as a replacement frontend action:

```sh
"$AOCC/bin/clang++" -std=c++17 -fsyntax-only \
  -Xclang -load -Xclang /tmp/libwavebridge_capture_plugin.so \
  -Xclang -plugin -Xclang wavebridge-native-captures \
  input.cpp > capture-envelope.json
```

The output schema is `clang-native-captures/v1`. Pointer IDs start from
`llvm::formatv("{0:p}", pointer)` and normalize its fixed-width rendering to
the unpadded, lower-case representation used by Clang's JSON AST dumper.
Init-captures, `this` captures, and VLA-type captures are retained as explicit
`unsupported` entries rather than omitted. `enclosing_lambda_ids` records
syntactic nesting only and must not be interpreted as runtime object identity.
The observer covers LambdaExpr nodes reached through capture initializers and
lambda bodies. It does not claim complete capture coverage for every possible
template instantiation, merged declaration, or default-argument traversal.
