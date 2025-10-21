"""
Scenario State Tracking for Multi-Step Scenario Execution

This module provides a state machine for tracking the execution of multi-step
diagnostic scenarios. It helps prevent looping and ensures proper sequential
execution of scenario steps.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScenarioStep:
    """Represents a single step in a diagnostic scenario"""
    
    step_number: int
    query_id: str
    status: str = "pending"  # pending, completed, failed, skipped
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ScenarioExecution:
    """Tracks the execution state of a multi-step scenario"""
    
    scenario_slug: str
    total_steps: int
    current_step: int = 0
    steps: dict[int, ScenarioStep] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    
    def is_complete(self) -> bool:
        """Check if all steps have been attempted"""
        return self.current_step >= self.total_steps
    
    def get_next_pending_step(self) -> Optional[ScenarioStep]:
        """Get the next step that hasn't been completed"""
        for step in self.steps.values():
            if step.status == "pending":
                return step
        return None
    
    def mark_step_complete(self, step_number: int, result: Any) -> None:
        """Mark a step as successfully completed"""
        if step_number in self.steps:
            self.steps[step_number].status = "completed"
            self.steps[step_number].result = result
            self.current_step = max(self.current_step, step_number)
            logger.info(f"Step {step_number} completed. Progress: {self.current_step}/{self.total_steps}")
    
    def mark_step_failed(self, step_number: int, error: str) -> None:
        """Mark a step as failed"""
        if step_number in self.steps:
            self.steps[step_number].status = "failed"
            self.steps[step_number].error = error
            self.current_step = max(self.current_step, step_number)
            logger.warning(f"Step {step_number} failed: {error}")
    
    def mark_step_skipped(self, step_number: int, reason: str) -> None:
        """Mark a step as skipped (e.g., due to missing dependencies)"""
        if step_number in self.steps:
            self.steps[step_number].status = "skipped"
            self.steps[step_number].error = reason
            self.current_step = max(self.current_step, step_number)
            logger.info(f"Step {step_number} skipped: {reason}")
    
    def get_completed_steps(self) -> list[int]:
        """Get list of completed step numbers"""
        return [num for num, step in self.steps.items() if step.status == "completed"]
    
    def get_progress_summary(self) -> str:
        """Get a human-readable progress summary"""
        completed = sum(1 for s in self.steps.values() if s.status == "completed")
        failed = sum(1 for s in self.steps.values() if s.status == "failed")
        skipped = sum(1 for s in self.steps.values() if s.status == "skipped")
        
        summary_parts = [f"{completed}/{self.total_steps} steps completed"]
        if failed > 0:
            summary_parts.append(f"{failed} failed")
        if skipped > 0:
            summary_parts.append(f"{skipped} skipped")
        
        return ", ".join(summary_parts)


class ScenarioStateTracker:
    """Track execution state for multi-step scenarios
    
    This singleton tracker maintains state for the currently executing scenario,
    preventing the agent from restarting or looping through steps.
    """
    
    def __init__(self) -> None:
        self.active_scenario: Optional[ScenarioExecution] = None
    
    def start_scenario(self, slug: str, steps: list[dict[str, Any]]) -> ScenarioExecution:
        """Initialize tracking for a new scenario
        
        Args:
            slug: Scenario identifier
            steps: List of step definitions from get_scenario
            
        Returns:
            ScenarioExecution instance
        """
        execution = ScenarioExecution(
            scenario_slug=slug,
            total_steps=len(steps)
        )
        
        for step in steps:
            step_num = step.get('step_number', 0)
            query_id = step.get('query_id', '')
            execution.steps[step_num] = ScenarioStep(
                step_number=step_num,
                query_id=query_id
            )
        
        self.active_scenario = execution
        logger.info(f"Started tracking scenario '{slug}' with {len(steps)} steps")
        return execution
    
    def get_active_scenario(self) -> Optional[ScenarioExecution]:
        """Get the currently active scenario execution"""
        return self.active_scenario
    
    def clear_scenario(self) -> None:
        """Clear the active scenario (for starting fresh)"""
        if self.active_scenario:
            logger.info(f"Clearing scenario '{self.active_scenario.scenario_slug}' - {self.active_scenario.get_progress_summary()}")
        self.active_scenario = None
    
    def get_progress_info(self) -> str:
        """Get progress information for the active scenario"""
        if not self.active_scenario:
            return "No active scenario"
        return f"Scenario '{self.active_scenario.scenario_slug}': {self.active_scenario.get_progress_summary()}"


# Global singleton instance
scenario_tracker = ScenarioStateTracker()
