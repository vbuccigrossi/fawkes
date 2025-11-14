"""
Automated Crash Report Generator

Generates professional triage reports in multiple formats:
- Text reports
- JSON reports
- Markdown reports
- HTML reports (optional)
"""

import os
import json
from datetime import datetime
from typing import List, Dict
from analysis.enhanced_triage import CrashAnalysis, Severity, VulnType


class ReportGenerator:
    """Generate formatted crash reports"""

    def __init__(self, output_dir: str = "~/.fawkes/reports"):
        self.output_dir = os.path.expanduser(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_text_report(self, analysis: CrashAnalysis) -> str:
        """Generate detailed text report"""
        lines = []
        lines.append("=" * 80)
        lines.append("FAWKES CRASH TRIAGE REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Header
        lines.append(f"Crash ID: {analysis.crash_id}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Signature: {analysis.signature}")
        lines.append(f"Stack Hash: {analysis.stack_hash}")
        lines.append("")

        # Severity and Exploitability
        lines.append("=" * 80)
        lines.append("SEVERITY ASSESSMENT")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Severity: {analysis.severity.value}")
        lines.append(f"Exploitability Score: {analysis.exploitability_score}/100")
        lines.append(f"Confidence: {analysis.confidence * 100:.1f}%")
        lines.append("")

        # Vulnerability Classification
        lines.append("=" * 80)
        lines.append("VULNERABILITY CLASSIFICATION")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Type: {analysis.vuln_type.value}")
        lines.append(f"Class: {analysis.vuln_class}")
        lines.append(f"Control Flow Hijack: {'YES' if analysis.control_flow_hijack else 'NO'}")
        lines.append(f"Memory Corruption: {'YES' if analysis.memory_corruption else 'NO'}")
        lines.append(f"Controlled Data: {'YES' if analysis.controlled_data else 'NO'}")
        lines.append("")

        # Exploit Indicators
        if analysis.indicators:
            lines.append("=" * 80)
            lines.append("EXPLOIT INDICATORS")
            lines.append("=" * 80)
            lines.append("")
            for indicator in analysis.indicators:
                lines.append(f"  • {indicator}")
            lines.append("")

        # Stack Trace
        if analysis.stack_frames:
            lines.append("=" * 80)
            lines.append("STACK TRACE")
            lines.append("=" * 80)
            lines.append("")
            for i, frame in enumerate(analysis.stack_frames):
                lines.append(f"  #{i}: {frame}")
            lines.append("")

        # Registers
        if analysis.registers:
            lines.append("=" * 80)
            lines.append("REGISTERS")
            lines.append("=" * 80)
            lines.append("")
            for reg, val in sorted(analysis.registers.items()):
                lines.append(f"  {reg:8s} = {val}")
            lines.append("")

        # Crash Details
        lines.append("=" * 80)
        lines.append("CRASH DETAILS")
        lines.append("=" * 80)
        lines.append("")
        if analysis.fault_address:
            lines.append(f"Fault Address: {analysis.fault_address}")
        if analysis.crash_instruction:
            lines.append(f"Crash Instruction: {analysis.crash_instruction}")
        lines.append("")

        # Security Mitigations
        if analysis.mitigations:
            lines.append("=" * 80)
            lines.append("ACTIVE MITIGATIONS")
            lines.append("=" * 80)
            lines.append("")
            for mitigation in analysis.mitigations:
                lines.append(f"  ✓ {mitigation}")
            lines.append("")

        # Root Cause Analysis
        if analysis.root_cause:
            lines.append("=" * 80)
            lines.append("ROOT CAUSE ANALYSIS")
            lines.append("=" * 80)
            lines.append("")
            lines.append(analysis.root_cause)
            lines.append("")

        # Suggested Fix
        if analysis.suggested_fix:
            lines.append("=" * 80)
            lines.append("SUGGESTED FIX")
            lines.append("=" * 80)
            lines.append("")
            lines.append(analysis.suggested_fix)
            lines.append("")

        # Similar CVEs
        if analysis.similar_cves:
            lines.append("=" * 80)
            lines.append("SIMILAR KNOWN VULNERABILITIES")
            lines.append("=" * 80)
            lines.append("")
            for cve in analysis.similar_cves:
                lines.append(f"  • {cve}")
            lines.append("")

        # Triage Notes
        if analysis.triage_notes:
            lines.append("=" * 80)
            lines.append("TRIAGE NOTES")
            lines.append("=" * 80)
            lines.append("")
            for note in analysis.triage_notes:
                lines.append(f"  • {note}")
            lines.append("")

        # Recommendations
        lines.append("=" * 80)
        lines.append("RECOMMENDATIONS")
        lines.append("=" * 80)
        lines.append("")

        if analysis.severity == Severity.CRITICAL:
            lines.append("⚠️  CRITICAL: Immediate action required!")
            lines.append("  1. Isolate affected systems")
            lines.append("  2. Verify exploitability with POC")
            lines.append("  3. Develop and test fix immediately")
            lines.append("  4. Consider emergency patch release")
        elif analysis.severity == Severity.HIGH:
            lines.append("⚠️  HIGH: Priority fix needed")
            lines.append("  1. Reproduce crash reliably")
            lines.append("  2. Analyze with debugger")
            lines.append("  3. Develop fix for next release")
            lines.append("  4. Add regression test")
        elif analysis.severity == Severity.MEDIUM:
            lines.append("  1. Reproduce and document crash")
            lines.append("  2. Schedule fix for upcoming release")
            lines.append("  3. Add to bug tracker")
        else:
            lines.append("  1. Document crash for future reference")
            lines.append("  2. Consider low-priority fix")

        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)

        return "\n".join(lines)

    def generate_json_report(self, analysis: CrashAnalysis) -> str:
        """Generate machine-readable JSON report"""
        report = {
            'generated': datetime.now().isoformat(),
            'crash_analysis': analysis.to_dict(),
            'metadata': {
                'generator': 'Fawkes Enhanced Triage',
                'version': '0.2.0'
            }
        }
        return json.dumps(report, indent=2)

    def generate_markdown_report(self, analysis: CrashAnalysis) -> str:
        """Generate Markdown report for documentation"""
        lines = []

        # Header
        lines.append(f"# Crash Report: {analysis.crash_id}")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Signature**: `{analysis.signature}`")
        lines.append(f"**Stack Hash**: `{analysis.stack_hash}`")
        lines.append("")

        # Severity Badge
        severity_emoji = {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟠",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
            Severity.INFO: "🔵"
        }
        emoji = severity_emoji.get(analysis.severity, "⚪")

        lines.append(f"## {emoji} Severity: {analysis.severity.value}")
        lines.append("")
        lines.append(f"- **Exploitability Score**: {analysis.exploitability_score}/100")
        lines.append(f"- **Confidence**: {analysis.confidence * 100:.1f}%")
        lines.append("")

        # Vulnerability Info
        lines.append("## 🐛 Vulnerability")
        lines.append("")
        lines.append(f"- **Type**: {analysis.vuln_type.value}")
        lines.append(f"- **Class**: {analysis.vuln_class}")
        lines.append(f"- **Control Flow Hijack**: {' ✅' if analysis.control_flow_hijack else '❌'}")
        lines.append(f"- **Memory Corruption**: {'✅' if analysis.memory_corruption else '❌'}")
        lines.append(f"- **Controlled Data**: {'✅' if analysis.controlled_data else '❌'}")
        lines.append("")

        # Indicators
        if analysis.indicators:
            lines.append("## ⚠️ Exploit Indicators")
            lines.append("")
            for indicator in analysis.indicators:
                lines.append(f"- {indicator}")
            lines.append("")

        # Stack Trace
        if analysis.stack_frames:
            lines.append("## 📋 Stack Trace")
            lines.append("")
            lines.append("```")
            for i, frame in enumerate(analysis.stack_frames):
                lines.append(f"#{i}: {frame}")
            lines.append("```")
            lines.append("")

        # Registers
        if analysis.registers:
            lines.append("## 🔧 Registers")
            lines.append("")
            lines.append("```")
            for reg, val in sorted(analysis.registers.items()):
                lines.append(f"{reg:8s} = {val}")
            lines.append("```")
            lines.append("")

        # Root Cause
        if analysis.root_cause:
            lines.append("## 🔍 Root Cause")
            lines.append("")
            lines.append(analysis.root_cause)
            lines.append("")

        # Fix Suggestion
        if analysis.suggested_fix:
            lines.append("## 🛠️ Suggested Fix")
            lines.append("")
            lines.append(analysis.suggested_fix)
            lines.append("")

        # Similar CVEs
        if analysis.similar_cves:
            lines.append("## 🔗 Similar CVEs")
            lines.append("")
            for cve in analysis.similar_cves:
                lines.append(f"- {cve}")
            lines.append("")

        # Mitigations
        if analysis.mitigations:
            lines.append("## 🛡️ Active Mitigations")
            lines.append("")
            for mitigation in analysis.mitigations:
                lines.append(f"- ✅ {mitigation}")
            lines.append("")

        return "\n".join(lines)

    def save_report(self, analysis: CrashAnalysis, formats: List[str] = None) -> Dict[str, str]:
        """
        Save report in multiple formats

        Args:
            analysis: CrashAnalysis object
            formats: List of formats ('text', 'json', 'markdown'). Default: all

        Returns:
            Dict mapping format to saved file path
        """
        if formats is None:
            formats = ['text', 'json', 'markdown']

        saved_files = {}
        base_name = f"crash_report_{analysis.stack_hash}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if 'text' in formats:
            text_path = os.path.join(self.output_dir, f"{base_name}.txt")
            with open(text_path, 'w') as f:
                f.write(self.generate_text_report(analysis))
            saved_files['text'] = text_path

        if 'json' in formats:
            json_path = os.path.join(self.output_dir, f"{base_name}.json")
            with open(json_path, 'w') as f:
                f.write(self.generate_json_report(analysis))
            saved_files['json'] = json_path

        if 'markdown' in formats:
            md_path = os.path.join(self.output_dir, f"{base_name}.md")
            with open(md_path, 'w') as f:
                f.write(self.generate_markdown_report(analysis))
            saved_files['markdown'] = md_path

        return saved_files


def generate_summary_report(analyses: List[CrashAnalysis], output_path: str = None) -> str:
    """
    Generate summary report across multiple crashes

    Args:
        analyses: List of CrashAnalysis objects
        output_path: Optional path to save report

    Returns:
        Summary report text
    """
    lines = []
    lines.append("=" * 80)
    lines.append("FAWKES CRASH SUMMARY REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Crashes Analyzed: {len(analyses)}")
    lines.append("")

    # Severity breakdown
    severity_counts = {}
    for analysis in analyses:
        severity_counts[analysis.severity] = severity_counts.get(analysis.severity, 0) + 1

    lines.append("=" * 80)
    lines.append("SEVERITY BREAKDOWN")
    lines.append("=" * 80)
    lines.append("")
    for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
        count = severity_counts.get(severity, 0)
        if count > 0:
            percentage = (count / len(analyses)) * 100
            lines.append(f"  {severity.value:12s}: {count:3d} ({percentage:5.1f}%)")
    lines.append("")

    # Vulnerability type breakdown
    vuln_counts = {}
    for analysis in analyses:
        vuln_counts[analysis.vuln_type] = vuln_counts.get(analysis.vuln_type, 0) + 1

    lines.append("=" * 80)
    lines.append("VULNERABILITY TYPES")
    lines.append("=" * 80)
    lines.append("")
    for vuln_type, count in sorted(vuln_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(analyses)) * 100
        lines.append(f"  {vuln_type.value:30s}: {count:3d} ({percentage:5.1f}%)")
    lines.append("")

    # Top crashes by exploitability
    lines.append("=" * 80)
    lines.append("TOP 10 MOST EXPLOITABLE CRASHES")
    lines.append("=" * 80)
    lines.append("")
    sorted_analyses = sorted(analyses, key=lambda x: x.exploitability_score, reverse=True)[:10]
    for i, analysis in enumerate(sorted_analyses, 1):
        lines.append(f"  {i:2d}. {analysis.crash_id}")
        lines.append(f"      Score: {analysis.exploitability_score}/100 | {analysis.severity.value} | {analysis.vuln_type.value}")
        lines.append("")

    # Unique crashes (by stack hash)
    unique_hashes = set(a.stack_hash for a in analyses)
    lines.append("=" * 80)
    lines.append("DEDUPLICATION RESULTS")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"  Total Crashes: {len(analyses)}")
    lines.append(f"  Unique Crashes: {len(unique_hashes)}")
    lines.append(f"  Duplicate Rate: {((len(analyses) - len(unique_hashes)) / len(analyses) * 100):.1f}%")
    lines.append("")

    # Recommendations
    critical_count = severity_counts.get(Severity.CRITICAL, 0)
    high_count = severity_counts.get(Severity.HIGH, 0)

    lines.append("=" * 80)
    lines.append("RECOMMENDATIONS")
    lines.append("=" * 80)
    lines.append("")

    if critical_count > 0:
        lines.append(f"⚠️  CRITICAL: {critical_count} critical vulnerabilities require immediate attention!")
        lines.append("  → Review all critical crashes immediately")
        lines.append("  → Develop patches and test thoroughly")
        lines.append("  → Consider security advisory/CVE assignment")
        lines.append("")

    if high_count > 0:
        lines.append(f"⚠️  HIGH: {high_count} high-severity vulnerabilities need priority fixes")
        lines.append("  → Schedule fixes for next release cycle")
        lines.append("  → Add regression tests")
        lines.append("")

    lines.append("=" * 80)
    lines.append("END OF SUMMARY")
    lines.append("=" * 80)

    report_text = "\n".join(lines)

    if output_path:
        with open(output_path, 'w') as f:
            f.write(report_text)

    return report_text
