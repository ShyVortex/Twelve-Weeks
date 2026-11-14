// Offline harness for the virtual-region descriptor reader of tools/ext/p1side.h (p1s_read_desc): a synthetic in-memory PE with a ".t2rps" section.
//   gcc -std=gnu2x -O1 -o p1side_desc_harness.exe p1side_desc_harness.c
//   prints "OK <status> <layout> <step> <err hex> <size1> <size2>" for a good descriptor, and "NONE" for a module without the section / a bad magic.
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define P1S_LOG(...) (printf(__VA_ARGS__), printf("\n"))
#include "../ext/p1side.h"

int main(void) {
    static uint8_t img[0x3000];
    memset(img, 0, sizeof img);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)img;
    dos->e_magic = IMAGE_DOS_SIGNATURE;
    dos->e_lfanew = 0x80;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(img + 0x80);
    nt->Signature = IMAGE_NT_SIGNATURE;
    nt->FileHeader.NumberOfSections = 2;
    nt->FileHeader.SizeOfOptionalHeader = sizeof(IMAGE_OPTIONAL_HEADER64);
    IMAGE_SECTION_HEADER *sh = IMAGE_FIRST_SECTION(nt);
    memcpy(sh[0].Name, ".text", 6);
    sh[0].VirtualAddress = 0x1000;
    memcpy(sh[1].Name, ".t2rps", 7);
    sh[1].VirtualAddress = 0x2000;
    p1s_desc d;
    if (p1s_read_desc(img, &d)) { printf("BAD-ACCEPTED-NO-MAGIC\n"); return 1; }          // section present, magic missing
    uint8_t *s = img + 0x2000;
    *(uint32_t *)s = 0x44533150u; *(uint32_t *)(s + 4) = 1;
    *(uint32_t *)(s + 8) = 2; *(uint32_t *)(s + 12) = 1; *(uint32_t *)(s + 16) = 5; *(uint32_t *)(s + 20) = 2;
    *(uint64_t *)(s + 0x18) = 1111; *(uint64_t *)(s + 0x20) = 2222;
    if (!p1s_read_desc(img, &d)) { printf("NONE\n"); return 1; }
    printf("OK %u %u %u %x %llu %llu %s\n", d.status, d.layout, d.step, d.err, (unsigned long long)d.size1, (unsigned long long)d.size2, p1s_status_name(d.status));
    sh[1].Name[1] = 'x';                                                                  // no such section
    if (p1s_read_desc(img, &d)) { printf("BAD-ACCEPTED-NO-SECTION\n"); return 1; }
    dos->e_magic = 0;                                                                     // not a PE
    if (p1s_read_desc(img, &d)) { printf("BAD-ACCEPTED-NO-PE\n"); return 1; }
    if (p1s_read_desc(NULL, &d)) { printf("BAD-ACCEPTED-NULL\n"); return 1; }
    printf("NONE\n");
    return 0;
}
