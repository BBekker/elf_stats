#include <stdint.h>

struct otherstruct_t {
    int a;
    int b[10];
};

struct otherstruct_t others[10];

static void changeOthers() {
    others[0].a = 10;
}