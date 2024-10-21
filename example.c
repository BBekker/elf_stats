
#include <stdint.h>

typedef struct subexample_t {
    union {
        uint32_t value;
        uint8_t value2;
    };
} subexample_typedef_t;

struct example_t {
    subexample_typedef_t subs[5];
    uint32_t value;
};

struct example_t example1;
volatile struct example_t example2;
const struct example_t example3;

int main(int argc, char **argv)
{
    example1.subs[1].value2 = 5;
    example2.subs[3].value = 5;

    subexample_typedef_t local_variable;
    local_variable.value = 5;
}