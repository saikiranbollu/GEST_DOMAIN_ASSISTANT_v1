#!/usr/bin/env python3
"""
LLM Integration Module - PHASE 4
Support for GitHub Copilot and other models via VS Code LLM API

Providers:
1. GitHub Copilot (Claude 3.5 Sonnet, GPT-4, etc.)
2. Fallback to local models if needed
"""

from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import json
import subprocess
import sys
import os
from pathlib import Path


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate text from prompt with optional context"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available"""
        pass


class GitHubCopilotProvider(LLMProvider):
    """
    GitHub Copilot provider via VS Code LLM API
    
    Uses GitHub Copilot through VS Code's language model API.
    Supports user selection of available models.
    """
    
    def __init__(self, model: Optional[str] = None):
        """
        Initialize Copilot provider
        
        Args:
            model: Model identifier (e.g., 'claude-3.5-sonnet', 'gpt-4')
                   If None, will use first available from user's environment
        """
        self.model = model
        self.available_models = self._discover_models()
        
        # If no models discovered yet, that's OK - they can be set later via VS Code API
        if not self.available_models:
            print(f"[LLM] WARNING: No models discovered from environment or VS Code config")
            print(f"      Set GITHUB_COPILOT_MODELS or VSCODE_LLM_MODELS environment variable")
            print(f"      Example: export GITHUB_COPILOT_MODELS='claude-3.5-sonnet,gpt-4'")
            self.available_models = []  # Will be populated dynamically via API
        
        if model and self.available_models and model not in self.available_models:
            raise ValueError(
                f"Model '{model}' not in available models. "
                f"Available: {self.available_models}"
            )
        
        # Use provided model or first available (if any)
        if self.available_models:
            self.model = model or self.available_models[0]
            print(f"[LLM] Using model: {self.model}")
        else:
            self.model = model
            print(f"[LLM] Model selection deferred - will use API to discover models")
    
    def _discover_models(self) -> List[str]:
        """
        Discover available GitHub Copilot models via VS Code API
        
        Zero hardcoding - only returns models user actually has access to.
        
        Returns:
            List of available model identifiers from user's VS Code environment
        """
        models = []
        
        # Check for GitHub Copilot models from environment
        if os.getenv("GITHUB_COPILOT_MODELS"):
            models = os.getenv("GITHUB_COPILOT_MODELS", "").split(",")
            models = [m.strip() for m in models if m.strip()]
            if models:
                print(f"[LLM] Discovered {len(models)} models from GITHUB_COPILOT_MODELS")
                print(f"      Available: {models}")
                return models
        
        # Try to query VS Code LLM API via environment
        vscode_llm_models = os.getenv("VSCODE_LLM_MODELS")
        if vscode_llm_models:
            models = vscode_llm_models.split(",")
            models = [m.strip() for m in models if m.strip()]
            if models:
                print(f"[LLM] Discovered {len(models)} models from VSCODE_LLM_MODELS")
                print(f"      Available: {models}")
                return models
        
        # Try to read from VS Code settings/config file
        try:
            vscode_settings_path = Path.home() / ".vscode" / "settings.json"
            if vscode_settings_path.exists():
                with open(vscode_settings_path, 'r') as f:
                    settings = json.load(f)
                    if 'github.copilot.models' in settings:
                        models = settings['github.copilot.models']
                        if isinstance(models, list):
                            models = [m.strip() for m in models if m.strip()]
                            if models:
                                print(f"[LLM] Discovered {len(models)} models from VS Code settings")
                                print(f"      Available: {models}")
                                return models
        except Exception as e:
            print(f"[LLM] Could not read VS Code settings: {e}")
        
        # No models found from any source
        print(f"[LLM] WARNING: No models discovered from environment or VS Code config")
        print(f"      Set GITHUB_COPILOT_MODELS or VSCODE_LLM_MODELS environment variable")
        print(f"      Example: export GITHUB_COPILOT_MODELS='claude-3.5-sonnet,gpt-4'")
        return []
    
    def is_available(self) -> bool:
        """Check if Copilot is available"""
        return len(self.available_models) > 0
    
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate text using GitHub Copilot
        
        Args:
            prompt: Main prompt/request
            context: Optional context dict with:
                - test_intent: What the test should do
                - function_signature: Function to test
                - imports: Required imports
                - setup_code: Initialization code
                - test_data: Test data structures
        
        Returns:
            Generated test code
        """
        # Build enhanced prompt with context
        full_prompt = self._build_prompt(prompt, context)
        
        print(f"[LLM] Generating with {self.model}...")
        
        # Call Copilot API
        try:
            response = self._call_copilot(full_prompt)
            return response
        except Exception as e:
            print(f"[LLM] Error calling Copilot: {e}")
            raise
    
    def _build_prompt(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """
        Build enhanced prompt with RAG/KG context
        
        Args:
            prompt: Base prompt
            context: Additional context from RAG/KG
        
        Returns:
            Enhanced prompt string
        """
        if not context:
            return prompt
        
        # Build structured prompt with context sections
        sections = [f"Task: {prompt}\n"]
        
        # Add RAG context
        if 'rag_functions' in context and context['rag_functions']:
            rag_funcs = context['rag_functions']
            if isinstance(rag_funcs, (list, tuple)) and len(rag_funcs) > 0:
                sections.append("\nRelevant Functions:")
                for func in rag_funcs[:5]:  # Top 5
                    if isinstance(func, dict):
                        content = func.get('content', '')
                        similarity = func.get('similarity', 0)
                        sections.append(f"  - {content[:100]}... (similarity: {similarity:.2f})")
        
        if 'rag_structs' in context and context['rag_structs']:
            rag_structs = context['rag_structs']
            if isinstance(rag_structs, (list, tuple)) and len(rag_structs) > 0:
                sections.append("\nRelevant Data Structures:")
                for struct in rag_structs[:3]:
                    if isinstance(struct, dict):
                        content = struct.get('content', '')
                        sections.append(f"  - {content[:80]}...")
        
        if 'rag_requirements' in context and context['rag_requirements']:
            rag_reqs = context['rag_requirements']
            if isinstance(rag_reqs, (list, tuple)) and len(rag_reqs) > 0:
                sections.append("\nRelevant Requirements:")
                for req in rag_reqs[:3]:
                    if isinstance(req, dict):
                        content = req.get('content', '')
                        sections.append(f"  - {content[:80]}...")
        
        # Add KG context
        if 'kg_dependencies' in context and context['kg_dependencies']:
            kg_deps = context['kg_dependencies']
            if isinstance(kg_deps, (list, tuple)) and len(kg_deps) > 0:
                sections.append("\nFunction Dependencies:")
                for dep in kg_deps[:5]:
                    if isinstance(dep, dict):
                        sections.append(f"  - {dep.get('name', 'unknown')}")
        
        # Add generation result context
        if 'generation_result' in context:
            gen = context['generation_result']
            if isinstance(gen, dict):
                if 'function_sequence' in gen:
                    func_seq = gen['function_sequence']
                    if isinstance(func_seq, (list, tuple)) and len(func_seq) > 0:
                        sections.append(f"\nFunction Sequence ({len(func_seq)} calls):")
                        for func in func_seq[:10]:
                            sections.append(f"  - {func}")
                
                if 'struct_initializations' in gen:
                    struct_inits = gen['struct_initializations']
                    if isinstance(struct_inits, (list, tuple)) and len(struct_inits) > 0:
                        sections.append(f"\nStruct Initializations ({len(struct_inits)} total):")
                        for struct_init in struct_inits[:3]:
                            if isinstance(struct_init, dict):
                                sections.append(f"  - {struct_init.get('name', 'unknown')}")
        
        # Add struct initialization instructions
        sections.append("\n\nPHASE 6: STRUCT INITIALIZATION PATTERNS")
        sections.append("=" * 40)
        sections.append("Generated code must follow this pattern (from real test code):")
        sections.append("")
        sections.append("// GLOBAL SCOPE: Only declarations, NO initialization values")
        sections.append("static StructType structVar;")
        sections.append("")
        sections.append("int main(void) {")
        sections.append("    // INSIDE main(): Three-step initialization")
        sections.append("")
        sections.append("    // STEP 1: Call init function to set defaults")
        sections.append("    initFunction(&structVar, &parentVar);")
        sections.append('    printf("Initialization: struct configured\\\\n");')
        sections.append("")
        sections.append("    // STEP 2: Assign member values AFTER init function call")
        sections.append("    structVar.member1 = value1;")
        sections.append("    structVar.member2 = value2;")
        sections.append("")
        sections.append("    // STEP 3: Use the initialized struct in function calls")
        sections.append("    someFunction(&structVar);")
        sections.append("}")
        sections.append("")
        sections.append("CRITICAL STRUCT INITIALIZATION RULES:")
        sections.append("- Struct declarations are ALWAYS in global scope (NO = {...} initialization)")
        sections.append("- Member value assignments MUST be INSIDE main() function")
        sections.append("- Init function call MUST come BEFORE member assignments")
        sections.append("- Use actual enum values from the module definitions")
        sections.append("- Add printf() between initialization steps for debugging")
        sections.append("- Member values should be derived from: user intent > hw_spec > defaults")
        
        # Add formula verification instructions ONLY if hw_spec_chunks exist
        if 'hw_spec_chunks' in context and context['hw_spec_chunks']:
            sections.append("\n\nPHASE 7: FORMULA VERIFICATION (IF APPLICABLE)")
            sections.append("=" * 40)
            sections.append("IF the hardware specification contains mathematical formulas:")
            sections.append("")
            sections.append("1. IDENTIFY: Look for patterns like:")
            sections.append("   - 'Error = (Desired - Current) * 100 / Desired'")
            sections.append("   - 'Timeout = FrameLength / Baudrate'")
            sections.append("   - 'Temperature = Measured + Offset'")
            sections.append("   - Constraints like: 'Tolerance ±5%', 'must be < 50ms'")
            sections.append("")
            sections.append("2. EXTRACT: Formula name, expression, and constraint")
            sections.append("")
            sections.append("3. IMPLEMENT: Generate C code that:")
            sections.append("   a) Gets actual hardware value via appropriate API call")
            sections.append("   b) Applies formula using proper C syntax and type casts")
            sections.append("   c) Validates against constraint (if/else check)")
            sections.append("   d) Provides clear printf output showing value and result")
            sections.append("")
            sections.append("4. EXAMPLE:")
            sections.append("   // Formula from hw_spec: Baudrate Error = (Desired - Current) * 100 / Desired")
            sections.append("   // Constraint: Tolerance ±5%")
            sections.append("   printf(\"Verifying baudrate error...\\\\n\");")
            sections.append("   uint32_t actual_rate = getHardwareBaudrate(&channel);")
            sections.append("   int32_t error_percent = ((int32_t)DESIRED_RATE - (int32_t)actual_rate) * 100 / (int32_t)DESIRED_RATE;")
            sections.append("   printf(\"Error: %d%% (tolerance: ±5%%)\\\\n\", (int)error_percent);")
            sections.append("   if (error_percent < -5 || error_percent > 5) {")
            sections.append("       printf(\"FAILED: Tolerance exceeded\\\\n\");")
            sections.append("       return ERROR_CODE;")
            sections.append("   }")
            sections.append("")
            sections.append("FORMULA VERIFICATION RULES (if applicable):")
            sections.append("- Extract formula ONLY if explicitly present in hw_spec")
            sections.append("- Convert mathematical notation to C expressions (× to *, ÷ to /, etc.)")
            sections.append("- Add type casts (int32_t, uint32_t) to prevent integer overflow")
            sections.append("- Implement constraint validation (if tolerance exceeded, return error)")
            sections.append("- Include printfs before/after calculation for traceability")
            sections.append("- Return appropriate error code on constraint violation")
        
        # Add general instructions
        sections.append("\n\nGENERAL INSTRUCTIONS:")
        sections.append("1. Write MISRA-C compliant test code")
        sections.append("2. Include proper error handling")
        sections.append("3. Add comments explaining the test")
        sections.append("4. Use the provided function signatures")
        sections.append("5. Ensure proper resource cleanup")
        
        return "\n".join(sections)
    
    def _call_copilot(self, prompt: str) -> str:
        """
        Call GitHub Copilot API
        
        Args:
            prompt: Full prompt with context
        
        Returns:
            Generated text
        """
        # Try to use Python requests to call Copilot API
        try:
            import requests
        except ImportError:
            print("[LLM] requests library not available, using mock response")
            return self._generate_mock_response(prompt)
        
        # Construct API call to Copilot
        # Note: Actual endpoint depends on VS Code extension setup
        # This is a placeholder that respects user's available models
        
        try:
            # Try to get Copilot token from environment or VS Code
            token = os.getenv("GITHUB_COPILOT_TOKEN")
            if not token:
                print("[LLM] No GitHub Copilot token found, using mock response")
                return self._generate_mock_response(prompt)
            
            # Call Copilot API endpoint
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "max_tokens": 15000,
                "temperature": 0.3
            }
            
            # Actual endpoint would be GitHub Copilot API
            # This is a simplified example
            response = requests.post(
                "https://api.github.com/copilot/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('text', data.get('content', ''))
            else:
                print(f"[LLM] API error {response.status_code}, using mock response")
                return self._generate_mock_response(prompt)
        
        except Exception as e:
            print(f"[LLM] Exception calling Copilot API: {e}")
            print("[LLM] Falling back to mock response")
            return self._generate_mock_response(prompt)
    
    def _generate_mock_response(self, prompt: str) -> str:
        """
        Generate mock test code response (for testing without Copilot)
        
        Args:
            prompt: The prompt
        
        Returns:
            Mock test code
        """
        mock_code = '''
// Generated test code (mock response - Copilot API not available)
// To enable real generation: set GITHUB_COPILOT_TOKEN environment variable

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>

uint8_t run_test(void)
{
    printf("\\n $ Mock test — Copilot API not connected $\\n");
    // TODO: Connect GitHub Copilot (set GITHUB_COPILOT_TOKEN) for real code generation
    return 0;
}
'''
        return mock_code


class LLMService:
    """
    Main LLM service managing provider selection and generation
    """
    
    def __init__(self, provider_type: str = "copilot", model: Optional[str] = None):
        """
        Initialize LLM service
        
        Args:
            provider_type: 'copilot', 'openai', 'anthropic', etc.
            model: Specific model to use (e.g., 'claude-3.5-sonnet')
        """
        self.provider_type = provider_type
        self.model = model
        self.provider = self._init_provider(provider_type, model)
    
    def _init_provider(self, provider_type: str, model: Optional[str]) -> LLMProvider:
        """Initialize the appropriate LLM provider"""
        
        if provider_type.lower() in ["copilot", "github", "github-copilot"]:
            return GitHubCopilotProvider(model=model)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
    
    def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate test code using LLM
        
        Args:
            prompt: Main prompt/request
            context: Optional context (RAG results, KG results, generation results)
        
        Returns:
            Dict with:
            - status: 'success' or 'error'
            - code: Generated code
            - model: Model used
            - tokens: Approx token count
            - error: Error message if failed
        """
        try:
            print(f"[LLM] Generating with {self.provider_type}:{self.model}")
            generated_code = self.provider.generate(prompt, context)
            
            return {
                'status': 'success',
                'code': generated_code,
                'model': self.model or 'auto-selected',
                'provider': self.provider_type,
                'tokens_estimate': len(generated_code.split()) // 4  # Rough estimate
            }
        
        except Exception as e:
            import traceback
            print(f"[LLM] Generation failed: {e}")
            print(f"[LLM] Exception type: {type(e).__name__}")
            print(f"[LLM] Traceback:")
            traceback.print_exc()
            return {
                'status': 'error',
                'code': '',
                'model': self.model or 'auto-selected',
                'provider': self.provider_type,
                'error': f"{type(e).__name__}: {str(e)}"
            }
    
    def get_available_models(self) -> List[str]:
        """Get list of available models for current provider"""
        if isinstance(self.provider, GitHubCopilotProvider):
            return self.provider.available_models
        return []
    
    def select_model(self, model: str) -> bool:
        """
        Switch to a different model
        
        Args:
            model: Model identifier
        
        Returns:
            True if successful, False otherwise
        """
        available = self.get_available_models()
        if model in available:
            self.model = model
            self.provider.model = model
            print(f"[LLM] Switched to model: {model}")
            return True
        else:
            print(f"[LLM] Model '{model}' not available. Available: {available}")
            return False


# Convenience function
def create_llm_service(model: Optional[str] = None) -> LLMService:
    """
    Create an LLM service with GitHub Copilot provider
    
    Args:
        model: Optional model name to use
    
    Returns:
        LLMService instance
    """
    return LLMService(provider_type="copilot", model=model)
