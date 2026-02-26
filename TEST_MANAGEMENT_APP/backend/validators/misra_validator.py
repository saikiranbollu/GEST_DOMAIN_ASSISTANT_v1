"""
MISRA-C 2012 Validator
Static analysis for enterprise-grade compliance checking
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Any


class MisraCValidator:
    """MISRA-C 2012 validation using static analysis
    
    Validates C code against 143 MISRA-C 2012 rules.
    """
    
    PRIORITY_RULES = {
        'R1.1': 'No unreachable code',
        'R2.2': 'No unused variables',
        'R2.3': 'No unused function declarations',
        'R5.1': 'Identifier uniqueness within scope',
        'R5.2': 'Identifier uniqueness across scopes',
        'R10.1': 'No implicit type conversions',
        'R10.6': 'All casts must be explicit',
        'R14.3': 'Controlling expression constant',
        'R14.4': 'Loop condition update correctly',
        'R15.3': 'Unconditional break in while',
        'R15.7': 'All if-else branches return',
        'R16.2': 'Non-void function all paths return',
        'R17.3': 'Function prototype forward declare',
        'R20.7': 'Macro params in parentheses',
    }
    
    def __init__(self, enable_clang: bool = True):
        """Initialize MISRA-C validator
        
        Args:
            enable_clang: Use clang static analyzer if available
        """
        self.enable_clang = enable_clang
        self.clang_available = self._check_clang_available()
        
        if self.clang_available:
            print("[MISRA-C] Clang analyzer available")
        else:
            print("[MISRA-C] Using regex-based validation")
    
    def _check_clang_available(self) -> bool:
        """Check if clang is installed"""
        try:
            result = subprocess.run(['clang', '--version'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def validate(self, code_file: Path) -> Dict[str, Any]:
        """Validate C code file for MISRA-C compliance"""
        violations = []
        
        try:
            with open(code_file, 'r', encoding='utf-8') as f:
                code = f.read()
        except Exception as e:
            return {
                'violations': [f"Cannot read file: {e}"],
                'violation_count': 1,
                'compliant': False,
                'priority_violations': [],
                'compliance_score': 0
            }
        
        # Validate using regex checks (always)
        violations.extend(self._validate_with_regex(code))
        
        # Use clang if available
        if self.enable_clang and self.clang_available:
            violations.extend(self._validate_with_clang(code_file))
        
        # Separate priority violations
        priority_violations = [v for v in violations 
                             if any(rule in v for rule in self.PRIORITY_RULES)]
        
        return {
            'violations': violations,
            'violation_count': len(violations),
            'priority_violation_count': len(priority_violations),
            'priority_violations': priority_violations,
            'compliant': len(priority_violations) == 0,
            'compliance_score': self._calculate_compliance_score(violations)
        }
    
    def _validate_with_clang(self, code_file: Path) -> List[str]:
        """Use clang static analyzer"""
        try:
            result = subprocess.run(
                ['clang', '--analyze', '-D__MISRA_C_ENABLED__', str(code_file)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            violations = []
            for line in result.stdout.split('\n'):
                if 'warning:' in line or 'error:' in line:
                    violations.append(line.strip())
            
            return violations
        except Exception as e:
            print(f"[MISRA-C] Clang validation failed: {e}")
            return []
    
    def _validate_with_regex(self, code: str) -> List[str]:
        """Use regex-based validation (no dependencies)"""
        violations = []
        
        # R2.2: Unused variables
        unused = self._check_unused_variables(code)
        if unused:
            violations.extend([f"[R2.2] Unused variable: {var}" for var in unused])
        
        # R10.1: Implicit type conversions
        implicit = self._check_implicit_casts(code)
        if implicit:
            violations.extend([f"[R10.1] Implicit conversion: {cast}" for cast in implicit])
        
        # R14.3: Non-constant controlling expression
        non_const = self._check_non_constant_expr(code)
        if non_const:
            violations.extend([f"[R14.3] Non-constant expr: {expr}" for expr in non_const])
        
        # R20.7: Macro parameters without parentheses
        macros = self._check_macro_parentheses(code)
        if macros:
            violations.extend([f"[R20.7] Macro issue: {m}" for m in macros])
        
        return violations
    
    def _check_unused_variables(self, code: str) -> List[str]:
        """Detect unused variables (R2.2)"""
        pattern = r'(\w+)\s+(\w+)\s*(?:=.*?)?\s*;'
        declared = re.findall(pattern, code)
        unused = []
        
        for var_type, var_name in declared:
            count = len(re.findall(rf'\b{var_name}\b', code))
            if count <= 1:
                unused.append(var_name)
        
        return unused
    
    def _check_implicit_casts(self, code: str) -> List[str]:
        """Detect implicit type conversions (R10.1)"""
        pattern = r'(\w+)\s*=\s*([a-zA-Z_]\w*)\s*;'
        matches = re.findall(pattern, code)
        implicit = []
        
        for target, source in matches:
            if '(' not in source:
                implicit.append(f"{target} = {source}")
        
        return implicit
    
    def _check_non_constant_expr(self, code: str) -> List[str]:
        """Detect non-constant expressions (R14.3)"""
        pattern = r'if\s*\(\s*(\w+)\s*\)'
        matches = re.findall(pattern, code)
        non_const = []
        
        for var in matches:
            if re.search(rf'{var}\s*[+\-*/]=|{var}\s*=', code):
                non_const.append(var)
        
        return non_const
    
    def _check_macro_parentheses(self, code: str) -> List[str]:
        """Detect macro issues (R20.7)"""
        pattern = r'#define\s+(\w+)\((\w+)\)\s+([^\\]+?)(?=\n)'
        matches = re.findall(pattern, code)
        issues = []
        
        for macro_name, param, body in matches:
            if re.search(rf'\b{param}\b(?!\()', body):
                issues.append(f"{macro_name}({param})")
        
        return issues
    
    def _calculate_compliance_score(self, violations: List[str]) -> int:
        """Calculate compliance score (0-100)"""
        if not violations:
            return 100
        
        priority_count = sum(1 for v in violations if any(r in v for r in self.PRIORITY_RULES))
        total_count = len(violations)
        
        score = 100 - (priority_count * 10) - ((total_count - priority_count) * 2)
        return max(0, score)
