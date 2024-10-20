
#include <stdint.h>

struct subexample_t {
    uint32_t value;
    uint8_t value2;
};

struct example_t {
    struct subexample_t subs[5];
    uint32_t value;
};

struct example_t example1;
struct example_t example2;

int main(int argc, char **argv)
{
    example1.subs[1].value2 = 5;
    example2.subs[3].value = 5;
}