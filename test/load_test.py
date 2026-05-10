#!/usr/bin/env python3
"""
Load test script for the Goat Yard Archive backend.

Usage:
    uv run python test/load_test.py --url http://localhost:8000 --requests 20 --concurrency 5
    uv run python test/load_test.py --url http://localhost:8000 --requests 50 --concurrency 10 --token <clerk_jwt>
"""

import argparse
import asyncio
import time
import sys
from dataclasses import dataclass, field
from typing import List

import httpx


@dataclass
class Result:
    status: int
    duration: float
    error: str = ""
    trace_id: str = ""


@dataclass
class Summary:
    total: int
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    rate_limited: int = 0
    durations: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def avg_duration(self) -> float:
        return sum(self.durations) / len(self.durations) if self.durations else 0

    @property
    def min_duration(self) -> float:
        return min(self.durations) if self.durations else 0

    @property
    def max_duration(self) -> float:
        return max(self.durations) if self.durations else 0

    def print_report(self):
        print("\n" + "=" * 60)
        print(" LOAD TEST REPORT ")
        print("=" * 60)
        print(f"  Total requests:      {self.total}")
        print(f"  Successful (2xx):    {self.successes}")
        print(f"  Failed (4xx/5xx):    {self.failures}")
        print(f"  Timeouts:            {self.timeouts}")
        print(f"  Rate limited (429):  {self.rate_limited}")
        print(f"  Avg duration:        {self.avg_duration:.2f}s")
        print(f"  Min duration:        {self.min_duration:.2f}s")
        print(f"  Max duration:        {self.max_duration:.2f}s")
        if self.errors:
            print(f"\n  Sample errors:")
            for err in self.errors[:5]:
                print(f"    - {err}")
        print("=" * 60)


async def fire_request(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    token: str | None,
    semaphore: asyncio.Semaphore,
) -> Result:
    async with semaphore:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {"query": query}
        start = time.perf_counter()

        try:
            response = await client.post(
                f"{url}/api/search",
                json=payload,
                headers=headers,
                timeout=70.0,
            )
            duration = time.perf_counter() - start
            trace_id = response.json().get("trace_id", "") if response.status_code == 200 else ""
            return Result(
                status=response.status_code,
                duration=duration,
                trace_id=trace_id,
            )
        except httpx.TimeoutException:
            duration = time.perf_counter() - start
            return Result(status=0, duration=duration, error="Request timed out")
        except Exception as e:
            duration = time.perf_counter() - start
            return Result(status=0, duration=duration, error=str(e))


async def run_load_test(url: str, total_requests: int, concurrency: int, token: str | None):
    queries = [
        "What does Gill say about baptism?",
        "What is the covenant of grace?",
        "Explain predestination according to Gill",
        "What does the commentary say about Matthew 5?",
        "Tell me about the deity of Christ",
        "What is Gill's view on the atonement?",
        "Explain justification by faith",
        "What does Gill say about the Trinity?",
        "What is the nature of the church?",
        "Explain Gill's view on election",
    ]

    semaphore = asyncio.Semaphore(concurrency)
    summary = Summary(total=total_requests)

    async with httpx.AsyncClient(http2=True) as client:
        # Quick health check first
        try:
            health = await client.get(f"{url}/health", timeout=5.0)
            print(f"Health check: {health.status_code} {health.json()}")
        except Exception as e:
            print(f"Health check failed: {e}")
            sys.exit(1)

        print(f"\nFiring {total_requests} requests with concurrency={concurrency}...")
        start_time = time.perf_counter()

        tasks = [
            fire_request(
                client,
                url,
                queries[i % len(queries)],
                token,
                semaphore,
            )
            for i in range(total_requests)
        ]

        results = await asyncio.gather(*tasks)
        total_duration = time.perf_counter() - start_time

        for r in results:
            summary.durations.append(r.duration)
            if r.status == 200:
                summary.successes += 1
            elif r.status == 429:
                summary.rate_limited += 1
                summary.failures += 1
            elif r.status == 0 and "timed out" in r.error.lower():
                summary.timeouts += 1
                summary.failures += 1
            else:
                summary.failures += 1
                if r.error:
                    summary.errors.append(f"{r.status}: {r.error}")

        print(f"Total wall-clock time: {total_duration:.2f}s")
        print(f"Throughput: {total_requests / total_duration:.2f} req/s")
        summary.print_report()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test the Goat Yard Archive API")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("--requests", type=int, default=20, help="Total number of requests to fire")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests")
    parser.add_argument("--token", default=None, help="Clerk JWT token for authenticated requests")

    args = parser.parse_args()
    asyncio.run(run_load_test(args.url, args.requests, args.concurrency, args.token))
