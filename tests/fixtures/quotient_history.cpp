void observe_threads(int);
void opaque_threads_call();

void outer_else_quotient_history(int target, const int candidate, bool outer, int* output) {
    if (outer) {
        output[0] = target;
    } else {
        target = candidate < target ? candidate : target;
        const int threads = 128;
        int quotient = threads / target;
        int derived = quotient + 1;
        output[0] = derived;
        observe_threads(quotient);
    }
}

void zero_intervening_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    observe_threads(quotient);
}

void rewrite_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    quotient = 4;
    observe_threads(quotient);
}

void alias_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    using Ref = int&;
    Ref alias = quotient;
    alias = 4;
    observe_threads(quotient);
}

void escape_quotient_in_array_filler(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    int* escaped[2] = {&quotient};
    (void)escaped;
    observe_threads(quotient);
}

void opaque_between_quotient_and_use(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    opaque_threads_call();
    observe_threads(quotient);
}

void nested_target_quotient(int target, const int candidate, bool choose) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    int quotient = threads / target;
    if (choose) {
        observe_threads(quotient);
    }
}

void target_before_quotient(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    observe_threads(target);
    int quotient = threads / target;
    (void)quotient;
}

void static_quotient_history(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    const int threads = 128;
    static int quotient = threads / target;
    observe_threads(quotient);
}
