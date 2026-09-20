// Compiler regression only; the external function has no assumed GPU semantics.
float exchange(float value, int offset, int width);
constexpr int group_size = 32;
float original(float acc) {
  for (int mask = group_size / 2; mask > 0; mask >>= 1)
    acc += exchange(acc, mask, group_size);
  return acc;
}
constexpr int other_group = 64;
float renamed(float sum) {
  for (int route = other_group / 2; route > 0; route >>= 1)
    sum += exchange(sum, route, other_group);
  return sum;
}
float changed_condition(float acc) {
  for (int mask = group_size / 2; mask > 1; mask >>= 1)
    acc += exchange(acc, mask, group_size);
  return acc;
}
