// chat.h slur filter: gcc -I tools/ext tools/ext/tests/chat_test.c -o chat_test && ./chat_test
#include <stdio.h>
#include "chat.h"

static int fails;
static void t(const char *in, const char *want) {
    char b[CH_BUF];
    snprintf(b, sizeof b, "%s", in);
    ch_censor(b);
    int ok = !strcmp(b, want);
    printf("%s '%s' -> '%s'%s%s\n", ok ? "ok  " : "FAIL", in, b, ok ? "" : "  want ", ok ? "" : want);
    fails += !ok;
}
int main(void) {
    t("gg wp", "gg wp");
    t("you nigger", "you ******");
    t("NIGGAS lol", "****** lol");
    t("n1gg4 pls", "***** pls");
    t("niiigaaa", "********");
    t("stop being a faggot.", "stop being a ******.");
    t("fag", "***");
    t("f@ggot", "******");
    t("retarded team", "******** team");
    t("dykes", "*****");
    t("trannies", "********");
    t("chinks", "******");
    t("kike!", "****!");
    t("spic spice", "**** spice");
    t("czarnuchy", "*********");
    t("coon raccoon", "**** raccoon");
    t("snigger", "snigger");                          // a real word
    t("Niger Nigeria", "Niger Nigeria");
    t("pakistan", "pakistan");
    t("they have a bow, careful", "they have a bow, careful");
    t("DRUŻYNA ciota", "DRUŻYNA *****");
    t("", "");
    printf(fails ? "FAILED: %d\n" : "all ok\n", fails);
    return fails != 0;
}
