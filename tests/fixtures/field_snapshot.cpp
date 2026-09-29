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
