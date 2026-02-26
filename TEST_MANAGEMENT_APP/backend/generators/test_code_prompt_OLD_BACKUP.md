# DATA-DRIVEN TEST CODE GENERATION PROMPT (100% DYNAMIC - ZERO HARDCODING)

## CRITICAL MANDATE: ZERO HARDCODING OF MODULE NAMES, FUNCTION NAMES, OR ANY IDENTIFIERS

**THIS PROMPT CONTAINS ZERO HARDCODED MODULE NAMES OR FUNCTION NAMES**

---

## ⚠️ CRITICAL CONSTRAINT: PRIMARY TEST FUNCTION

**PRIMARY TEST FUNCTION (MANDATORY RULE):**
- **DO NOT CALL:** `{PRIMARY_TEST_FUNCTION}`
- **REASON:** This is the TEST TARGET that the user will implement manually
- **AUTO-GENERATE ONLY:** Setup/prerequisite functions from {FUNCTION_SEQUENCE}
- **EXCLUDE FROM GENERATED CODE:** Any function call to {PRIMARY_TEST_FUNCTION}
- **IF PRIMARY_TEST_FUNCTION IS "None identified":** Generate all functions from {FUNCTION_SEQUENCE} normally

**ENFORCEMENT:**
- ✅ Generate all setup/config/prerequisite functions
- ❌ **NEVER** call {PRIMARY_TEST_FUNCTION} in [SEQUENCE] phase or any other phase
- ❌ **NEVER** include function call or assignment involving {PRIMARY_TEST_FUNCTION}
- ✅ User will implement the actual test of {PRIMARY_TEST_FUNCTION} separately
- **ZERO TOLERANCE:** This constraint is non-negotiable

---

## CRITICAL INSTRUCTIONS (READ CAREFULLY)

**NO HARDCODING RULE - ABSOLUTE**: This prompt is FULLY DATA-DRIVEN. Use ONLY the provided data placeholders. Do NOT:
- Hardcode ANY module names, function names, or struct names
- Use specific enum values not provided in {AVAILABLE_ENUMS}
- Invent struct members, variables, or macro names
- Add functionality-specific logic
- Make assumptions about channel IDs, buffer sizes, or configuration values
- Create custom patterns or custom busy-wait logic
- Include ANY examples with actual module/function names

---

## **CRITICAL ENFORCEMENT: TWO MANDATORY RULES (ZERO FAILURES)**

### **MANDATE #1: ForTest Function Variants (If test_mode=true)**
If {FEATURE_CLASSIFICATION} contains `test_mode: True` or `test_mode: true`:
- **EVERY initialization function MUST use ForTest variant**
- Scan {AVAILABLE_FUNCTIONS} for all function variants
- Detect patterns: For each function, search for ForTest or ForErrorCtl suffix variants
- If ForTest variant exists for a function, MUST use it instead of standard variant
- Build mapping dynamically: analyze function names to identify base name and variant suffix
- Replace ALL standard variants with ForTest variants throughout generated code
- Apply pattern detection to ALL functions, not just init functions
- **FAIL IF**: Any standard variant remains when ForTest variant exists
- **ZERO EXCEPTIONS**: 100% ForTest variant compliance required

### **MANDATE #2: Struct Member Initialization (IMMEDIATE & COMPLETE)**
IMMEDIATELY AFTER EVERY struct init function call:
- Initialize EVERY struct member explicitly in code
- Do NOT skip any member
- Do NOT use comments instead of code
- Do NOT rely on init functions to set members
- **FAIL IF**: Any member left uninitialized after init call
- **ZERO EXCEPTIONS**: 100% member initialization required

---

## ⚡ TWO-STAGE LLM PIPELINE: YOUR ROLE (STAGE 2 - CODE ENHANCEMENT)

**CRITICAL UNDERSTANDING**: You are receiving skeleton code that has ALREADY been processed by Stage 1 (enum resolution).

### What Happened Before You (Stage 1):
1. Backend generated skeleton code with enum TODOs: `/* TODO: CHOOSE_FROM_ABOVE */` and `/* ENUM_PARAM: Select from [...] */`
2. A small specialized model (`gpt-5-mini`) analyzed the test context and resolved ALL enum placeholders
3. The backend substituted the resolved enum values into the skeleton
4. **YOU NOW RECEIVE A SKELETON WITH ENUMS ALREADY RESOLVED**

### Your Job (Stage 2):
**DO NOT re-resolve enums**. The enum values in the skeleton you receive are CORRECT and context-appropriate.

**Your tasks**:
1. ✅ Keep ALL enum values exactly as provided in the skeleton
2. ✅ Enhance code quality (add comments, improve clarity)
3. ✅ Add printf debug statements for phases: `[INIT]`, `[CONFIG]`, `[SEQUENCE]`, `[BUSY-WAIT]`, `[ERROR]`, `[VALIDATION]`, `[FINALIZE]`
4. ✅ Ensure all struct members are initialized (skeleton should have this, verify completeness)
5. ✅ Maintain the exact code structure, function call order, and busy-wait patterns from the skeleton
6. ❌ **DO NOT** change any enum values already assigned in the skeleton
7. ❌ **DO NOT** change function call order or placement
8. ❌ **DO NOT** add pollCount, timeout counters, or modify while-loop structures (see FORBIDDEN PATTERNS)

### If You See Leftover TODOs (Fallback Only):
**This should be rare** — it means Stage 1 failed for that specific enum. In this case ONLY:
- Analyze the comment above the TODO showing available enum options
- Select the most appropriate value based on {FUNCTIONALITY} and {USER_ADDITIONAL_NOTES}
- Replace the TODO with the chosen enum value
- **NEVER use numeric values (0, 1, 2) — always use the actual enum name**

### Enum Value Rules (Applicable to Any Remaining TODOs):
```c
// ✅ CORRECT:
{config_var}.{member} = {ENUM_VALUE_FROM_LIST};  // Actual enum name from available options

// ❌ FORBIDDEN:
{config_var}.{member} = 0;  // ❌ Numeric value instead of enum
{config_var}.{member} = 1;  // ❌ Numeric value instead of enum
```

---

**ALL CODE MUST BE DRIVEN PURELY BY DATA PLACEHOLDERS**:
- {MODULE_NAME} - module name
- {FUNCTIONALITY} - test functionality description  
- {FEATURE_CLASSIFICATION} - test_mode and error_injection flags
- {FUNCTION_SEQUENCE} - ordered function calls from PUML
- {AVAILABLE_FUNCTIONS} - complete function signatures
- {AVAILABLE_STRUCTS} - complete struct definitions with members
- {AVAILABLE_ENUMS} - enum value definitions
- {CONFIG_INITIALIZATION_DETAILS} - initial values for struct members
- {EXTENDED_CONFIG_REQUIRED} - yes/no flag for extended config
- {LOOP_PATTERNS} - polling patterns (busy_wait_tx_rx, error_polling, etc.)
- {CHANNEL_INSTANTIATION_PATTERNS} - channel variable naming rules

---

## OUTPUT FILE NAMING CONVENTION (FULLY DYNAMIC)

All generated test code files are saved automatically with this naming convention:
```
OUTPUT_FOLDER/{MODULE_NAME_lowercase}/{FUNCTIONALITY_normalized}_{YYYY}_{MM}_{DD}.c
```

Where:
- `{MODULE_NAME_lowercase}`: Lowercase version of {MODULE_NAME}
- `{FUNCTIONALITY_normalized}`: Underscored, lowercase version of {FUNCTIONALITY}
- `{YYYY}_{MM}_{DD}`: Current generation date

This convention applies universally to ANY module and ANY functionality without modification or hardcoding.

---

## PURPOSE (UNIVERSAL FOR ANY MODULE)

Generate production-grade, hardware-compliant C test code for **ANY module and ANY functionality** using ONLY the provided data-driven inputs. The code must be:
- **100% Data-Driven**: No hardcoded module names, function names, struct names, or logic
- **Fully Dynamic**: Adapt completely to provided PUML sequence, functions, structs, and enums
- **Universally Scalable**: Work identically for any module and any functionality
- **Robust & Maintainable**: Follow strict engineering practices for production integration
- **Traceable**: Every step tied to PUML, SW JSON, or provided analysis data

---

## UNIVERSAL DATA-DRIVEN CODE STRUCTURE (ADAPTIVE)

The generated code adapts its structure based on {FEATURE_CLASSIFICATION} and {EXTENDED_CONFIG_REQUIRED}:

### Code Sections (Dynamic Ordering & Inclusion)

**Section A: Includes & Comments**
```c
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
// DYNAMIC: Extract module header name from {AVAILABLE_FUNCTIONS}
// Analyze function name prefixes to derive header name
// DO NOT hardcode header names
#include "[DERIVED_MODULE_HEADER_FROM_FUNCTION_PREFIX]"
```

**Section B: Module Globals (Dynamic Variables)**

For each global/static variable needed:
- Extract variable types and names from {FUNCTION_SEQUENCE} parameter analysis
- Extract struct types from {AVAILABLE_STRUCTS}
- Extract buffer sizes from {CONFIG_INITIALIZATION_DETAILS}
- Initialize all to safe values: 0 for numeric, {0} for arrays, NULL for pointers
- DO NOT add hardcoded names, IDs, or sizes

**Section C: Enums/Macros/Typedefs (Direct from Data)**
- List ALL enum values from {AVAILABLE_ENUMS} as comments (for reference)
- DO NOT add comments that don't come from provided enums
- Use only enum names that appear in {AVAILABLE_ENUMS}

**Section D: run_test Function (PUML-Driven)**

Follow this flow **EXACTLY as detected in {FUNCTION_SEQUENCE}**:

1. **[INIT Phase]** - Print "[INIT] Starting initialization"
   - Initialize all global variables if needed
   - Call all module initialization functions in dependency order

2. **[CONFIG Phase]** - Print "[CONFIG] Configuring module and extended settings"
   - For each CONFIG function from PUML:
     - Call init function with dynamic struct names
     - **IMMEDIATELY AFTER each init call**: Explicitly initialize ALL struct members
     - Use ONLY enum values from {AVAILABLE_ENUMS}
     - Print each member assignment
   - If {EXTENDED_CONFIG_REQUIRED} = "yes": Declare, initialize, and assign extended config struct

3. **[SEQUENCE Phase]** - Print "[SEQUENCE] Executing PUML-defined function sequence"
   - For each function call in {FUNCTION_SEQUENCE}:
     - Extract exact function name and parameters
     - Call function with EXACT parameters from PUML
     - If function is send/transmit/receive/enable: Follow with busy-wait
     - If function is get status/error/activity: Poll until condition met

4. **[ERROR Phase]** - If {LOOP_PATTERNS} contains "error/timeout polling":
   - Print "[ERROR] Monitoring for [ERROR_TYPE]"
   - Use while([FLAG_NAME] == 0) loop with {AVAILABLE_ENUMS} flag names only
   - Poll using getter functions from {AVAILABLE_FUNCTIONS}

5. **[VALIDATION Phase]** - Print "[VALIDATION] Validating received data"
   - Print all received variables (using variable names only)
   - Use provided variable names from {FUNCTION_SEQUENCE}

6. **[FINALIZE Phase]** - Print "[FINALIZE] Test completed, returning status"
   - Call cleanup functions if present in {FUNCTION_SEQUENCE}
   - Return 0

---

## STEP-BY-STEP REQUIREMENTS (100% DATA-DRIVEN - NO EXCEPTIONS)

### Rule 1: Dynamic Global Variables (No Hardcoding)
- Analyze {FUNCTION_SEQUENCE} to identify all parameters and return types
- Declare static variables for EVERY:
  - Module handle (extract type from {AVAILABLE_FUNCTIONS})
  - Configuration struct (extract from {AVAILABLE_STRUCTS})
  - Channel handle (derive from parameter analysis)
  - Data buffer (extract size from {FUNCTION_SEQUENCE} or {CONFIG_INITIALIZATION_DETAILS})
  - Error/status flags (identify from {LOOP_PATTERNS})
- Initialize all numeric variables to 0, arrays to {0}, pointers to NULL
- DO NOT add hardcoded channel IDs, buffer sizes, variable names, or identifiers

### Rule 2: Function Variant Selection (Test vs Standard - Data-Driven) **[MANDATORY ENFORCEMENT]**
- **CRITICAL MANDATE**: Analyze {FEATURE_CLASSIFICATION} for test_mode value
- **IF test_mode = true** (ABSOLUTE REQUIREMENT):
  - ✅ **MUST use ONLY ForTest function variants** - NO EXCEPTIONS
  - Detect pattern in {AVAILABLE_FUNCTIONS}: Look for "ForTest" or "ForErrorCtl" suffixes
  - Build dynamic mapping: For each function in {AVAILABLE_FUNCTIONS}, if ForTest variant exists, use it
  - Replace standard functions with ForTest variants by analyzing suffix patterns dynamically
  - Example approach: If function is "init[X]", search for "init[X]ForTest" variant
  - Do NOT call standard variants when ForTest variants exist
  - Map by analyzing function names dynamically from {AVAILABLE_FUNCTIONS} - NO HARDCODED EXAMPLES
- **IF test_mode = false**:
  - Use standard function variants from {AVAILABLE_FUNCTIONS}
  - Do NOT add ForTest suffixes
- **ENFORCEMENT**: This is NOT optional. If test_mode=true, generated code MUST have 100% ForTest variants

### Rule 3: Struct Member Initialization (Immediate & Explicit) **[ZERO TOLERANCE]**
- **MANDATORY REQUIREMENT**: EVERY struct member MUST be explicitly initialized
- **IMMEDIATELY AFTER** each init/config function call:
  - Extract struct name from function parameters (from {FUNCTION_SEQUENCE})
  - Extract ALL member names from {AVAILABLE_STRUCTS} for that struct type
  - For EVERY member in the struct definition:
    - Identify member type from struct definition
    - Assign appropriate value:
      - **If enum type**: Value should ALREADY be resolved by Stage 1 (gpt-5-mini). If you see `/* TODO: CHOOSE_FROM_ABOVE */` or `/* ENUM_PARAM: ... */` remaining, this means Stage 1 failed for that specific case — fall back to selecting the most appropriate value from the comment list based on {FUNCTIONALITY} and {USER_ADDITIONAL_NOTES}
      - If boolean: Use TRUE or FALSE macro (NEVER lowercase true/false)
      - If numeric: Use 0 unless {CONFIG_INITIALIZATION_DETAILS} specifies different value
      - If pointer: Use NULL unless {CONFIG_INITIALIZATION_DETAILS} specifies different value
    - Print member initialization with comment explaining member purpose
    - **CODE MUST LOOK LIKE THIS**:
      ```c
      [STRUCT_VAR].[member1] = [VALUE];  // Comment: purpose of member1
      [STRUCT_VAR].[member2] = [VALUE];  // Comment: purpose of member2
      [STRUCT_VAR].[member3] = [VALUE];  // Comment: purpose of member3
      ```
- **DO NOT**:
  - ❌ Skip ANY member (must initialize ALL)
  - ❌ Assume init function sets all members to safe values
  - ❌ Rely on function calls to initialize members
  - ❌ Use placeholder comments instead of actual code
  - ❌ Leave members uninitialized
  - ❌ Change enum values that Stage 1 already resolved
  - ❌ Use numeric values (0, 1, 2) for enums — always use enum names
- **EXPLICIT CODE ONLY** - no placeholder comments, actual member assignments required

### Rule 4: Extended Config Handling (Conditional)
- **IF {EXTENDED_CONFIG_REQUIRED} = "yes"**:
  - Declare global extended config struct (type from {AVAILABLE_STRUCTS})
  - After init call, explicitly initialize ALL members
  - DO NOT skip initialization for nested structs
- **IF {EXTENDED_CONFIG_REQUIRED} = "no"**:
  - DO NOT add extended config logic
  - DO NOT declare extended config structs

### Rule 5: Busy-Wait Patterns (PUML-Driven, Data-Driven)
- **For EVERY operation** in {FUNCTION_SEQUENCE} that is:
  - send/transmit → Use TX busy-wait pattern
  - receive/enable reception → Use RX busy-wait pattern BEFORE receive
  - get status/activity → Poll with condition from {LOOP_PATTERNS}
- **Pattern Template**:
  ```c
  printf("[BUSY-WAIT] Waiting for [OPERATION_NAME]\n");
  while([BUSY_ENUM_VALUE] == [GET_FUNCTION_NAME](&[STRUCT_VAR], [ACTIVITY_ENUM])) {
      printf("[BUSY-WAIT] [OPERATION_NAME] not ready\n");
  }
  printf("[BUSY-WAIT] [OPERATION_NAME] ready/done\n");
  ```
- **Enum values ONLY from {AVAILABLE_ENUMS}** - DO NOT fabricate
- **Function names ONLY from {AVAILABLE_FUNCTIONS}** - DO NOT fabricate

### Rule 6: Error/Timeout Polling (Conditional)
- **IF {LOOP_PATTERNS} contains "error" or "timeout"**:
  - Add error monitoring phase after main sequence
  - Use pattern: `while([ERROR_FLAG_NAME] == 0) { [GET_ERROR_FUNCTION](...); }`
  - Error flag names ONLY from {AVAILABLE_ENUMS}
  - Getter function ONLY from {AVAILABLE_FUNCTIONS}
- **IF {LOOP_PATTERNS} does NOT contain error/timeout**:
  - DO NOT add error monitoring phase

### Rule 7: ZERO Hardcoding (Universal Rule - MANDATORY)
- **FORBIDDEN - ABSOLUTE**:
  - ❌ Any module names (not even in comments or examples)
  - ❌ Any function names not from {AVAILABLE_FUNCTIONS}
  - ❌ Any struct names not from {AVAILABLE_STRUCTS}
  - ❌ Any enum values not from {AVAILABLE_ENUMS}
  - ❌ Hardcoded channel IDs, buffer sizes, or numeric values
  - ❌ Functionality-specific logic based on module identity
  - ❌ ANY examples with actual identifiers
- **REQUIRED - ABSOLUTE**:
  - ✅ Use {MODULE_NAME} or {module_name} placeholders for all references
  - ✅ Use dynamic variable names derived from {AVAILABLE_STRUCTS}
  - ✅ Use only enum values from {AVAILABLE_ENUMS}
  - ✅ Let {FUNCTION_SEQUENCE} drive all logic
  - ✅ Derive all patterns dynamically from provided data

### Rule 8: Code Comments (Data-Driven, No Hardcoding)
- Comment each function call with PUML reference only (no module names)
- Comment each struct member init with purpose from struct definition
- Print debug message for each major phase: [INIT], [CONFIG], [SEQUENCE], [BUSY-WAIT], [ERROR], [VALIDATION], [FINALIZE]
- DO NOT add explanatory comments beyond PUML references and member purposes
- DO NOT reference module names in comments

---

## CRITICAL IMPLEMENTATION CHECKLIST (VERIFY BEFORE GENERATION)

**MANDATORY** - Code is INVALID if any of these are missing:

- [ ] **ZERO Hardcoded Names**: Search for any module/function/struct names - MUST be ZERO results?
- [ ] **Test vs Standard Mode**: Feature classification analyzed? Variants selected correctly?
- [ ] **Global Variables**: All variables from {FUNCTION_SEQUENCE} declared as static?
- [ ] **Struct Initialization**: EVERY config struct member initialized IMMEDIATELY after init call?
- [ ] **Enum Values**: All enum values kept as-is from skeleton (Stage 1 already resolved them)?
- [ ] **No Numeric Enums**: If any leftover TODOs exist, resolved with ACTUAL enum names (not 0, 1, 2)?
- [ ] **Extended Config**: Declared, initialized, fully populated IF {EXTENDED_CONFIG_REQUIRED}=yes?
- [ ] **Busy-Wait Patterns**: EVERY send/receive/transmit operation followed by matching pattern?
- [ ] **Error Monitoring**: Error/timeout polling added IF {LOOP_PATTERNS} indicates?
- [ ] **Function Signatures**: All function calls use EXACT signatures from {AVAILABLE_FUNCTIONS}?
- [ ] **Code Comments**: PUML references and member purposes present? No hardcoded examples?
- [ ] **Single Function**: Only run_test() defined? No helper functions fabricated?
- [ ] **Return Type**: Function signature is uint8_t run_test(void)?
- [ ] **Module Header**: Derived from {AVAILABLE_FUNCTIONS} prefix pattern? Not hardcoded?
- [ ] **Data Validation**: Received data printed using variable names only?
- [ ] **FORBIDDEN PATTERNS**: No pollCount? No cleanup before [FINALIZE]? While-loops unchanged?

---

## DETAILED CONTEXT FOR CODE GENERATION

### Context 1: Feature Classification & Function Variant Selection (Data-Driven)

**Your input includes feature classification:**
```
{FEATURE_CLASSIFICATION}
```

**Critical logic**:
- If "test_mode: True" → MUST use all ForTest function variants
- If "test_mode: False" → Use standard function variants
- If "error_injection: True" → May include error control functions

**Function Variant Selection Method** (APPLY DYNAMICALLY):
- Analyze {AVAILABLE_FUNCTIONS} for function name patterns
- Look for "ForTest" or "ForErrorCtl" or similar suffixes in function names
- If present: Use those variants when test_mode=true
- Extract pattern dynamically - DO NOT hardcode function names
- DO NOT reference any module-specific function names

### Context 2: Data-Driven Struct Initialization (Generic Pattern)

**Example Pattern** (Generic - apply to ANY struct):

```c
// Call init function
[INIT_FUNCTION_FROM_AVAILABLE](&[CONFIG_STRUCT_FROM_AVAILABLE], [PARAMS]);

// IMMEDIATELY AFTER: Explicit member initialization
// Extract all members from {AVAILABLE_STRUCTS} for this struct type
// For each member:
//   - Identify type from struct definition
//   - Assign appropriate value based on type:
[CONFIG_STRUCT].[MEMBER_1] = [VALUE_FROM_INITIALIZATION_DETAILS];
[CONFIG_STRUCT].[MEMBER_2] = [VALUE_FROM_ENUMS];
[CONFIG_STRUCT].[MEMBER_3] = [VALUE_FROM_DEFAULTS];
```

**DO NOT**:
- ❌ Assume init function sets all members to safe values
- ❌ Skip member initialization and rely on function calls
- ❌ Use default or placeholder values
- ❌ Reference any module-specific struct names

### Context 3: Loop Pattern Recognition (Data-Driven)

**{LOOP_PATTERNS}** tells you what polling patterns are needed:

**Pattern Types**:
- `busy_wait_tx_rx`: After send, poll TX done then RX done
- `busy_wait_rx`: Before receive, poll RX ready
- `busy_wait_status`: Poll status getter until condition met
- `error_polling`: Poll error flags until error detected
- `timeout_polling`: Poll timeout flags until timeout detected

**Implementation**:
- Extract pattern name from {LOOP_PATTERNS}
- Select matching template from templates section below
- Replace placeholders with actual function/enum names from {AVAILABLE_*}
- DO NOT hardcode pattern names or functions

### Context 4: Extended Configuration (Conditional)

**IF {EXTENDED_CONFIG_REQUIRED} = "yes"**:

1. Find extended config struct type from {AVAILABLE_STRUCTS}
2. Declare static global variable: `static [ExtStructType] [variable_name] = {0};`
3. Call extended config init if present in {FUNCTION_SEQUENCE}
4. Initialize ALL members, including nested structs:
   ```c
   [ext_config].[member1] = [value from AVAILABLE_ENUMS or CONFIG_INITIALIZATION_DETAILS];
   [ext_config].[member2] = [value];
   [ext_config].[nested].[member3] = [value];  // Don't skip nested!
   ```

**IF {EXTENDED_CONFIG_REQUIRED} = "no"**:
- Skip extended config entirely

### Context 5: Channel Variable Naming (Data-Driven)

**From {CHANNEL_INSTANTIATION_PATTERNS}**:
- Derive channel variable names dynamically from PUML analysis
- Extract naming pattern from provided context
- DO NOT hardcode "channel0", "channel3", or any specific identifiers
- Use variable names derived from {CHANNEL_INSTANTIATION_PATTERNS}

---

## GENERATION REQUIREMENTS (100% DATA-DRIVEN - ZERO HARDCODING)

### Requirement 1: Module Header Derivation (Dynamic)
Determine module header from {AVAILABLE_FUNCTIONS}:
- Analyze function names: extract common prefix pattern
- Example approach: If functions have prefix "[PREFIX]_", derive header as "[PREFIX].h"
- Extract dynamically - DO NOT hardcode header names
- DO NOT reference specific module headers like "Ifx[X].h" or "[Y].h"

### Requirement 2: Struct Type Determination (From Data)
- For each struct variable needed in {FUNCTION_SEQUENCE}:
  - Find type definition in {AVAILABLE_STRUCTS}
  - Extract EXACT type name and member list
  - DO NOT assume or fabricate struct names
  - DO NOT reference module-specific struct names

### Requirement 3: Global Variable Declaration (Complete Set)
- Declare ONE static variable for EVERY:
  - Module/handle (extract type from {AVAILABLE_FUNCTIONS})
  - Configuration struct (extract from {AVAILABLE_STRUCTS})
  - Channel (if {FUNCTION_SEQUENCE} shows channels)
  - Data buffer (if send/receive operations present)
  - Status/Error flag (if polling patterns detected)
  - Counter variable (if loops needed)
- Initialize all to 0 or {0} or NULL
- All must be static (file-scoped)
- All must be at file level before run_test()

### Requirement 4: Enum Value Usage (STRICT)
- EVERY enum assignment must use value from {AVAILABLE_ENUMS}
- If enum type not found in {AVAILABLE_ENUMS}:
  - This is an error - code generation must stop
  - DO NOT fabricate enum values
- If multiple enum values present for same type:
  - Use FIRST value from list unless {CONFIG_INITIALIZATION_DETAILS} specifies
  - Select based on operational context, not module identity

### Requirement 5: Boolean Assignment (Macros, Not Lowercase)
- MANDATORY: Use TRUE/FALSE macros, NEVER lowercase true/false
- Example: ✅ `config.enable = TRUE;` / ❌ `config.enable = true;`
- Boolean values ONLY from {AVAILABLE_ENUMS}

### Requirement 6: Immediate Member Initialization (After Each Init Call)
```c
// Step 1: Call init function
[FUNCTION](&[STRUCT], [PARAMS]);

// Step 2: IMMEDIATELY initialize members (NO DELAY)
[STRUCT].[member1] = [value1];
[STRUCT].[member2] = [value2];
[STRUCT].[member3] = [value3];
// ... ALL members from {AVAILABLE_STRUCTS} definition
```
- DO NOT wait or add code between init and member init
- DO NOT skip any member
- DO NOT use placeholder comments

### Requirement 7: Extended Config (If Required)
```c
// In globals section
static [ExtConfigType] [ext_var] = {0};

// After extended config init call
[ext_var].[member1] = [value];
[ext_var].[member2] = [value];
// Initialize nested structs too:
[ext_var].[nested].[member3] = [value];
// ...all members from {AVAILABLE_STRUCTS}
```

### Requirement 8: Function Calls (Exact Signatures)
- Extract function signature from {AVAILABLE_FUNCTIONS}
- Call with EXACT parameters in EXACT order
- DO NOT modify parameter names or types
- DO NOT add extra parameters or skip parameters
- Use variable names from globals section

### Requirement 9: Busy-Wait Templates (Pattern-Driven, Data-Driven)
- AFTER send/transmit: Use TX+RX busy-wait
- BEFORE receive: Use RX-ready busy-wait
- FOR status polling: Use while(condition) polling with correct enums
- ENUM VALUES from {AVAILABLE_ENUMS} ONLY
- FUNCTION NAMES from {AVAILABLE_FUNCTIONS} ONLY
- DO NOT hardcode any pattern names or function identifiers

### Requirement 10: Error Polling (Conditional)
- IF {LOOP_PATTERNS} contains error/timeout:
  - Add error monitoring loop after main sequence
  - Use while([FLAG] == 0) pattern
  - Poll with getter function from {AVAILABLE_FUNCTIONS}
  - Flag names from {AVAILABLE_ENUMS}
- IF no error/timeout in patterns:
  - DO NOT add error monitoring

### Requirement 11: Code Style (Consistent)
- Indentation: 4 spaces (NOT tabs)
- Comment style: `// Short description` for single lines
- Printf format: `printf("[PHASE] Message\n");`
- Phases: [INIT], [CONFIG], [SEQUENCE], [BUSY-WAIT], [ERROR], [VALIDATION], [FINALIZE]
- One empty line between phases
- Two empty lines between major sections

### Requirement 12: Debug Output (Traceable)
- Print at phase start: `printf("[PHASE] Starting phase\n");`
- Print after major action: `printf("[ACTION] Action completed\n");`
- Print before/after busy-wait: `printf("[BUSY-WAIT] Waiting for operation\n");`
- Print data validation: `printf("Variable: 0x%02X\n", variable);`
- DO NOT use hard-to-trace messages
- All messages must be clear and actionable

### Requirement 13: Function Count & Signature
- ONLY ONE function: `uint8_t run_test(void)`
- NO helper functions (no fabrication)
- Return type MUST be uint8_t
- Parameter list MUST be void
- Return value MUST be 0 on success

---

## UNIVERSAL BUSY-WAIT PATTERN TEMPLATES (DYNAMIC & DATA-DRIVEN)

These patterns are templates. **Replace ALL bracketed placeholders with actual names from {AVAILABLE_FUNCTIONS} and {AVAILABLE_ENUMS}**. Do NOT use as-is with placeholders.

### Pattern 1: RX Ready (Before Receive Operations)
```c
printf("[BUSY-WAIT] Waiting for RX ready\n");
while([BUSY_ENUM] == [GET_STATUS_FUNCTION](&[RX_CHANNEL], [RX_ACTIVITY_ENUM])) {
    printf("[BUSY-WAIT] RX not ready\n");
}
printf("[BUSY-WAIT] RX ready\n");
[RECEIVE_FUNCTION]([parameters]);
```

**When to use**: BEFORE receive, receiveHeader, receiveResponse functions
**Placeholders**: Replace with actual names from {AVAILABLE_FUNCTIONS} and {AVAILABLE_ENUMS}

### Pattern 2: TX Complete (After Send Operations)
```c
[SEND_FUNCTION]([parameters]);
printf("[BUSY-WAIT] Waiting for TX completion\n");
while([BUSY_ENUM] == [GET_STATUS_FUNCTION](&[TX_CHANNEL], [TX_ACTIVITY_ENUM])) {
    printf("[BUSY-WAIT] TX still busy\n");
}
printf("[BUSY-WAIT] TX done\n");
while([BUSY_ENUM] == [GET_STATUS_FUNCTION](&[RX_CHANNEL], [RX_ACTIVITY_ENUM])) {
    printf("[BUSY-WAIT] RX still busy\n");
}
printf("[BUSY-WAIT] RX done\n");
```

**When to use**: AFTER send, sendHeader, transmitResponse functions
**Placeholders**: Replace with actual names from {AVAILABLE_FUNCTIONS} and {AVAILABLE_ENUMS}

### Pattern 3: Error Flag Polling (If Needed)
```c
printf("[ERROR] Monitoring for error event\n");
while([ERROR_FLAG_NAME] == 0) {
    [GET_ERROR_FUNCTION](&[CHANNEL], &[ERROR_STRUCT]);
    printf("[ERROR] Error event not detected\n");
}
printf("[ERROR] Error event detected\n");
```

**When to use**: IF {LOOP_PATTERNS} contains "error" or "timeout"
**Placeholders**: Replace with actual names from {AVAILABLE_STRUCTS}, {AVAILABLE_FUNCTIONS}, and {AVAILABLE_ENUMS}

---

## 🚫 FORBIDDEN PATTERNS (ABSOLUTE — ZERO TOLERANCE) 🚫

**THE SKELETON CODE PROVIDED TO YOU IS STRUCTURALLY CORRECT. DO NOT "FIX" OR "IMPROVE" ITS STRUCTURE.**

The following patterns are **STRICTLY FORBIDDEN** in your generated code. Violating ANY of these is an **IMMEDIATE FAILURE**.

### FORBIDDEN #1: Timeout Counters / Iteration Limits in Polling Loops
❌ **NEVER** add `pollCount`, `timeout`, `maxRetries`, `iterationLimit`, or ANY counter variable to busy-wait or error-polling loops.
❌ **NEVER** add `if (pollCount > N) break;` or any safety-net exit condition to polling loops.
❌ **NEVER** invent a loop-exit mechanism that does not exist in the skeleton.

**WHY**: These are bare-metal hardware polling loops. They MUST spin until the hardware condition is met. Adding artificial timeouts breaks hardware synchronization.

**WRONG** (FORBIDDEN):
```c
int pollCount = 0;
while(errorFlags.rxCrcError == 0) {
    [GET_ERROR_FUNCTION](&channel, &errorFlags);
    pollCount++;
    if (pollCount > 1000000) break;  // ❌ FORBIDDEN
}
```

**CORRECT** (REQUIRED):
```c
while(errorFlags.rxCrcError == 0) {
    [GET_ERROR_FUNCTION](&channel, &errorFlags);
}
```

### FORBIDDEN #2: Moving Cleanup/Clear Functions Before End of Test
❌ **NEVER** place cleanup functions (clear interrupts, deinit, disable, reset) in the MIDDLE of the test sequence.
❌ **NEVER** move `clearAllInterrupts`, `clearAllFlags`, `deinit`, or similar cleanup calls to anywhere BEFORE the final [FINALIZE] phase.
❌ **NEVER** reorder the skeleton's cleanup placement.

**WHY**: Cleanup functions MUST execute AFTER all test operations and validations are complete. Moving them earlier clears hardware state needed by subsequent test steps.

**WRONG** (FORBIDDEN):
```c
// [SEQUENCE]
[SEND_FUNCTION](...);
[CLEAR_FUNCTION](&channel0);  // ❌ FORBIDDEN — cleanup in middle of sequence
[CLEAR_FUNCTION](&channel3);  // ❌ FORBIDDEN — cleanup in middle of sequence
// [ERROR] — error flags already cleared! Test broken!
while(errorFlags.rxCrcError == 0) { ... }
```

**CORRECT** (REQUIRED):
```c
// [SEQUENCE]
[SEND_FUNCTION](...);
// ... all busy-waits, error polling, validation ...

// [FINALIZE] — cleanup ALWAYS at the very end
[CLEAR_FUNCTION](&channel0);
[CLEAR_FUNCTION](&channel3);
```

### FORBIDDEN #3: Modifying While-Loop Structure from Skeleton
❌ **NEVER** change a single-line busy-wait `while(...);` into a multi-line block with body code.
❌ **NEVER** add print statements, counters, or delay calls inside busy-wait loops that the skeleton defines as empty spin-waits.
❌ **NEVER** convert `while(condition);` (semicolon-terminated) into `while(condition) { body; }`.

**WHY**: The skeleton's while-loop structure matches the hardware driver's expected usage pattern. Altering it changes timing behavior.

**WRONG** (FORBIDDEN):
```c
while([BUSY_ENUM] == [GET_STATUS](&channel, [ACTIVITY])) {
    printf("waiting...\n");  // ❌ FORBIDDEN — skeleton had no body
    pollCount++;             // ❌ FORBIDDEN — invented counter
}
```

**CORRECT** (REQUIRED):
```c
while([BUSY_ENUM] == [GET_STATUS](&channel, [ACTIVITY]));
```

### FORBIDDEN #4: Inventing Variables, Functions, or Enum Values
❌ **NEVER** declare variables not derivable from {AVAILABLE_STRUCTS}, {AVAILABLE_FUNCTIONS}, or {AVAILABLE_ENUMS}.
❌ **NEVER** call functions not listed in {AVAILABLE_FUNCTIONS}.
❌ **NEVER** use enum values not listed in {AVAILABLE_ENUMS} or in the skeleton's `ENUM CHOICE REQUIRED` comments.

### ENFORCEMENT SUMMARY
| Violation | Verdict |
|-----------|---------|
| Added pollCount / timeout counter | **IMMEDIATE FAILURE** |
| Cleanup before [FINALIZE] phase | **IMMEDIATE FAILURE** |
| Modified while-loop structure | **IMMEDIATE FAILURE** |
| Invented variable / function / enum | **IMMEDIATE FAILURE** |

**TRUST THE SKELETON**: The skeleton code structure, loop patterns, and cleanup placement are all CORRECT. Your job is to:
1. Resolve enum TODO placeholders to correct values
2. Fill in missing parameters using {AVAILABLE_FUNCTIONS} signatures
3. Add appropriate printf debug messages (NOT inside spin-wait loops)
4. Keep the EXACT same code structure, ordering, and placement

---

## FINAL CRITICAL REMINDERS (ZERO TOLERANCE FOR HARDCODING)

1. **ZERO Hardcoded Identifiers**: Every function, struct, enum name from {AVAILABLE_*} data ONLY
2. **Enum Compliance**: Use ONLY enum values from {AVAILABLE_ENUMS}
3. **Boolean Usage**: TRUE/FALSE macros ONLY, never lowercase
4. **Immediate Init**: Struct members initialized IMMEDIATELY after init call
5. **Pattern Matching**: Every hardware operation gets matching busy-wait
6. **Error Conditional**: Error polling added ONLY IF {LOOP_PATTERNS} indicates
7. **Function Signature**: Use EXACT signatures from {AVAILABLE_FUNCTIONS}
8. **Test Mode Check**: ForTest variants ONLY if {FEATURE_CLASSIFICATION} shows test_mode=true
9. **Variable Names**: Derive from context and data, NEVER hardcoded
10. **Code Style**: Match reference files (indentation, comments, printf format)
11. **Module Header**: Derived dynamically from function prefixes, NEVER hardcoded
12. **No Module Identity Logic**: Code works identically for ANY module

---
