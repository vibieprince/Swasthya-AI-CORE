"""
SWASTHYA AI CORE — End-to-End Integration Test.

Automatically verifies the entire distributed pipeline:
Context API → Discovery API → RabbitMQ → Worker → Redis → Progress API.

Prerequisites:
1. API Server is running (python -m src.main)
2. Worker is running (python -m src.workers.discovery_worker)
3. Redis and RabbitMQ are available
"""

import asyncio
import time
from typing import Any

import httpx

API_BASE_URL = "http://localhost:8000/api"


async def run_e2e_test() -> None:
    print("==========================================================")
    print("SWASTHYA AI CORE — End-to-End Integration Test")
    print("==========================================================\n")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # ── 1. Context API ──────────────────────────────────────────────────
        print("[1/5] Submitting query to Context API...")
        query = "My grandfather is having severe chest pain and sweating profusely. We need a hospital in South Delhi immediately."
        
        t0 = time.monotonic()
        context_res = await client.post(
            f"{API_BASE_URL}/context/analyze",
            json={"message": query}
        )
        
        if context_res.status_code != 200:
            print(f"❌ Context API failed: {context_res.status_code}")
            print(context_res.text)
            return

        context_data = context_res.json()
        print(f"✅ Context API Success ({int((time.monotonic()-t0)*1000)}ms)")
        print(f"   Intent: {context_data['language']['detected_intent']}")
        print(f"   Emergency: {context_data['clinical']['is_emergency']}")
        print(f"   Location: {context_data['clinical']['patient_location'].get('city')}")
        
        # ── 2. Discovery API ────────────────────────────────────────────────
        print("\n[2/5] Initiating Discovery Task...")
        t0 = time.monotonic()
        discovery_res = await client.post(
            f"{API_BASE_URL}/discovery/search",
            json={"context": context_data, "max_results": 4}
        )
        
        if discovery_res.status_code != 200:
            print(f"❌ Discovery API failed: {discovery_res.status_code}")
            print(discovery_res.text)
            return
            
        task_data = discovery_res.json()
        task_id = task_data["task_id"]
        print(f"✅ Discovery Task Queued ({int((time.monotonic()-t0)*1000)}ms)")
        print(f"   Task ID: {task_id}")

        # ── 3. Polling Progress ──────────────────────────────────────────────
        print("\n[3/5] Polling Task Progress from Redis (via API)...")
        
        max_attempts = 120  # 4 minutes max
        delay_seconds = 2.0
        
        final_result = None
        last_percent = -1
        
        for attempt in range(max_attempts):
            progress_res = await client.get(f"{API_BASE_URL}/tasks/{task_id}/progress")
            
            if progress_res.status_code != 200:
                print(f"❌ Progress API failed: {progress_res.status_code}")
                print(progress_res.text)
                return
                
            progress_data = progress_res.json()
            status = progress_data["status"]
            percent = progress_data["progress_percent"]
            stage = progress_data["current_stage"]
            
            # Print only when progress advances
            if percent > last_percent:
                print(f"   ⏳ {status.upper()} [{percent}%] — {stage}")
                last_percent = percent
                
            if status == "completed":
                final_result = progress_data.get("result")
                print(f"\n✅ Task Completed successfully!")
                break
            elif status == "failed":
                print(f"\n❌ Task Failed: {progress_data.get('error_message')}")
                return
                
            await asyncio.sleep(delay_seconds)
            
        else:
            print("\n❌ Task timed out after 4 minutes.")
            return

        # ── 4. Final Output Validation ──────────────────────────────────────
        print("\n[4/5] Validating Output...")
        if not final_result:
            print("❌ No final result found in completed task.")
            return
            
        recs = final_result.get("recommendations", [])
        print(f"✅ Retrieved {len(recs)} ranked hospitals.")
        
        for i, rec in enumerate(recs, 1):
            name = rec["candidate"]["hospital_name"]
            score = rec["final_score"]
            print(f"   {i}. {name} (Score: {score:.2f})")
            print(f"      Explain: {rec['explanation']['summary']}")
            
        print("\n==========================================================")
        print("🎉 END-TO-END PIPELINE VALIDATED SUCCESSFULLY 🎉")
        print("==========================================================")


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
