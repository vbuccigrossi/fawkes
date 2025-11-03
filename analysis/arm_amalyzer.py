from fawkes.analysis.base import CrashAnalyzer
import zipfile
import hashlib
import json
import re
import os

class ARMAnalyzer(CrashAnalyzer):
    def get_signature(self, crash_zip: str) -> str:
        """Generate a precise crash signature for ARM."""
        try:
            with zipfile.ZipFile(crash_zip, "r") as zf:
                if "gdb_output.txt" in zf.namelist():
                    gdb_output = zf.read("gdb_output.txt").decode(errors="ignore")
                    # Extract key elements: fault type, function names, instruction
                    fault_type = "unknown"
                    call_stack = []
                    faulting_inst = "none"
                    
                    # Common GDB patterns for ARM
                    if "undefined instruction" in gdb_output.lower():
                        fault_type = "undefined_instruction"
                    elif "data abort" in gdb_output.lower():
                        fault_type = "data_abort"
                    elif "prefetch abort" in gdb_output.lower():
                        fault_type = "prefetch_abort"
                    
                    # Extract call stack (e.g., #0 func1, #1 func2)
                    stack_matches = re.findall(r"#\d+\s+(\w+)\s*\(", gdb_output)
                    call_stack = stack_matches[:5]  # Limit to top 5 frames
                    
                    # Extract faulting instruction or PC
                    pc_match = re.search(r"PC\s*=\s*0x[0-9a-fA-F]+", gdb_output)
                    if pc_match:
                        faulting_inst = "pc_set"
                    
                    # Combine for signature
                    sig_parts = [fault_type] + call_stack + [faulting_inst]
                    sig_str = ":".join(sig_parts)
                    self.logger.debug(f"Kernel crash signature: {sig_str}")
                    return hashlib.sha256(sig_str.encode()).hexdigest()
                
                elif "crash_info.json" in zf.namelist():
                    crash_info = json.loads(zf.read("crash_info.json").decode(errors="ignore"))
                    # Use exe, exception, top stack frames, faulting address
                    exe = crash_info.get("exe", "unknown")
                    exception = crash_info.get("exception", "unknown").lower()
                    stack = crash_info.get("stack", [])[:3]  # Top 3 frames
                    address = crash_info.get("address", "none")
                    
                    # Normalize stack to function names or module+offset
                    stack_str = ":".join(str(frame.get("function", "unknown")) for frame in stack)
                    sig_parts = [exe, exception, stack_str, address]
                    sig_str = ":".join(sig_parts)
                    self.logger.debug(f"User-space crash signature: {sig_str}")
                    return hashlib.sha256(sig_str.encode()).hexdigest()
                
                elif "crash.log" in zf.namelist():
                    # Fallback for crash.log
                    crash_log = zf.read("crash.log").decode(errors="ignore")
                    sig_str = crash_log[:100]  # First 100 chars as heuristic
                    self.logger.debug(f"Fallback crash.log signature: {sig_str}")
                    return hashlib.sha256(sig_str.encode()).hexdigest()
        
        except Exception as e:
            self.logger.error(f"Failed to generate signature for {crash_zip}: {e}")
        
        # Ultimate fallback: hash file content
        self.logger.warning(f"No valid signature data in {crash_zip}, using file hash")
        with open(crash_zip, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def rank_exploitability(self, crash_zip: str) -> str:
        """Rank exploitability with detailed analysis for ARM crashes."""
        try:
            with zipfile.ZipFile(crash_zip, "r") as zf:
                if "gdb_output.txt" in zf.namelist():
                    gdb_output = zf.read("gdb_output.txt").decode(errors="ignore").lower()
                    analysis = []
                    
                    # Check for control flow issues
                    if "pc" in gdb_output:
                        analysis.append("PC corruption detected")
                        if "0x00000000" in gdb_output or "0x41414141" in gdb_output:
                            analysis.append("Null or pattern-based PC")
                            return self._finalize_rank(crash_zip, "High", analysis)
                        return self._finalize_rank(crash_zip, "High", analysis)
                    
                    # Instruction issues
                    if "undefined instruction" in gdb_output:
                        analysis.append("Undefined instruction executed")
                        return self._finalize_rank(crash_zip, "Medium", analysis)
                    
                    # Memory faults
                    if "data abort" in gdb_output:
                        analysis.append("Data abort")
                        if "sp" in gdb_output or "lr" in gdb_output:
                            analysis.append("Possible stack corruption")
                            return self._finalize_rank(crash_zip, "Medium", analysis)
                        return self._finalize_rank(crash_zip, "Low", analysis)
                    
                    if "prefetch abort" in gdb_output:
                        analysis.append("Prefetch abort")
                        return self._finalize_rank(crash_zip, "Low", analysis)
                    
                    # Generic kernel crash
                    analysis.append("Generic kernel crash")
                    return self._finalize_rank(crash_zip, "Low", analysis)
                
                elif "crash_info.json" in zf.namelist():
                    crash_info = json.loads(zf.read("crash_info.json").decode(errors="ignore"))
                    exception = crash_info.get("exception", "unknown").lower()
                    address = crash_info.get("address", "unknown")
                    stack = crash_info.get("stack", [])
                    analysis = []
                    
                    # Access violations (ARM equivalent: data abort)
                    if "data abort" in exception:
                        analysis.append(f"Data abort at {address}")
                        if "write" in exception:
                            analysis.append("Write abort, potential overwrite")
                            return self._finalize_rank(crash_zip, "High", analysis)
                        elif "execute" in exception:
                            analysis.append("Execute abort, potential code exec")
                            return self._finalize_rank(crash_zip, "High", analysis)
                        analysis.append("Read abort, likely less exploitable")
                        return self._finalize_rank(crash_zip, "Medium", analysis)
                    
                    # Buffer overflow
                    if "buffer overflow" in exception:
                        analysis.append("Buffer overflow detected")
                        if any("stack" in str(frame).lower() for frame in stack):
                            analysis.append("Stack-based overflow")
                            return self._finalize_rank(crash_zip, "High", analysis)
                        return self._finalize_rank(crash_zip, "Medium", analysis)
                    
                    # Other exceptions
                    if "null pointer" in exception:
                        analysis.append("Null pointer dereference")
                        return self._finalize_rank(crash_zip, "Low", analysis)
                    
                    # Generic user-space crash
                    analysis.append("Generic user-space crash")
                    return self._finalize_rank(crash_zip, "Low", analysis)
        
        except Exception as e:
            self.logger.error(f"Failed to rank exploitability for {crash_zip}: {e}")
        
        return self._finalize_rank(crash_zip, "Unknown", ["No analysis possible"])

    def _finalize_rank(self, crash_zip: str, rank: str, analysis: list) -> str:
        """Log analysis and save summary with unique crash."""
        base_name = os.path.basename(crash_zip).replace(".zip", "")
        summary_file = os.path.join(self.unique_dir, f"{base_name}_analysis.txt")
        summary_content = (
            f"Crash: {crash_zip}\n"
            f"Exploitability: {rank}\n"
            f"Analysis:\n" + "\n".join(f"- {item}" for item in analysis) + "\n"
            f"Next Steps:\n"
        )
        
        if rank == "High":
            summary_content += "- Inspect registers and stack in gdb_output.txt or crash_info.json.\n"
            summary_content += "- Check for controlled pointers or code execution.\n"
        elif rank == "Medium":
            summary_content += "- Review faulting address and stack trace.\n"
            summary_content += "- Look for partial control or data corruption.\n"
        else:
            summary_content += "- Verify crash reproducibility.\n"
            summary_content += "- Check for environmental factors.\n"
        
        try:
            with open(summary_file, "w") as f:
                f.write(summary_content)
            self.logger.info(f"Saved crash analysis to {summary_file}")
        except Exception as e:
            self.logger.error(f"Failed to save analysis to {summary_file}: {e}")
        
        self.logger.info(f"Crash {crash_zip} ranked {rank}: {'; '.join(analysis)}")
        return rank
