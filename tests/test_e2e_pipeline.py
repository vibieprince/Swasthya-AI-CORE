"""
SWASTHYA AI CORE — End-to-End Integration Test

Validates the complete production pipeline:

Context API
      ↓
Discovery API
      ↓
RabbitMQ
      ↓
Discovery Worker
      ↓
Redis Progress
      ↓
Final Results

Prerequisites

1. python -m src.main
2. Discovery worker running
3. Redis running
4. RabbitMQ running
"""

import asyncio
import json
import time
from datetime import datetime
import httpx

API_BASE = "http://127.0.0.1:8000/api"

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def log(*args):
    print(f"[{ts()}]", *args)

async def run_e2e_test():

    log("=" * 60)
    log("SWASTHYA AI CORE — End-to-End Integration Test")
    log("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:

        ####################################################################
        # STEP 1
        ####################################################################

        log("\n[1/5] Calling Context API...")

        query = (
            "My father has diabetes and severe chest pain since 30 minutes. "
            "We are near Pari Chowk, Greater Noida. "
            "Budget is around ₹3 lakh. "
            "He has Star Health insurance."
        )

        t0 = time.monotonic()

        response = await client.post(
            f"{API_BASE}/context/analyze",
            json={
                "message": query
            }
        )

        elapsed = int((time.monotonic() - t0) * 1000)

        if response.status_code != 200:
            log("❌ Context API FAILED")
            log(response.status_code)
            log(response.text)
            return

        context_response = response.json()

        context = context_response["context_data"]

        log(f"✅ Context API Success ({elapsed} ms)")

        log(f"Intent       : {context['language']['detected_intent']}")
        log(f"Language     : {context['language']['language_name']}")
        log(f"Emergency    : {context['clinical']['is_emergency']}")
        log(f"Symptoms     : {context['clinical']['symptoms']}")
        log(f"Location     : {context['clinical']['patient_location']['raw_location']}")
        log(f"Specialty    : {context['clinical']['preferred_specialty']}")
        log(f"Sufficient   : {context['validation']['is_context_sufficient']}")

        ####################################################################
        # STEP 2
        ####################################################################

        log("\n[2/5] Calling Discovery API...")

        t0 = time.monotonic()

        response = await client.post(
            f"{API_BASE}/discovery/search",
            json={
                "context": context,
                "max_results": 4,
                "correlation_id": "e2e-test"
            }
        )

        elapsed = int((time.monotonic() - t0) * 1000)

        if response.status_code != 200:
            log("❌ Discovery API FAILED")
            log(response.status_code)
            log(response.text)
            return

        discovery = response.json()

        task_id = discovery["task_id"]

        log(f"✅ Discovery Queued ({elapsed} ms)")
        log("Task ID :", task_id)
        log("Status  :", discovery["status"])

        ####################################################################
        # STEP 3
        ####################################################################

        log("\n[3/5] Polling Task Progress...\n")

        previous = -1

        for _ in range(120):

            response = await client.get(
                f"{API_BASE}/tasks/{task_id}/progress"
            )

            if response.status_code != 200:
                log("❌ Progress API FAILED")
                log(response.status_code)
                log(response.text)
                return

            progress = response.json()

            percent = progress["progress_percent"]

            if percent != previous:
                previous = percent

                log(
                    f"{percent:>3}% | "
                    f"{progress['status']:10} | "
                    f"{progress['current_stage']}"
                )

            if progress["status"].lower() == "completed":

                log("\n✅ Discovery Completed")

                final_result = progress.get("result")

                break

            if progress["status"].lower() == "failed":

                log("\n❌ Discovery Failed")

                log(progress.get("error_message"))

                return

            await asyncio.sleep(2)

        else:

            log("\n❌ Timed out waiting for worker.")

            return

        ####################################################################
        # STEP 4
        ####################################################################

        log("\n[4/5] Final Result Validation")

        if final_result is None:

            log("Worker returned no result.")

            return

        if isinstance(final_result, str):
            try:
                final_result = json.loads(final_result)
            except Exception:
                pass

        recommendations = final_result.get("recommendations", [])

        log(f"Recommendations : {len(recommendations)}")

        for i, hospital in enumerate(recommendations, start=1):

            log()

            log(f"{i}. {hospital.get('hospital_name')}")

            log("Score :", hospital.get("scores", {}).get("clinical_suitability_score", hospital.get("final_score")))

            log(
                "Reason:",
                hospital.get(
                    "recommendation_summary_english",
                    hospital.get("recommendation_summary", "")
                )
            )

        ####################################################################
        # STEP 5
        ####################################################################

        log("\n[5/5] SUCCESS")

        log("=" * 60)

        log("✓ Context API")

        log("✓ Discovery API")

        log("✓ RabbitMQ")

        log("✓ Discovery Worker")

        log("✓ Redis Progress")

        log("✓ Final Recommendations")

        log("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())