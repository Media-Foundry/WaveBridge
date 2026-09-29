typedef enum Code { success, failure } Code;
void stop(int) __attribute__((noreturn));
void ordinary(int);
void log_status(Code);
void good(Code status) { if (status != success) { log_status(status); stop(2); } }
void returns(Code status) { if (status != success) { ordinary(2); } }
void early_return(Code status) { if (status != success) { return; stop(2); } }
void wrong_test(Code status) { if (status == success) { stop(2); } }
void changed_status(Code status) { status = success; if (status != success) { stop(2); } }
void has_else(Code status) { if (status != success) { stop(2); } else { ordinary(2); } }
void hidden_return(Code status) { if (status != success) { ordinary(({ return; 2; })); stop(2); } }
void indirect(Code status) { void (*fp)(int) = stop; if (status != success) { fp(2); } }
void after_terminal(Code status) { if (status != success) { stop(2); ordinary(2); } }
Code query(int* output);
Code other_query(int* output);
void call_good(int* output) { good(query(output)); }
void call_other(int* output) { good(other_query(output)); }
void call_constant(int* output) { good(success); }
void call_discarded(int* output) { good((query(output), success)); }
void call_converted(int* output) { good(static_cast<Code>(static_cast<int>(query(output)) + 1)); }
void call_conditional(int* output, bool select) { good(select ? query(output) : success); }
void call_indirect(int* output, Code (*fp)(int*)) { good(fp(output)); }
void call_unguarded(int* output) { returns(query(output)); }
