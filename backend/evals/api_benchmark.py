"""HTTP API 性能基准：ASGI 直连 + 内存 SQLite（不依赖 MySQL / 网络）。

测的是应用层开销（路由、鉴权、序列化、仓库查询），不包含网络与 MySQL。
用于回答两个问题：

1. 常用读接口的 P50/P95 是多少（是否有明显慢查询）；
2. 并发请求下错误率与吞吐如何（连接池/会话是否正确复用）。

运行（backend/ 目录）::

    conda activate langGraph
    python -m evals.api_benchmark
    python -m evals.api_benchmark --iterations 200 --json evals/reports/api.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from evals.instrument import latency_summary
from homemind.models.family import Family
from homemind.models.user import User
from homemind.repositories import unit_of_work
from homemind.services.password_service import hash_password
from tests.db import memory_database

ENDPOINTS = (
    ("health", "GET", "/", False),
    ("current_user", "GET", "/api/auth/me", True),
    ("rooms", "GET", "/api/rooms", True),
    ("devices", "GET", "/api/devices", True),
    ("scenes", "GET", "/api/scenes", True),
    ("environment", "GET", "/api/agent/environment", True),
    ("history", "GET", "/api/agent/history?session_id=bench", True),
)


async def _seed() -> dict[str, str]:
    username = f"bench_{uuid.uuid4().hex[:8]}"
    password = "bench-pass-123"
    async with unit_of_work() as uow:
        family = await uow.families.add(Family(name="性能评测家庭", owner_user_id=0))
        owner = await uow.users.add(
            User(
                username=username,
                password=hash_password(password),
                nickname="压测用户",
                role="owner",
                family_id=family.id,
            )
        )
        family.owner_user_id = owner.id
        await uow.commit()
    return {"username": username, "password": password}


async def _request(client: httpx.AsyncClient, method: str, path: str, headers: dict):
    if method == "GET":
        return await client.get(path, headers=headers)
    return await client.request(method, path, headers=headers)


async def _bench(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    headers: dict[str, str],
    iterations: int,
) -> dict[str, Any]:
    # 预热：排除首次导入、连接初始化的噪声
    for _ in range(5):
        await _request(client, method, path, headers)

    latencies: list[float] = []
    errors = 0
    for _ in range(iterations):
        started = time.perf_counter()
        response = await _request(client, method, path, headers)
        latencies.append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            errors += 1
    return {
        "iterations": iterations,
        "errors": errors,
        "error_rate": round(errors / iterations, 4) if iterations else 0.0,
        **latency_summary(latencies),
    }


async def _bench_concurrent(
    client: httpx.AsyncClient,
    path: str,
    headers: dict[str, str],
    requests_count: int,
    concurrency: int,
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    statuses: list[int] = []
    latencies: list[float] = []

    async def one():
        async with semaphore:
            started = time.perf_counter()
            response = await client.get(path, headers=headers)
            latencies.append((time.perf_counter() - started) * 1000)
            statuses.append(response.status_code)

    for _ in range(5):
        await client.get(path, headers=headers)

    started = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(requests_count)))
    elapsed = time.perf_counter() - started
    errors = sum(1 for status in statuses if status >= 400)
    return {
        "requests": requests_count,
        "concurrency": concurrency,
        "elapsed_s": round(elapsed, 3),
        "rps": round(requests_count / elapsed, 1) if elapsed else 0.0,
        "errors": errors,
        "error_rate": round(errors / requests_count, 4) if requests_count else 0.0,
        **latency_summary(latencies),
    }


async def run(iterations: int, concurrency: int, concurrent_requests: int) -> dict[str, Any]:
    from homemind.api import deps
    from homemind.main import app

    # 评测进程内可能复用 user_id=1，清掉鉴权身份缓存避免读到上一次评测的库
    deps._identity_cache.clear()

    async with memory_database():
        credentials = await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
            login = await client.post("/api/auth/login", json=credentials)
            if login.status_code != 200:
                raise RuntimeError(f"登录失败: {login.status_code} {login.text}")
            token = login.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            endpoints = {}
            for name, method, path, auth in ENDPOINTS:
                endpoints[name] = {
                    "method": method,
                    "path": path,
                    **await _bench(
                        client,
                        method,
                        path,
                        headers if auth else {},
                        iterations,
                    ),
                }

            concurrent = await _bench_concurrent(
                client,
                "/api/devices",
                headers,
                requests_count=concurrent_requests,
                concurrency=concurrency,
            )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": "ASGI in-process + SQLite in-memory (single connection)",
        "iterations": iterations,
        "endpoints": endpoints,
        "concurrent_devices": concurrent,
    }


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 78)
    print("HTTP API 性能基准    ASGI 直连 + 内存 SQLite")
    print("=" * 78)
    print(f"{'接口':<18}{'方法':<7}{'P50':>9}{'P95':>9}{'均值':>9}{'错误率':>9}")
    print("-" * 78)
    for name, item in report["endpoints"].items():
        print(
            f"{name:<18}{item['method']:<7}"
            f"{item['p50_ms']:>7.1f}ms{item['p95_ms']:>7.1f}ms"
            f"{item['mean_ms']:>7.1f}ms{item['error_rate'] * 100:>8.1f}%"
        )
    concurrent = report["concurrent_devices"]
    print("-" * 78)
    print(
        f"并发 {concurrent['requests']} 请求 / 并发度 {concurrent['concurrency']}："
        f"{concurrent['rps']} req/s，P95 {concurrent['p95_ms']:.1f}ms，"
        f"错误率 {concurrent['error_rate'] * 100:.1f}%"
    )
    print("=" * 78)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTTP API 性能基准")
    parser.add_argument("--iterations", type=int, default=100, help="每个接口的串行请求数")
    parser.add_argument("--concurrency", type=int, default=50, help="并发压测并发度")
    parser.add_argument("--concurrent-requests", type=int, default=300, help="并发请求总数")
    parser.add_argument("--json", dest="json_path", help="写入 JSON 报告")
    args = parser.parse_args(argv)

    report = asyncio.run(run(args.iterations, args.concurrency, args.concurrent_requests))
    _print_report(report)

    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
