// Source-analysis regression, not a production kernel or relation oracle.
constexpr int tile = 256;
constexpr int alternate_tile = 128;
void columns(float *input, float *output, int tid, int count) {
  for (int column = tid; column < count; column += tile)
    output[column] = input[column];
}
void renamed(float *a, float *b, int first, int limit) {
  for (int position = first; position < limit; position += alternate_tile)
    b[position] = a[position];
}
void hidden_increment(float *a, float *b, int first, int limit) {
  for (int position = first; position < limit; position += tile) {
    b[position] = a[position];
    ++position;
  }
}
void changing_bound(float *a, float *b, int first, int limit) {
  for (int position = first; position < limit; position += tile) {
    b[position] = a[position];
    --limit;
  }
}
