#include <stdint.h>

struct otherstruct_t {
    int a;
    int b[10];
};

struct otherstruct_t others[5];

char* string = "Hello World";

typedef enum {
    A, B, C
} myenum_t;

typedef struct {
    char* some_string;
    struct otherstruct_t other[C];
    uint64_t some_number;
} evenMore_t;

evenMore_t more;

static void changeOthers() {
    others[0].a = 10;
}