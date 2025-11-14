"""
Enhanced Crash Triage System

Provides advanced crash analysis beyond basic exploitability ranking:
- Stack hash deduplication
- Vulnerability pattern detection
- Severity scoring
- Root cause analysis
- Automated report generation
"""

import os
import json
import re
import hashlib
import zipfile
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger("fawkes.triage")


class Severity(Enum):
    """Crash severity levels"""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"
    UNKNOWN = "Unknown"


class VulnType(Enum):
    """Vulnerability types"""
    BUFFER_OVERFLOW = "Buffer Overflow"
    STACK_OVERFLOW = "Stack Overflow"
    HEAP_OVERFLOW = "Heap Overflow"
    USE_AFTER_FREE = "Use After Free"
    DOUBLE_FREE = "Double Free"
    NULL_DEREF = "Null Pointer Dereference"
    INT_OVERFLOW = "Integer Overflow"
    FORMAT_STRING = "Format String"
    RACE_CONDITION = "Race Condition"
    UNINITIALIZED = "Uninitialized Memory"
    TYPE_CONFUSION = "Type Confusion"
    PC_CONTROL = "Program Counter Control"
    ARBITRARY_WRITE = "Arbitrary Write"
    ARBITRARY_READ = "Arbitrary Read"
    UNKNOWN = "Unknown"


@dataclass
class CrashAnalysis:
    """Complete crash analysis result"""
    crash_id: str
    signature: str
    stack_hash: str
    severity: Severity
    exploitability_score: int  # 0-100
    vuln_type: VulnType
    vuln_class: str
    control_flow_hijack: bool
    memory_corruption: bool
    controlled_data: bool
    stack_frames: List[str]
    registers: Dict[str, str]
    fault_address: Optional[str]
    crash_instruction: Optional[str]
    confidence: float  # 0.0-1.0
    indicators: List[str]  # List of exploit indicators found
    mitigations: List[str]  # List of active mitigations (ASLR, DEP, etc.)
    root_cause: Optional[str]
    suggested_fix: Optional[str]
    similar_cves: List[str]
    triage_notes: List[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary with enum values as strings"""
        d = asdict(self)
        d['severity'] = self.severity.value
        d['vuln_type'] = self.vuln_type.value
        return d


class EnhancedTriageEngine:
    """Advanced crash triage and analysis engine"""

    def __init__(self):
        self.logger = logging.getLogger("fawkes.triage.engine")

        # Vulnerability patterns for detection
        self.vuln_patterns = self._init_vuln_patterns()

        # Exploitability indicators
        self.exploit_indicators = self._init_exploit_indicators()

        # Known CVE patterns (can be expanded)
        self.cve_patterns = self._init_cve_patterns()

    def _init_vuln_patterns(self) -> Dict[VulnType, List[Dict]]:
        """Initialize vulnerability detection patterns"""
        return {
            VulnType.BUFFER_OVERFLOW: [
                {
                    'pattern': r'buffer overflow|stack smashing|__stack_chk_fail',
                    'weight': 0.9,
                    'register_patterns': [r'(rsp|esp|rbp|ebp).*0x[4-9a-fA-F]{8,}']
                },
                {
                    'pattern': r'strcpy|strcat|sprintf|gets|scanf',
                    'weight': 0.6,
                    'desc': 'Unsafe string function'
                }
            ],
            VulnType.STACK_OVERFLOW: [
                {
                    'pattern': r'stack overflow|stack exhausted',
                    'weight': 0.95,
                },
                {
                    'pattern': r'(rsp|esp).*0x[0-9a-fA-F]{1,4}$',
                    'weight': 0.7,
                    'desc': 'Stack pointer near zero'
                }
            ],
            VulnType.HEAP_OVERFLOW: [
                {
                    'pattern': r'heap.*corrupt|malloc.*corrupt|free.*invalid',
                    'weight': 0.9
                },
                {
                    'pattern': r'corrupted size|invalid next size',
                    'weight': 0.85
                }
            ],
            VulnType.USE_AFTER_FREE: [
                {
                    'pattern': r'use after free|freed memory|double free',
                    'weight': 0.9
                },
                {
                    'pattern': r'invalid pointer|freed pointer',
                    'weight': 0.7
                }
            ],
            VulnType.NULL_DEREF: [
                {
                    'pattern': r'null.*deref|nullptr|0x0+\s',
                    'weight': 0.85
                },
                {
                    'pattern': r'segmentation fault.*0x0+',
                    'weight': 0.8
                }
            ],
            VulnType.FORMAT_STRING: [
                {
                    'pattern': r'%n|%s.*%x|printf.*%',
                    'weight': 0.7
                },
                {
                    'pattern': r'format string|printf vulnerability',
                    'weight': 0.9
                }
            ],
            VulnType.PC_CONTROL: [
                {
                    'pattern': r'(rip|eip|pc).*0x41414141',
                    'weight': 0.95,
                    'desc': 'Program counter overwritten with pattern'
                },
                {
                    'pattern': r'(rip|eip|pc).*corrupted',
                    'weight': 0.85
                }
            ]
        }

    def _init_exploit_indicators(self) -> List[Dict]:
        """Initialize exploitability indicators"""
        return [
            {
                'name': 'PC Control',
                'pattern': r'(rip|eip|pc).*0x[4-9a-fA-F]',
                'score': 40,
                'severity': Severity.CRITICAL
            },
            {
                'name': 'Return Address Overwrite',
                'pattern': r'return address.*overwrit|ret.*corrupt',
                'score': 35,
                'severity': Severity.CRITICAL
            },
            {
                'name': 'Stack Corruption',
                'pattern': r'stack.*corrupt|__stack_chk_fail',
                'score': 30,
                'severity': Severity.HIGH
            },
            {
                'name': 'Arbitrary Write',
                'pattern': r'write.*arbitrary|write-what-where',
                'score': 35,
                'severity': Severity.CRITICAL
            },
            {
                'name': 'Heap Metadata Corruption',
                'pattern': r'heap.*metadata|chunk.*corrupt',
                'score': 25,
                'severity': Severity.HIGH
            },
            {
                'name': 'ROP Gadgets Available',
                'pattern': r'rop|gadget|return-oriented',
                'score': 15,
                'severity': Severity.MEDIUM
            }
        ]

    def _init_cve_patterns(self) -> List[Dict]:
        """Initialize known CVE patterns for similarity matching"""
        return [
            {
                'cve': 'CVE-2021-3156 (sudo heap overflow)',
                'pattern': r'sudo.*heap|nss_load_library.*heap',
                'similarity_threshold': 0.8
            },
            {
                'cve': 'CVE-2019-14287 (sudo bypass)',
                'pattern': r'sudo.*uid.*-1',
                'similarity_threshold': 0.7
            },
            # Add more CVE patterns as you discover them
        ]

    def analyze_crash(self, crash_zip: str, crash_info: Optional[Dict] = None) -> CrashAnalysis:
        """
        Perform comprehensive crash analysis

        Args:
            crash_zip: Path to crash archive
            crash_info: Optional pre-parsed crash information

        Returns:
            CrashAnalysis object with complete analysis
        """
        self.logger.info(f"Analyzing crash: {crash_zip}")

        # Extract crash data
        data = self._extract_crash_data(crash_zip, crash_info)

        # Generate signatures
        stack_hash = self._generate_stack_hash(data['stack_frames'])
        signature = self._generate_signature(data)

        # Detect vulnerability type
        vuln_type, confidence = self._detect_vulnerability_type(data)

        # Analyze exploitability
        exploit_score, indicators = self._analyze_exploitability(data)

        # Determine severity
        severity = self._calculate_severity(vuln_type, exploit_score, indicators)

        # Detect control flow issues
        control_flow_hijack = self._detect_control_flow_hijack(data)

        # Detect memory corruption
        memory_corruption = self._detect_memory_corruption(data)

        # Check for controlled data
        controlled_data = self._detect_controlled_data(data)

        # Detect active mitigations
        mitigations = self._detect_mitigations(data)

        # Root cause analysis
        root_cause = self._analyze_root_cause(data, vuln_type)

        # Suggest fix
        suggested_fix = self._suggest_fix(vuln_type, root_cause)

        # Find similar CVEs
        similar_cves = self._find_similar_cves(data, vuln_type)

        # Generate triage notes
        triage_notes = self._generate_triage_notes(data, vuln_type, indicators)

        # Build vulnerability class
        vuln_class = self._classify_vulnerability(vuln_type, control_flow_hijack, memory_corruption)

        analysis = CrashAnalysis(
            crash_id=os.path.basename(crash_zip),
            signature=signature,
            stack_hash=stack_hash,
            severity=severity,
            exploitability_score=exploit_score,
            vuln_type=vuln_type,
            vuln_class=vuln_class,
            control_flow_hijack=control_flow_hijack,
            memory_corruption=memory_corruption,
            controlled_data=controlled_data,
            stack_frames=data['stack_frames'],
            registers=data['registers'],
            fault_address=data.get('fault_address'),
            crash_instruction=data.get('crash_instruction'),
            confidence=confidence,
            indicators=indicators,
            mitigations=mitigations,
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            similar_cves=similar_cves,
            triage_notes=triage_notes
        )

        self.logger.info(f"Analysis complete: {severity.value} severity, {exploit_score}/100 exploitability")
        return analysis

    def _extract_crash_data(self, crash_zip: str, crash_info: Optional[Dict]) -> Dict:
        """Extract and normalize crash data from zip or info dict"""
        data = {
            'stack_frames': [],
            'registers': {},
            'fault_address': None,
            'crash_instruction': None,
            'exception': '',
            'raw_output': '',
            'binary': '',
            'environment': {}
        }

        try:
            with zipfile.ZipFile(crash_zip, 'r') as zf:
                # Try GDB output first (kernel crashes)
                if 'gdb_output.txt' in zf.namelist():
                    gdb_output = zf.read('gdb_output.txt').decode(errors='ignore')
                    data['raw_output'] = gdb_output
                    data.update(self._parse_gdb_output(gdb_output))

                # Try crash_info.json (user-space crashes)
                elif 'crash_info.json' in zf.namelist():
                    info = json.loads(zf.read('crash_info.json').decode())
                    data.update(self._parse_crash_info_json(info))

                # Fallback to provided crash_info
                elif crash_info:
                    data.update(self._parse_crash_info_json(crash_info))

        except Exception as e:
            self.logger.error(f"Error extracting crash data: {e}")

        return data

    def _parse_gdb_output(self, gdb_output: str) -> Dict:
        """Parse GDB output for stack, registers, etc."""
        data = {
            'stack_frames': [],
            'registers': {},
            'exception': ''
        }

        # Extract stack frames (#0, #1, etc.)
        stack_matches = re.findall(r'#(\d+)\s+(?:0x[0-9a-fA-F]+\s+in\s+)?([^\n\(]+)', gdb_output)
        data['stack_frames'] = [frame[1].strip() for frame in stack_matches[:10]]

        # Extract registers
        reg_matches = re.findall(r'([re][abcds][xpi]|[re]bp|[re]sp|rip|eip|pc)\s*[=:]\s*(0x[0-9a-fA-F]+)', gdb_output, re.IGNORECASE)
        data['registers'] = {reg[0].lower(): reg[1] for reg in reg_matches}

        # Extract fault address
        fault_match = re.search(r'fault address\s*[=:]\s*(0x[0-9a-fA-F]+)', gdb_output, re.IGNORECASE)
        if fault_match:
            data['fault_address'] = fault_match.group(1)

        # Extract exception type
        exc_match = re.search(r'(signal\s+\w+|segmentation fault|illegal instruction|general protection)', gdb_output, re.IGNORECASE)
        if exc_match:
            data['exception'] = exc_match.group(1)

        return data

    def _parse_crash_info_json(self, crash_info: Dict) -> Dict:
        """Parse crash_info.json format"""
        return {
            'stack_frames': [str(f) for f in crash_info.get('stack', [])[:10]],
            'registers': crash_info.get('registers', {}),
            'fault_address': crash_info.get('address'),
            'exception': crash_info.get('exception', ''),
            'binary': crash_info.get('exe', ''),
            'crash_instruction': crash_info.get('instruction')
        }

    def _generate_stack_hash(self, stack_frames: List[str]) -> str:
        """
        Generate sophisticated stack hash for deduplication

        Uses normalized function names from top 5 frames
        """
        if not stack_frames:
            return hashlib.sha256(b'no_stack').hexdigest()[:16]

        # Normalize stack frames (remove addresses, keep function names)
        normalized = []
        for frame in stack_frames[:5]:
            # Extract function name, removing addresses and parameters
            func_name = re.sub(r'0x[0-9a-fA-F]+', '', frame)
            func_name = re.sub(r'\(.*\)', '', func_name)
            func_name = func_name.strip()
            if func_name:
                normalized.append(func_name)

        stack_str = '|'.join(normalized)
        return hashlib.sha256(stack_str.encode()).hexdigest()[:16]

    def _generate_signature(self, data: Dict) -> str:
        """Generate unique crash signature"""
        sig_parts = [
            data.get('exception', 'unknown'),
            data.get('fault_address', 'none'),
            '|'.join(data['stack_frames'][:3])
        ]
        sig_str = ':'.join(str(p) for p in sig_parts)
        return hashlib.sha256(sig_str.encode()).hexdigest()

    def _detect_vulnerability_type(self, data: Dict) -> Tuple[VulnType, float]:
        """
        Detect vulnerability type with confidence score

        Returns:
            (VulnType, confidence_score)
        """
        scores = {}
        raw_text = (data.get('raw_output', '') + data.get('exception', '')).lower()

        # Score each vulnerability type
        for vuln_type, patterns in self.vuln_patterns.items():
            score = 0.0
            for pattern_dict in patterns:
                if re.search(pattern_dict['pattern'], raw_text, re.IGNORECASE):
                    score += pattern_dict['weight']

                    # Check register patterns if specified
                    if 'register_patterns' in pattern_dict:
                        for reg_name, reg_val in data.get('registers', {}).items():
                            for reg_pattern in pattern_dict['register_patterns']:
                                if re.search(reg_pattern, f"{reg_name} {reg_val}"):
                                    score += 0.2

            if score > 0:
                scores[vuln_type] = min(score, 1.0)

        # Return highest scoring type
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1])
            return best_type[0], best_type[1]

        return VulnType.UNKNOWN, 0.0

    def _analyze_exploitability(self, data: Dict) -> Tuple[int, List[str]]:
        """
        Analyze exploitability and return score (0-100) and list of indicators

        Returns:
            (score, indicators_found)
        """
        score = 0
        indicators = []
        raw_text = (data.get('raw_output', '') + data.get('exception', '')).lower()

        # Check each exploitability indicator
        for indicator_dict in self.exploit_indicators:
            if re.search(indicator_dict['pattern'], raw_text, re.IGNORECASE):
                score += indicator_dict['score']
                indicators.append(indicator_dict['name'])

        # Check register control
        regs = data.get('registers', {})
        if any(reg in ['rip', 'eip', 'pc'] for reg in regs):
            pc_val = regs.get('rip') or regs.get('eip') or regs.get('pc')
            if pc_val:
                # Check for pattern-based control
                if '41414141' in pc_val or '42424242' in pc_val:
                    score += 40
                    indicators.append('Full PC Control (pattern-based)')
                elif pc_val not in ['0x0', '0x00000000', '0x0000000000000000']:
                    score += 20
                    indicators.append('PC Control (non-null)')

        # Cap at 100
        return min(score, 100), indicators

    def _calculate_severity(self, vuln_type: VulnType, exploit_score: int, indicators: List[str]) -> Severity:
        """Calculate overall severity based on multiple factors"""
        # Critical if exploit score > 70 or PC control
        if exploit_score >= 70 or any('PC Control' in ind for ind in indicators):
            return Severity.CRITICAL

        # High if exploit score > 50 or certain vuln types
        if exploit_score >= 50 or vuln_type in [VulnType.BUFFER_OVERFLOW, VulnType.ARBITRARY_WRITE]:
            return Severity.HIGH

        # Medium if exploit score > 30
        if exploit_score >= 30:
            return Severity.MEDIUM

        # Low if exploit score > 10
        if exploit_score >= 10:
            return Severity.LOW

        # Otherwise info
        return Severity.INFO

    def _detect_control_flow_hijack(self, data: Dict) -> bool:
        """Detect if crash allows control flow hijacking"""
        regs = data.get('registers', {})
        raw_text = data.get('raw_output', '').lower()

        # Check PC control
        if any(reg in ['rip', 'eip', 'pc'] for reg in regs):
            return True

        # Check return address corruption
        if 'return address' in raw_text and 'corrupt' in raw_text:
            return True

        # Check indirect call/jump corruption
        if re.search(r'call.*corrupt|jmp.*corrupt', raw_text):
            return True

        return False

    def _detect_memory_corruption(self, data: Dict) -> bool:
        """Detect memory corruption"""
        raw_text = data.get('raw_output', '').lower()

        corruption_indicators = [
            'corrupt',
            'overflow',
            'overwrite',
            'smash',
            'invalid.*size',
            'heap.*metadata',
            'use after free'
        ]

        return any(re.search(pattern, raw_text) for pattern in corruption_indicators)

    def _detect_controlled_data(self, data: Dict) -> bool:
        """Detect if attacker controls data"""
        regs = data.get('registers', {})

        # Check for pattern-based values in registers
        patterns = ['41414141', '42424242', '43434343', 'aaaaaaaa', 'bbbbbbbb']
        for reg_val in regs.values():
            if any(pattern in reg_val.lower() for pattern in patterns):
                return True

        return False

    def _detect_mitigations(self, data: Dict) -> List[str]:
        """Detect active security mitigations"""
        mitigations = []
        raw_text = data.get('raw_output', '')

        # Common mitigations
        if '__stack_chk_fail' in raw_text or 'stack canary' in raw_text.lower():
            mitigations.append('Stack Canary')

        if 'aslr' in raw_text.lower() or 'pie' in raw_text.lower():
            mitigations.append('ASLR/PIE')

        if 'dep' in raw_text.lower() or 'nx' in raw_text.lower():
            mitigations.append('DEP/NX')

        if 'cfi' in raw_text.lower() or 'control flow' in raw_text.lower():
            mitigations.append('CFI')

        return mitigations

    def _analyze_root_cause(self, data: Dict, vuln_type: VulnType) -> Optional[str]:
        """Analyze likely root cause"""
        # This is simplified - could be much more sophisticated
        if vuln_type == VulnType.BUFFER_OVERFLOW:
            if any('strcpy' in frame or 'sprintf' in frame for frame in data['stack_frames']):
                return "Unsafe string function usage (strcpy/sprintf)"

        if vuln_type == VulnType.NULL_DEREF:
            return "Null pointer dereference - missing validation"

        if vuln_type == VulnType.USE_AFTER_FREE:
            return "Use-after-free - object accessed after being freed"

        return None

    def _suggest_fix(self, vuln_type: VulnType, root_cause: Optional[str]) -> Optional[str]:
        """Suggest potential fix"""
        fixes = {
            VulnType.BUFFER_OVERFLOW: "Use bounds-checked functions (strncpy, snprintf) and validate buffer sizes",
            VulnType.NULL_DEREF: "Add null pointer checks before dereferencing",
            VulnType.USE_AFTER_FREE: "Set pointers to NULL after free, use smart pointers",
            VulnType.HEAP_OVERFLOW: "Validate allocation sizes and use safe memory functions",
            VulnType.FORMAT_STRING: "Use static format strings, never pass user data as format",
        }
        return fixes.get(vuln_type)

    def _find_similar_cves(self, data: Dict, vuln_type: VulnType) -> List[str]:
        """Find similar known CVEs"""
        similar = []
        raw_text = data.get('raw_output', '').lower()

        for cve_info in self.cve_patterns:
            if re.search(cve_info['pattern'], raw_text):
                similar.append(cve_info['cve'])

        return similar

    def _generate_triage_notes(self, data: Dict, vuln_type: VulnType, indicators: List[str]) -> List[str]:
        """Generate helpful triage notes"""
        notes = []

        notes.append(f"Vulnerability Type: {vuln_type.value}")
        notes.append(f"Exploit Indicators: {', '.join(indicators) if indicators else 'None'}")

        if data.get('fault_address'):
            notes.append(f"Fault Address: {data['fault_address']}")

        if data['stack_frames']:
            notes.append(f"Top Function: {data['stack_frames'][0]}")

        return notes

    def _classify_vulnerability(self, vuln_type: VulnType, control_flow: bool, memory_corrupt: bool) -> str:
        """Classify vulnerability into broader category"""
        if control_flow:
            return "Control Flow Hijack"
        elif memory_corrupt:
            return "Memory Corruption"
        elif vuln_type in [VulnType.NULL_DEREF]:
            return "Memory Safety"
        else:
            return "Other"
