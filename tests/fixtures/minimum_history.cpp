void observe(int);
void opaque_call();

void nested_else_history(int target, const int candidate, bool choose, int* output) {
    target = candidate < target ? candidate : target;
    if (choose) {
        output[0] = target;
    } else {
        output[0] = target + 1;
    }
    observe(target);
}

void no_intervening_statement(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    observe(target);
}

void endpoints_inside_outer_else(int target, const int candidate, bool outer,
                                 bool inner, int* output) {
    if (outer) {
        output[0] = target;
    } else {
        target = candidate < target ? candidate : target;
        if (inner) {
            output[0] = target;
        } else {
            output[0] = target + 1;
        }
        observe(target);
    }
}

void direct_rewrite(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    target = 9;
    observe(target);
}

void reference_alias(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    using Ref = int&;
    Ref alias = target;
    alias = 9;
    observe(target);
}

void array_filler_escape(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    int* escaped[2] = {&target};
    (void)escaped;
    observe(target);
}

void opaque_intermediate_call(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    opaque_call();
    observe(target);
}

void goto_control(int target, const int candidate, bool choose) {
    target = candidate < target ? candidate : target;
    if (choose) {
        goto selected;
    }
selected:
    observe(target);
}

void target_in_nested_compound(int target, const int candidate, bool choose) {
    target = candidate < target ? candidate : target;
    if (choose) {
        observe(target);
    }
}

void target_before_update(int target, const int candidate) {
    observe(target);
    target = candidate < target ? candidate : target;
}

void alias_before_update(int target, const int candidate) {
    using Ref = int&;
    Ref alias = target;
    target = candidate < target ? candidate : target;
    observe(target);
    (void)alias;
}

void write_after_target(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    observe(target);
    target = 9;
}

void writing_target_statement(int target, const int candidate) {
    target = candidate < target ? candidate : target;
    target = 9;
}
