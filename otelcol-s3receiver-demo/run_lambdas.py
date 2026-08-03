#!/usr/bin/env python3
"""Invoke the two 'lambda' handlers K times each, fanning delta samples into S3.

Inputs are chosen so the merged (cumulative) result is independently checkable:

  counter   invocation k -> delta = k          -> cumulative sum  = 1+2+...+K
  histogram invocation k -> [k, k+1, k+2, k+3] -> merged buckets  = sum over k

For the default K=5:
  cumulative counter = 15
  merged histogram   = bucketCounts=[15, 20, 25, 30], count=90

Usage: run_lambdas.py [K]
"""
import sys

from lambdas import counter_lambda, histogram_lambda

K = int(sys.argv[1]) if len(sys.argv) > 1 else 5
BOUNDS = [1.0, 5.0, 10.0]  # -> 4 buckets: (-inf,1] (1,5] (5,10] (10,+inf)


def expected(k):
    exp_sum = sum(range(1, k + 1))
    exp_buckets = [sum(j + i for j in range(1, k + 1)) for i in range(4)]
    exp_count = sum(exp_buckets)
    return exp_sum, exp_buckets, exp_count


def main():
    for k in range(1, K + 1):
        r1 = counter_lambda.handler({"invocation": k, "delta": k})
        counts = [k, k + 1, k + 2, k + 3]
        r2 = histogram_lambda.handler(
            {"invocation": k, "bucketCounts": counts, "bounds": BOUNDS}
        )
        print(
            f"invocation {k}: counter += {k}  hist {counts}"
            f"  -> {r1['key']}, {r2['key']}",
            flush=True,
        )

    exp_sum, exp_buckets, exp_count = expected(K)
    print(f"\nEXPECTED cumulative counter = {exp_sum}", flush=True)
    print(
        f"EXPECTED merged histogram   = bucketCounts={exp_buckets} count={exp_count}",
        flush=True,
    )


if __name__ == "__main__":
    main()
