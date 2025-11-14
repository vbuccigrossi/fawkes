"""
Differential Fuzzing Engine

Compares behavior across different versions/implementations of the same software
to find semantic bugs, security issues, and behavioral divergences.
"""

import os
import logging
import hashlib
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class DivergenceType(Enum):
    """Types of behavioral divergences"""
    CRASH = "crash"                      # One crashes, other doesn't
    DIFFERENT_OUTPUT = "different_output"  # Different outputs
    DIFFERENT_RETURN = "different_return"  # Different return codes
    TIMEOUT = "timeout"                  # One times out, other doesn't
    MEMORY_DIFF = "memory_diff"         # Different memory usage
    REGISTER_DIFF = "register_diff"     # Different register states
    EXCEPTION = "exception"             # Different exceptions/signals


class DivergenceSeverity(Enum):
    """Severity of divergences"""
    CRITICAL = "critical"    # Security-relevant (crash, corruption)
    HIGH = "high"           # Likely bug (different behavior)
    MEDIUM = "medium"       # Possible issue (minor differences)
    LOW = "low"            # Expected variation
    INFO = "info"          # Informational


@dataclass
class ExecutionResult:
    """Result of executing a testcase on one target"""
    target_id: str
    target_version: str
    testcase_path: str
    crashed: bool
    exit_code: int
    timeout: bool
    execution_time: float  # milliseconds
    stdout: Optional[str]
    stderr: Optional[str]
    output_hash: Optional[str]  # Hash of output for comparison
    registers: Optional[Dict[str, str]]
    signal: Optional[str]
    memory_usage: Optional[int]  # bytes
    error_message: Optional[str]


@dataclass
class Divergence:
    """Detected behavioral divergence"""
    divergence_id: str
    testcase_path: str
    divergence_type: DivergenceType
    severity: DivergenceSeverity
    target_a: ExecutionResult
    target_b: ExecutionResult
    description: str
    confidence: float  # 0.0-1.0
    details: Dict[str, Any]
    timestamp: int


class DifferentialEngine:
    """
    Core differential fuzzing engine

    Executes testcases across multiple targets and identifies divergences.
    """

    def __init__(self):
        self.logger = logging.getLogger("fawkes.differential")
        self.divergences: List[Divergence] = []
        self.stats = {
            "testcases_executed": 0,
            "divergences_found": 0,
            "crashes_found": 0,
            "timeouts": 0
        }

    def compare_executions(self, result_a: ExecutionResult,
                          result_b: ExecutionResult) -> List[Divergence]:
        """
        Compare two execution results and identify divergences

        Args:
            result_a: Result from target A
            result_b: Result from target B

        Returns:
            List of detected divergences
        """
        divergences = []
        testcase = result_a.testcase_path

        # 1. Check for crash divergence (most critical)
        if result_a.crashed != result_b.crashed:
            divergence = Divergence(
                divergence_id=self._generate_divergence_id(testcase, "crash"),
                testcase_path=testcase,
                divergence_type=DivergenceType.CRASH,
                severity=DivergenceSeverity.CRITICAL,
                target_a=result_a,
                target_b=result_b,
                description=f"Crash divergence: {result_a.target_version} "
                           f"{'crashed' if result_a.crashed else 'did not crash'}, "
                           f"{result_b.target_version} "
                           f"{'crashed' if result_b.crashed else 'did not crash'}",
                confidence=1.0,
                details={
                    "crashed_target": result_a.target_id if result_a.crashed else result_b.target_id,
                    "signal_a": result_a.signal,
                    "signal_b": result_b.signal
                },
                timestamp=int(time.time())
            )
            divergences.append(divergence)
            self.logger.warning(f"CRITICAL: Crash divergence detected in {testcase}")

        # 2. Check for timeout divergence
        if result_a.timeout != result_b.timeout:
            divergence = Divergence(
                divergence_id=self._generate_divergence_id(testcase, "timeout"),
                testcase_path=testcase,
                divergence_type=DivergenceType.TIMEOUT,
                severity=DivergenceSeverity.HIGH,
                target_a=result_a,
                target_b=result_b,
                description=f"Timeout divergence: {result_a.target_version} "
                           f"{'timed out' if result_a.timeout else 'completed'}, "
                           f"{result_b.target_version} "
                           f"{'timed out' if result_b.timeout else 'completed'}",
                confidence=1.0,
                details={
                    "exec_time_a": result_a.execution_time,
                    "exec_time_b": result_b.execution_time
                },
                timestamp=int(time.time())
            )
            divergences.append(divergence)

        # 3. Check for output divergence (if both completed successfully)
        if not result_a.crashed and not result_b.crashed and \
           not result_a.timeout and not result_b.timeout:

            # Compare output hashes
            if result_a.output_hash and result_b.output_hash and \
               result_a.output_hash != result_b.output_hash:

                # Calculate how different they are
                similarity = self._calculate_output_similarity(
                    result_a.stdout or "", result_b.stdout or ""
                )

                divergence = Divergence(
                    divergence_id=self._generate_divergence_id(testcase, "output"),
                    testcase_path=testcase,
                    divergence_type=DivergenceType.DIFFERENT_OUTPUT,
                    severity=self._assess_output_severity(similarity),
                    target_a=result_a,
                    target_b=result_b,
                    description=f"Output divergence: {result_a.target_version} and "
                               f"{result_b.target_version} produced different outputs "
                               f"({similarity*100:.1f}% similar)",
                    confidence=1.0 - similarity,
                    details={
                        "output_hash_a": result_a.output_hash,
                        "output_hash_b": result_b.output_hash,
                        "similarity": similarity
                    },
                    timestamp=int(time.time())
                )
                divergences.append(divergence)

            # Compare return codes
            if result_a.exit_code != result_b.exit_code:
                divergence = Divergence(
                    divergence_id=self._generate_divergence_id(testcase, "return"),
                    testcase_path=testcase,
                    divergence_type=DivergenceType.DIFFERENT_RETURN,
                    severity=DivergenceSeverity.MEDIUM,
                    target_a=result_a,
                    target_b=result_b,
                    description=f"Return code divergence: {result_a.target_version} "
                               f"returned {result_a.exit_code}, "
                               f"{result_b.target_version} returned {result_b.exit_code}",
                    confidence=0.9,
                    details={
                        "exit_code_a": result_a.exit_code,
                        "exit_code_b": result_b.exit_code
                    },
                    timestamp=int(time.time())
                )
                divergences.append(divergence)

        # 4. Check for register divergence (if crash states available)
        if result_a.registers and result_b.registers:
            reg_diff = self._compare_registers(result_a.registers, result_b.registers)
            if reg_diff:
                divergence = Divergence(
                    divergence_id=self._generate_divergence_id(testcase, "registers"),
                    testcase_path=testcase,
                    divergence_type=DivergenceType.REGISTER_DIFF,
                    severity=DivergenceSeverity.HIGH if result_a.crashed or result_b.crashed
                             else DivergenceSeverity.MEDIUM,
                    target_a=result_a,
                    target_b=result_b,
                    description=f"Register state divergence: {len(reg_diff)} registers differ",
                    confidence=0.8,
                    details={"differing_registers": reg_diff},
                    timestamp=int(time.time())
                )
                divergences.append(divergence)

        # 5. Check for memory usage divergence
        if result_a.memory_usage and result_b.memory_usage:
            mem_diff_pct = abs(result_a.memory_usage - result_b.memory_usage) / \
                          max(result_a.memory_usage, result_b.memory_usage)

            # If memory usage differs by more than 50%, flag it
            if mem_diff_pct > 0.5:
                divergence = Divergence(
                    divergence_id=self._generate_divergence_id(testcase, "memory"),
                    testcase_path=testcase,
                    divergence_type=DivergenceType.MEMORY_DIFF,
                    severity=DivergenceSeverity.LOW,
                    target_a=result_a,
                    target_b=result_b,
                    description=f"Memory usage divergence: {mem_diff_pct*100:.1f}% difference",
                    confidence=0.7,
                    details={
                        "memory_a": result_a.memory_usage,
                        "memory_b": result_b.memory_usage,
                        "diff_percent": mem_diff_pct
                    },
                    timestamp=int(time.time())
                )
                divergences.append(divergence)

        # Store divergences and update stats
        if divergences:
            self.divergences.extend(divergences)
            self.stats["divergences_found"] += len(divergences)

        return divergences

    def _generate_divergence_id(self, testcase: str, div_type: str) -> str:
        """Generate unique divergence ID"""
        content = f"{testcase}:{div_type}:{int(time.time())}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _calculate_output_similarity(self, output_a: str, output_b: str) -> float:
        """
        Calculate similarity between two outputs (0.0 = completely different, 1.0 = identical)
        Using simple string similarity for now
        """
        if output_a == output_b:
            return 1.0

        if not output_a or not output_b:
            return 0.0

        # Simple similarity based on common lines
        lines_a = set(output_a.split('\n'))
        lines_b = set(output_b.split('\n'))

        if not lines_a or not lines_b:
            return 0.0

        intersection = len(lines_a.intersection(lines_b))
        union = len(lines_a.union(lines_b))

        return intersection / union if union > 0 else 0.0

    def _assess_output_severity(self, similarity: float) -> DivergenceSeverity:
        """Assess severity based on output similarity"""
        if similarity < 0.2:
            return DivergenceSeverity.HIGH
        elif similarity < 0.5:
            return DivergenceSeverity.MEDIUM
        elif similarity < 0.8:
            return DivergenceSeverity.LOW
        else:
            return DivergenceSeverity.INFO

    def _compare_registers(self, regs_a: Dict[str, str],
                          regs_b: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
        """
        Compare register states

        Returns:
            Dict of {register: (value_a, value_b)} for differing registers
        """
        differences = {}

        # Check common registers
        for reg in set(regs_a.keys()).intersection(regs_b.keys()):
            if regs_a[reg] != regs_b[reg]:
                differences[reg] = (regs_a[reg], regs_b[reg])

        return differences

    def get_critical_divergences(self) -> List[Divergence]:
        """Get all critical severity divergences"""
        return [d for d in self.divergences if d.severity == DivergenceSeverity.CRITICAL]

    def get_divergences_by_type(self, div_type: DivergenceType) -> List[Divergence]:
        """Get divergences of a specific type"""
        return [d for d in self.divergences if d.divergence_type == div_type]

    def get_stats(self) -> Dict[str, Any]:
        """Get differential fuzzing statistics"""
        stats = self.stats.copy()

        # Add divergence breakdown by type
        stats["divergences_by_type"] = {}
        for div_type in DivergenceType:
            count = len(self.get_divergences_by_type(div_type))
            if count > 0:
                stats["divergences_by_type"][div_type.value] = count

        # Add divergence breakdown by severity
        stats["divergences_by_severity"] = {}
        for severity in DivergenceSeverity:
            count = len([d for d in self.divergences if d.severity == severity])
            if count > 0:
                stats["divergences_by_severity"][severity.value] = count

        return stats

    def generate_summary_report(self) -> str:
        """Generate text summary of differential fuzzing results"""
        lines = []
        lines.append("=" * 80)
        lines.append("DIFFERENTIAL FUZZING SUMMARY")
        lines.append("=" * 80)
        lines.append("")

        stats = self.get_stats()
        lines.append(f"Testcases Executed: {stats['testcases_executed']}")
        lines.append(f"Divergences Found: {stats['divergences_found']}")
        lines.append(f"Crashes Found: {stats['crashes_found']}")
        lines.append(f"Timeouts: {stats['timeouts']}")
        lines.append("")

        if stats.get("divergences_by_severity"):
            lines.append("Divergences by Severity:")
            for severity, count in sorted(stats["divergences_by_severity"].items(),
                                         key=lambda x: ["critical", "high", "medium", "low", "info"].index(x[0])):
                lines.append(f"  {severity.upper():12s}: {count}")
            lines.append("")

        if stats.get("divergences_by_type"):
            lines.append("Divergences by Type:")
            for div_type, count in sorted(stats["divergences_by_type"].items()):
                lines.append(f"  {div_type:20s}: {count}")
            lines.append("")

        # Show critical divergences
        critical = self.get_critical_divergences()
        if critical:
            lines.append("=" * 80)
            lines.append("CRITICAL DIVERGENCES")
            lines.append("=" * 80)
            lines.append("")
            for div in critical[:10]:  # Show top 10
                lines.append(f"ID: {div.divergence_id}")
                lines.append(f"Type: {div.divergence_type.value}")
                lines.append(f"Description: {div.description}")
                lines.append(f"Testcase: {div.testcase_path}")
                lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)
