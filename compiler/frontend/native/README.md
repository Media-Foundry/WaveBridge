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

The envelope also contains optional `expression_cleanups` observations from
`VisitExprWithCleanups`: `expression_id`, `subexpression_id`, `num_objects`, and
`cleanups_have_side_effects`. These IDs resolve in the same embedded AST and
are deduplicated by native expression pointer. `cleanup_coverage` is explicitly
`visited_expressions_not_exhaustive`; absence of an observation is not evidence
that a program has no cleanup. Older v1 envelopes do not contain this extension.

`num_objects` reflects Clang's auxiliary cleanup-object array (block declarations
and block-scoped compound literals), **not C++ temporary destructor events**.
The native cleanup fixture demonstrates a destructor writing a global counter
even though `num_objects` is zero. C++ temporary binding is represented elsewhere
in the AST, including `CXXBindTemporaryExpr`. The native boolean is an observed
compiler flag, not an independent proof of effects, lifetime, or deployment.
Adding these observations does not upgrade existing checker results or historical
AST artifacts. A future consumer must bind a specific observation to the exact
full-expression and explicitly state its trusted-frontend assumptions.

The optional `local_record_objects` extension records visited local variables
whose declared type is a complete C++ record (not references, pointers, arrays,
or dependent types). Each item binds `variable_declaration_id`,
`record_declaration_id`, and the available `destructor_declaration_id` in the
same AST. A null destructor ID does not establish trivial destruction. Native
`has_nontrivial_destructor` records the record's type property, not its effects.

`declaring_compound_statement_id` is populated only for a variable declared in
a `DeclStmt` directly belonging to that `CompoundStmt`. For/if initializers are
not assigned the nearest enclosing compound as their declaration scope. Such
entries, and non-automatic storage durations including static/thread-local,
remain explicitly `unsupported`; `has_automatic_storage_duration` is obtained
from Clang's storage-duration classification rather than spelling heuristics.

Coverage is `visited_local_complete_record_variables_not_exhaustive`, with
semantics `lexical_declarations_not_runtime_destructor_events`. In particular,
this is not a CFG cleanup schedule, an exhaustive local-object inventory, an
effects proof, or evidence that a constructor/destructor executes. Constructor
failure, exceptions, jumps, dynamic lifetime, attributes, arrays and other
unvisited declaration forms require separate obligations. Consumers must bind
declarations and scopes and distinguish already-ended scopes from enclosing
scopes; absent metadata in older artifacts cannot mean no local destruction.
The independent object-use structure checker consumes this extension only to
classify observed declaration scopes relative to copy syntax. Its dedicated
child report does not discharge preservation, completeness or cleanup effects.

The optional `builtin_calls` extension uses `CallExpr::getDirectCallee()` and
`FunctionDecl::getBuiltinID()` (nonzero), not a name-prefix heuristic. Each entry
records `call_expression_id`, `callee_declaration_id`, `builtin_id`,
`builtin_name` from the compiler builtin table, and ordered
`argument_expression_ids`. All pointer IDs belong to the embedded ASTContext;
numeric builtin IDs are compiler-version-specific, not portable semantic tags.
Only visited direct calls are observed and deduplicated by expression pointer.
`builtin_call_coverage` is `visited_direct_builtin_calls_not_exhaustive`;
absence, including in old v1 envelopes, cannot prove a call is not builtin.

This is compiler identity evidence, not a whitelist: builtin functions can write
memory, synchronize, fail to return, or evaluate arguments with effects. The
plugin neither evaluates returned values nor grants purity. It does not enable
calls in the column-loop checker. Consumers must bind the exact same-context
call, declaration, argument AST and compiler evidence before applying any
separate explicit semantics protocol. Indirect calls and unresolved/dependent
calls are not covered; syntactic visitation is not runtime reachability.

The observer now explicitly visits template instantiations, recorded by
`visits_template_instantiations=true`. Earlier artifacts may contain instantiated
JSON AST bodies without the corresponding native observations. They are not
retrospectively complete. Coverage labels remain non-exhaustive; visiting an
instantiation does not prove it is dynamically reachable.

The optional `constructor_calls` extension binds each visited `CXXConstructExpr`
to `expression_id`, the exact `constructor_declaration_id` selected by Clang,
its `record_declaration_id`, and ordered `argument_expression_ids`. Native
`is_trivial` and `is_default_constructor` flags describe the selected declaration,
not the whole initialization expression or its argument effects. Entries are
deduplicated by expression pointer. Coverage is
`visited_construct_expressions_not_exhaustive`, with semantics
`compiler_identity_not_effect_or_lifetime_proof`. Missing observations, a null
destructor ID, or a trivial constructor flag alone cannot authorize preservation
or deployment. All IDs must be rebound within the new capture; never join them
to IDs from an older compiler invocation.
