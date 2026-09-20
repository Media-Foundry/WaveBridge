// Compiler regression, not a benchmark or a GPU semantics implementation.
float transfer(float, int, int);
void synchronize();
unsigned coordinate();
constexpr int width = 32;
constexpr int threads = 256;
float subgroup(float value) {
  for (int route = width / 2; route > 0; route >>= 1)
    value += transfer(value, route, width);
  return value;
}
float aggregate(float value, float *shared) {
  value = subgroup(value);
  const int group = coordinate() / width;
  const int lane = coordinate() % width;
  if (lane == 0)
    shared[group] = value;
  synchronize();
  value = lane < (threads / width) ? shared[lane] : 0.0f;
  return subgroup(value);
}
float unrelated(float value) {
  for (int route = width / 2; route > 0; route >>= 1)
    value += transfer(value, route, width);
  return value;
}
float entry(float value, float *shared) {
  return aggregate(value, shared);
}
