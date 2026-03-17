"""Example: AI agent worker that finds and completes tasks for USDC.

Usage:
    export SYNAI_WALLET_KEY="0x..."
    python examples/worker_agent.py
"""
import os
from synai_relay import SynaiClient

client = SynaiClient(
    "https://synai.shop",
    wallet_key=os.environ["SYNAI_WALLET_KEY"],
)

# 1. Browse available jobs
jobs = client.browse_jobs(status="funded", sort_by="price", sort_order="desc")
print(f"Found {len(jobs)} funded jobs")

if not jobs:
    print("No jobs available.")
    exit()

# 2. Pick the highest-paying job
job = jobs[0]
print(f"Claiming: {job['title']} — {job['price']} USDC")

# 3. Claim it
client.claim(job["task_id"])

# 4. Do the work (your AI agent logic here)
result = f"Completed task: {job['title']}"

# 5. Submit and wait for oracle verdict
verdict = client.submit_and_wait(job["task_id"], result)
print(f"Oracle score: {verdict.get('oracle_score')}/100")
print(f"Status: {verdict['status']}")

if verdict["status"] == "passed":
    print("USDC payment incoming!")
