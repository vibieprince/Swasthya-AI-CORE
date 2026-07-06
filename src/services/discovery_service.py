"""
SWASTHYA AI CORE — Discovery Service.

Application service layer for Hospital Discovery.
Validates input, generates a task ID, dispatches to the internal executor,
and returns immediately.
"""

from __future__ import annotations

import uuid

from src.common.correlation import get_correlation_id
from src.common.exceptions import SwasthyaBaseError
from src.common.logging import get_logger
from src.domain.context.enums import MedicalSpecialty, UrgencyLevel
from src.domain.context.models import PatientContext
from src.domain.discovery.models import DiscoveryRequest, SearchLocation
from src.dtos.discovery_dtos import DiscoverySearchRequest, DiscoverySearchResponse
from src.infrastructure.execution.executor import get_job_executor
from src.infrastructure.redis.client import create_task_progress

logger = get_logger(__name__)


class DiscoveryService:
    """
    Service for initiating asynchronous discovery tasks.
    """

    async def start_discovery(self, request: DiscoverySearchRequest) -> DiscoverySearchResponse:
        """
        Initiate a hospital discovery task asynchronously.
        
        1. Validate PatientContext has minimum requirements (location, specialty)
        2. Create a Redis task tracking record
        3. Dispatch to the internal async JobExecutor
        4. Return the task_id
        """
        correlation_id = get_correlation_id()
        task_id = str(uuid.uuid4())
        
        ctx: PatientContext = request.context
        
        # ── Pre-flight Validation ──────────────────────────────────────────────
        if not ctx.clinical.patient_location.city:
            raise SwasthyaBaseError("PatientContext must contain at least a city location.")
            
        if not ctx.clinical.preferred_specialty and not ctx.clinical.symptoms:
            raise SwasthyaBaseError("PatientContext must contain either a specialty or symptoms.")

        # ── Map to DiscoveryRequest Domain ─────────────────────────────────────
        discovery_request = DiscoveryRequest(
            task_id=task_id,
            context_id=ctx.context_id,
            specialty=ctx.clinical.preferred_specialty or MedicalSpecialty.GENERAL_MEDICINE,
            location=SearchLocation(
                city=ctx.clinical.patient_location.city,
                state=ctx.clinical.patient_location.state,
                pincode=ctx.clinical.patient_location.pincode,
                latitude=ctx.clinical.patient_location.latitude,
                longitude=ctx.clinical.patient_location.longitude,
                raw_text=ctx.clinical.patient_location.raw_location,
            ),
            urgency=ctx.clinical.urgency_level or UrgencyLevel.ROUTINE,
            budget_preference=ctx.clinical.budget.preference,
            hospital_type_preference=ctx.clinical.preferred_hospital_type,
            is_emergency=ctx.clinical.is_emergency,
            max_results=request.max_results,
            language_code=ctx.language.language_code,
            correlation_id=correlation_id,
        )

        # ── Initialize State & Dispatch ────────────────────────────────────────
        try:
            # 1. Create initial state in Redis (0% Queued)
            await create_task_progress(task_id, correlation_id)
            
            # 2. Dispatch to internal async executor
            # We serialize the Domain model to dict for consistency with the domain barrier
            msg_body = discovery_request.model_dump(mode="json")
            get_job_executor().submit_discovery_task(msg_body)
            
        except Exception as exc:
            logger.error("Failed to start discovery task", extra={"task_id": task_id, "error": str(exc)})
            raise SwasthyaBaseError("Failed to initiate discovery task.") from exc
            
        logger.info(
            "Discovery task initiated", 
            extra={"task_id": task_id, "specialty": discovery_request.specialty.value}
        )

        return DiscoverySearchResponse(task_id=task_id)
