int side_effect();

void lvalue_minimum(int target, const int candidate) {
    target = candidate < target ? candidate : target;
}

void prvalue_minimum(int target, const int candidate) {
    target = candidate < target ? +candidate : +target;
}

void local_minimum(int input) {
    int target = input;
    const int candidate = 7;
    target = candidate < target ? candidate : target;
}

void maximum_instead(int target, const int candidate) {
    target = candidate > target ? candidate : target;
}

void swapped_branches(int target, const int candidate) {
    target = candidate < target ? target : candidate;
}

void reference_target(int value, const int candidate) {
    using Ref = int&;
    Ref target = value;
    target = candidate < target ? candidate : target;
}

void volatile_target(volatile int target, const int candidate) {
    target = candidate < target ? candidate : target;
}

void call_in_condition(int target, const int candidate) {
    target = side_effect() < target ? candidate : target;
}

void call_in_branch(int target, const int candidate) {
    target = candidate < target ? side_effect() : target;
}

void indirect_target(int target, const int candidate, int* pointer) {
    *pointer = candidate < target ? candidate : target;
}

void converted_operand(int target, const short candidate) {
    target = candidate < target ? candidate : target;
}

void target_not_an_operand(int target, const int left, const int right) {
    target = left < right ? left : right;
}

void hidden_write_in_branch(int target, const int candidate) {
    target = candidate < target ? (target += 1) : target;
}

void nested_assignment_expression(int target, const int candidate) {
    int observed = (target = candidate < target ? candidate : target);
    (void)observed;
}

void lambda_owned_assignment(int target, const int candidate) {
    [&]() { target = candidate < target ? candidate : target; }();
}
