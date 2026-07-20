import asyncio
from src.domain.discovery.models import HospitalCandidate, HospitalCoordinates, DiscoveryRequest, SearchLocation
from src.domain.context.enums import MedicalSpecialty, UrgencyLevel, BudgetPreference, HospitalTypePreference
from src.pipelines.discovery.validator import HospitalValidator
from src.ranking.scorer import HospitalScorer
from src.pipelines.discovery.tavily_search import TavilySearcher

def test_tavily_extraction():
    print("--- Testing Tavily Extraction ---")
    t = TavilySearcher()
    
    bad_titles = [
        "Top 10 Best Emergency Hospitals in Noida",
        "Does Swastham Medicare Offer 24/7 Emergency Services?",
        "Fortis Hospital Noida Reviews and Complaints",
        "How to choose the best hospital for cardiology"
    ]
    
    good_titles = [
        "Fortis Hospital Noida | Advanced Healthcare",
        "Apollo Medical Centre",
        "Narayana Multispeciality Hospital"
    ]
    
    for title in bad_titles:
        name = t._extract_hospital_name(title, "")
        print(f"BAD TITLE: '{title}' -> extracted: '{name}' (Expected: '')")
        assert name == ""
        
    for title in good_titles:
        name = t._extract_hospital_name(title, "")
        print(f"GOOD TITLE: '{title}' -> extracted: '{name}'")
        assert name != ""

def test_validator():
    print("\n--- Testing Hospital Quality Gate (Validator) ---")
    v = HospitalValidator()
    
    candidates = [
        HospitalCandidate(
            candidate_id="1", hospital_name="Best Cardiology Hospital", source="tavily"
        ),
        HospitalCandidate(
            candidate_id="2", hospital_name="Fortis Hospital", source="tavily"
        ),
        HospitalCandidate(
            candidate_id="3", hospital_name="Generic Medical Info", source="tavily", data_quality_score=0.1
        )
    ]
    
    valid = v.validate_all(candidates)
    names = [c.hospital_name for c in valid]
    print(f"Passed validation: {names}")
    assert "Best Cardiology Hospital" not in names
    assert "Generic Medical Info" not in names
    assert "Fortis Hospital" in names

def test_ranking():
    print("\n--- Testing Ranking Feature Collapse Fix ---")
    scorer = HospitalScorer()
    
    req = DiscoveryRequest(
        task_id="t1", context_id="c1",
        specialty=MedicalSpecialty.CARDIOLOGY,
        location=SearchLocation(city="Noida"),
        urgency=UrgencyLevel.ROUTINE,
        budget_preference=BudgetPreference.ANY,
        hospital_type_preference=HospitalTypePreference.BOTH
    )
    
    # Candidate 1: Real hospital with coordinates and website
    c1 = HospitalCandidate(
        candidate_id="1", hospital_name="Real Hospital", source="maps",
        coordinates=HospitalCoordinates(latitude=28.0, longitude=77.0),
        website="https://realhospital.com",
        data_quality_score=0.9
    )
    
    # Candidate 2: Bad extraction (no coords, no website, not nabh)
    c2 = HospitalCandidate(
        candidate_id="2", hospital_name="Fake Hospital", source="tavily",
        data_quality_score=0.9
    )
    
    score1 = scorer.score(c1, req)
    score2 = scorer.score(c2, req)
    
    print(f"Real Hospital Confidence: {score1.confidence_score}")
    print(f"Fake Hospital Confidence: {score2.confidence_score}")
    
    assert score1.confidence_score > 0.5
    assert score2.confidence_score < 0.2

if __name__ == "__main__":
    test_tavily_extraction()
    test_validator()
    test_ranking()
    print("\n✅ All internal logic tests passed!")
