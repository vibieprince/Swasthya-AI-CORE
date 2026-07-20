import time
import requests
import json
import uuid
import sys

BASE_URL = "http://127.0.0.1:8000"
ANALYZE_URL = f"{BASE_URL}/api/context/analyze"

def print_result(name, passed, latency, info=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} | {latency:4.0f} ms | {name:<35} | {info}")

def test_scenario(name, payload, expected_status=200, check_fn=None):
    t0 = time.time()
    try:
        resp = requests.post(ANALYZE_URL, json=payload, timeout=30)
        latency = (time.time() - t0) * 1000
        
        if resp.status_code != expected_status:
            print_result(name, False, latency, f"Expected HTTP {expected_status}, got {resp.status_code}. Body: {resp.text}")
            return False, None
            
        data = resp.json()
        if check_fn:
            try:
                passed, msg = check_fn(data)
                print_result(name, passed, latency, msg)
                return passed, data
            except Exception as e:
                print_result(name, False, latency, f"Check error: {str(e)}. Data: {json.dumps(data)[:200]}")
                return False, data
            
        print_result(name, True, latency, "Status OK")
        return True, data
        
    except Exception as e:
        latency = (time.time() - t0) * 1000
        print_result(name, False, latency, f"Exception: {str(e)}")
        return False, None

def run_all_tests():
    print("\n--- SWASTHYA AI CORE REGRESSION TESTS ---\n")
    
    # 1. Greetings (Fast path)
    test_scenario("Greeting 'Hi'", {"message": "Hi"}, check_fn=lambda d: (d["language"]["is_greeting"] == True, "Fast path worked" if d["processing_latency_ms"] < 100 else f"Slow: {d['processing_latency_ms']}ms"))
    test_scenario("Greeting 'Hello'", {"message": "Hello"}, check_fn=lambda d: (d["language"]["is_greeting"] == True, "Fast path worked"))
    test_scenario("Greeting 'Namaste'", {"message": "Namaste"}, check_fn=lambda d: (d["language"]["is_greeting"] == True and d["language"]["language_code"] == "hi", "Fast path Hindi worked"))

    # 2. Greeting + Irrelevant
    test_scenario("Greeting + Irrelevant", {"message": "Hi tell me a joke"}, check_fn=lambda d: (d["language"]["is_irrelevant"] == True and d["language"]["is_greeting"] == False, "Handled as irrelevant"))

    # 3. Irrelevant
    test_scenario("Irrelevant query", {"message": "What is the weather?"}, check_fn=lambda d: (d["language"]["is_irrelevant"] == True, "Handled as irrelevant"))

    # 4. Minimal Healthcare
    passed, data1 = test_scenario("Minimal Healthcare", {"message": "I have fever."}, check_fn=lambda d: (
        "fever" in " ".join(d["clinical"]["symptoms"]).lower() and not d["validation"]["is_context_sufficient"],
        "Extracted symptom, needs follow-up"
    ))

    # 5. Symptom + Location
    test_scenario("Symptom + Location", {"message": "I have fever in Delhi."}, check_fn=lambda d: (
        d["clinical"]["patient_location"]["city"] != None or d["clinical"]["patient_location"]["raw_location"] != None,
        "Extracted both"
    ))

    # 6. Anatomical vs Geographical (I have pain -> lower abdomen)
    _, anat_1 = test_scenario("Anatomical 1", {"message": "I have pain"})
    if anat_1:
        ctx_id = anat_1["context_id"]
        test_scenario("Anatomical 2 (Abdomen)", {"context_id": ctx_id, "message": "Lower abdomen"}, check_fn=lambda d: (
            not d["validation"]["is_context_sufficient"],
            "Still needs geographical location"
        ))

    # 7. Continuation (Fever -> Delhi)
    if passed and data1:
        ctx_id = data1["context_id"]
        test_scenario("Continuation (Delhi)", {"context_id": ctx_id, "message": "Delhi"}, check_fn=lambda d: (
            d["clinical"]["patient_location"]["city"] != None or d["clinical"]["patient_location"]["raw_location"] != None,
            "Merged Delhi successfully"
        ))

    # 8. Emergency
    test_scenario("Emergency", {"message": "Severe chest pain in Mumbai."}, check_fn=lambda d: (
        d["clinical"]["is_emergency"] == True,
        "Detected emergency"
    ))

    # 9. Hindi
    test_scenario("Hindi message", {"message": "मुझे बुखार है।"}, check_fn=lambda d: (
        d["language"]["language_code"] == "hi",
        "Detected Hindi"
    ))

    # 10. Hinglish
    test_scenario("Hinglish message", {"message": "Mujhe fever hai."}, check_fn=lambda d: (
        d["language"]["language_code"] in ["hi", "en"],
        "Handled Hinglish"
    ))

    # 11. Empty request
    test_scenario("Empty request", {"message": ""}, expected_status=422)

    # 12. Invalid request
    test_scenario("Invalid request (missing message)", {}, expected_status=422)

    # 13. Invalid context_id
    test_scenario("Invalid context_id", {"context_id": str(uuid.uuid4()), "message": "Hi"}, expected_status=410)

    # 14. Long message
    test_scenario("Long message", {"message": "I have fever " * 500}, expected_status=413)

    print("\nTests complete.")

if __name__ == "__main__":
    run_all_tests()
