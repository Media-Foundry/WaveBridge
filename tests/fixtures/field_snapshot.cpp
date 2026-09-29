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
