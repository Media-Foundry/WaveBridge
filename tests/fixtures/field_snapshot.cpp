struct Properties { int width; volatile int volatile_width; };
int observed = 0, calls = 0, other = 0;
extern void query(Properties*);
extern void opaque();
int good() {
    Properties p{};
    query(&p);
    observed = p.width;
    ++calls;
    return observed;
}
int wrong_counter() {
    Properties p{};
    observed = p.width;
    ++observed;
    return observed;
}
int wrong_return() {
    Properties p{};
    observed = p.width;
    ++calls;
    return other;
}
int intervening_call() {
    Properties p{};
    observed = p.width;
    opaque();
    ++calls;
    return observed;
}
int volatile_field() {
    Properties p{};
    observed = p.volatile_width;
    ++calls;
    return observed;
}
int changed_value() {
    Properties p{};
    observed = p.width + 1;
    ++calls;
    return observed;
}

typedef enum Status { success, failure } Status;
void fatal(int) __attribute__((noreturn));
void guard(Status code) { if (code != success) { fatal(2); } }
Status property_query(Properties*, int);
Status reordered_query(int, Properties*);
Status duplicate_query(Properties*, Properties*);
int guarded_snapshot() {
    Properties p{};
    guard(property_query(&p, 0));
    observed = p.width; ++calls; return observed;
}
int reordered_snapshot() {
    Properties p{};
    guard(reordered_query(0, &p));
    observed = p.width; ++calls; return observed;
}
int wrong_query_object() {
    Properties p{}, q{};
    guard(property_query(&q, 0));
    observed = p.width; ++calls; return observed;
}
int query_not_adjacent() {
    Properties p{};
    guard(property_query(&p, 0));
    opaque();
    observed = p.width; ++calls; return observed;
}
int query_pointer_alias() {
    Properties p{};
    Properties* alias = &p;
    guard(property_query(alias, 0));
    observed = p.width; ++calls; return observed;
}
int ambiguous_query_role() {
    Properties p{};
    guard(duplicate_query(&p, &p));
    observed = p.width; ++calls; return observed;
}
int result_discarded() {
    Properties p{};
    guard((property_query(&p, 0), success));
    observed = p.width; ++calls; return observed;
}

void initializer_cases() {
    int local_good = guarded_snapshot();
    local_good = 7; // This checker must not claim preservation to later uses.
    int local_other = reordered_snapshot();
    static int local_static = guarded_snapshot();
    thread_local int local_tls = guarded_snapshot();
    const int local_const = guarded_snapshot();
    long local_long = guarded_snapshot();
    int local_comma = (guarded_snapshot(), 0);
    int (*fp)() = guarded_snapshot;
    int local_indirect = fp();
    int local_multi = guarded_snapshot(), second = 0;
    { int local_nested = guarded_snapshot(); }
    if (observed) { int local_branch = guarded_snapshot(); }
    try { int local_try = guarded_snapshot(); } catch (...) {}
}
template<class T> int template_initializer() {
    int local_template = guarded_snapshot();
    return local_template;
}
template int template_initializer<int>();

void history_good() {
    int history_value = guarded_snapshot();
    int unrelated = 1;
    history_value = history_value < 32 ? history_value : 32;
    history_value = 7;
    int* later_alias = &history_value;
}
void history_write() {
    int history_written = guarded_snapshot();
    ++history_written;
    history_written = history_written < 32 ? history_written : 32;
}
void history_escape() {
    int history_escaped = guarded_snapshot();
    int* aliases[] = {&history_escaped};
    history_escaped = history_escaped < 32 ? history_escaped : 32;
}
void history_jump() {
restart: ;
    int history_jumped = guarded_snapshot();
    history_jumped = history_jumped < 32 ? history_jumped : 32;
    goto restart;
}
void history_lambda() {
    int history_captured = guarded_snapshot();
    history_captured = history_captured < 32 ? history_captured : 32;
    auto capture = [&history_captured] { ++history_captured; };
}

int composed_exponent(int input) {
    int exponent = 0;
    while ((1 << exponent) < input) ++exponent;
    return exponent;
}
int composed_dispatch(int input) {
    int composed_log = composed_exponent(input);
    const int composed_power = 1 << composed_log;
    int composed_width = guarded_snapshot();
    composed_width = composed_power < composed_width ? composed_power : composed_width;
    const int composed_threads = 128;
    int composed_quotient = composed_threads / composed_width;
    return composed_quotient;
}
int composed_caller(int input) {
    const int composed_input = input;
    if (composed_input != 65 && composed_input != 128) return 3;
    composed_dispatch(composed_input);
    return 0;
}

// Each variant is compiled into a real AST; the checker does not read these names.
#define COMPOSED_VARIANT(NAME, BEFORE, EXPR) \
int NAME(int input) { \
    int composed_log = composed_exponent(input); \
    const int composed_power = 1 << composed_log; \
    int composed_width = guarded_snapshot(); \
    BEFORE; \
    composed_width = EXPR; \
    return composed_width; \
} \
int NAME##_caller(int input) { \
    const int composed_input = input; \
    if (composed_input != 65 && composed_input != 128) return 3; \
    NAME(composed_input); \
    return 0; \
}
COMPOSED_VARIANT(composed_write, ++composed_width,
    composed_power < composed_width ? composed_power : composed_width)
COMPOSED_VARIANT(composed_max, (void)0,
    composed_power < composed_width ? composed_width : composed_power)
COMPOSED_VARIANT(composed_escape, int* aliases[] = {&composed_width},
    composed_power < composed_width ? composed_power : composed_width)

#define QUOTIENT_VARIANT(NAME, BETWEEN, DENOMINATOR) \
int NAME(int input) { \
    int composed_log = composed_exponent(input); \
    const int composed_power = 1 << composed_log; \
    int composed_width = guarded_snapshot(); \
    composed_width = composed_power < composed_width ? composed_power : composed_width; \
    BETWEEN; \
    const int composed_threads = 128; \
    int composed_quotient = composed_threads / DENOMINATOR; \
    return composed_quotient; \
} \
int NAME##_caller(int input) { \
    const int composed_input = input; \
    if (composed_input != 65 && composed_input != 128) return 3; \
    NAME(composed_input); \
    return 0; \
}
QUOTIENT_VARIANT(quotient_changed, ++composed_width, composed_width)
QUOTIENT_VARIANT(quotient_wrong, (void)0, input)
QUOTIENT_VARIANT(quotient_escaped, int* aliases[] = {&composed_width}, composed_width)

void stop_now() __attribute__((noreturn));
void can_return();
#define SOURCE_GUARD(NAME, CONDITION, FAILURE, BETWEEN) \
int NAME(int input) { \
    int composed_log = composed_exponent(input); \
    const int composed_power = 1 << composed_log; \
    int composed_width = guarded_snapshot(); \
    if (CONDITION) FAILURE; \
    BETWEEN \
    composed_width = composed_power < composed_width ? composed_power : composed_width; \
    const int composed_threads = 128; \
    int composed_quotient = composed_threads / composed_width; \
    return composed_quotient; \
} \
int NAME##_caller(int input) { \
    const int composed_input = input; \
    if (composed_input != 65 && composed_input != 128) return 3; \
    NAME(composed_input); \
    return 0; \
}
SOURCE_GUARD(source_gate, composed_width != 32, stop_now(), )
SOURCE_GUARD(source_gate_zero, composed_width != 0, stop_now(), )
SOURCE_GUARD(source_gate_wrong, input != 32, stop_now(), )
SOURCE_GUARD(source_gate_returns, composed_width != 32, can_return(), )
SOURCE_GUARD(source_gate_write, composed_width != 32, stop_now(), ++composed_width;)
SOURCE_GUARD(source_gate_changed_condition, ++composed_width != 32, stop_now(), )

template<class T> void shared_literal_guard(int input) {
    int shared_guard_local = input;
    if (shared_guard_local != 32) stop_now();
    shared_guard_local = 1;
}
template void shared_literal_guard<int>(int);

typedef struct GuardDims {
    unsigned x, y, z;
    GuardDims(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) {}
} GuardDimsAlias;
typedef struct GuardSwapped {
    unsigned x, y, z;
    GuardSwapped(unsigned a, unsigned b, unsigned c) : x(b), y(a), z(c) {}
} GuardSwappedAlias;
typedef struct GuardOverwritten {
    unsigned x, y, z;
    GuardOverwritten(unsigned a, unsigned b, unsigned c) : x(a), y(b), z(c) { x = 0; }
} GuardOverwrittenAlias;
#define GUARDED_CONSTRUCT(NAME, RECORD, BETWEEN, FIRST) \
int NAME(int input) { \
    int composed_log = composed_exponent(input); \
    const int composed_power = 1 << composed_log; \
    int composed_width = guarded_snapshot(); \
    if (composed_width != 32) stop_now(); \
    composed_width = composed_power < composed_width ? composed_power : composed_width; \
    const int composed_threads = 128; \
    int composed_quotient = composed_threads / composed_width; \
    BETWEEN \
    RECORD composed_dims(FIRST, composed_quotient, 1); \
    return 0; \
} \
int NAME##_caller(int input) { \
    const int composed_input = input; \
    if (composed_input != 65 && composed_input != 128) return 3; \
    NAME(composed_input); \
    return 0; \
}
GUARDED_CONSTRUCT(constructed_guard, GuardDimsAlias, , composed_width)
GUARDED_CONSTRUCT(constructed_swap, GuardSwappedAlias, , composed_width)
GUARDED_CONSTRUCT(constructed_write, GuardDimsAlias, ++composed_quotient;, composed_width)
GUARDED_CONSTRUCT(constructed_alias, GuardDimsAlias, int* aliases[] = {&composed_quotient};, composed_width)
GUARDED_CONSTRUCT(constructed_wrong, GuardDimsAlias, , input)
GUARDED_CONSTRUCT(constructed_body, GuardOverwrittenAlias, , composed_width)
