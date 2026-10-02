#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/prctl.h>
#include <seccomp.h>

int main(int argc, char **argv)
{
	scmp_filter_ctx ctx;

	if (argc < 2) {
		fprintf(stderr, "usage: %s command [args...]\n", argv[0]);
		return 2;
	}

	/* Without this, an unprivileged process cannot load a seccomp filter. */
	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
		perror("prctl(NO_NEW_PRIVS)");
		return 1;
	}

	ctx = seccomp_init(SCMP_ACT_ALLOW);
	if (!ctx) {
		fprintf(stderr, "seccomp_init failed\n");
		return 1;
	}

	/* getppid never fails in normal Unix. Returning EPERM is the proof. */
	if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(getppid), 0) != 0) {
		fprintf(stderr, "seccomp_rule_add failed\n");
		return 1;
	}

	if (seccomp_load(ctx) != 0) {
		perror("seccomp_load");
		return 1;
	}
	seccomp_release(ctx);

	execvp(argv[1], &argv[1]);
	perror("execvp");
	return 127;
}
