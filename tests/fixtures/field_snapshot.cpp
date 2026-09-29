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
