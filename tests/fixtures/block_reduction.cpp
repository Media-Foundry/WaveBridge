// Structural regression only; all external semantics remain assumptions.
float reduce_group(float value);
void rendezvous();
int coordinate();
unsigned unsigned_coordinate();
constexpr int group_width = 32;
constexpr int threads = 256;
float block_sum(float value, float *shared) {
  value = reduce_group(value);
  const int group = coordinate() / group_width;
  const int lane = coordinate() % group_width;
  if (lane == 0)
    shared[group] = value;
  rendezvous();
  value = lane < (threads / group_width) ? shared[lane] : 0.0f;
  return reduce_group(value);
}
float missing_barrier(float value, float *shared) {
  value = reduce_group(value);
  const int group = coordinate() / group_width;
  const int lane = coordinate() % group_width;
  if (lane == 0)
    shared[group] = value;
  value = lane < (threads / group_width) ? shared[lane] : 0.0f;
  return reduce_group(value);
}
float unsigned_block_sum(float value, float *shared) {
  value = reduce_group(value);
  const int group = unsigned_coordinate() / group_width;
  const int lane = unsigned_coordinate() % group_width;
  if (lane == 0)
    shared[group] = value;
  rendezvous();
  value = lane < (threads / group_width) ? shared[lane] : 0.0f;
  return reduce_group(value);
}
