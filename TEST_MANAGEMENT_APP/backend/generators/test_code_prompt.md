# STAGE 2: TEST CODE ENHANCEMENT PROMPT

> You are enhancing a pre-processed C test skeleton. The skeleton is COMPLETE and CORRECT. Enum values are ALREADY resolved by Stage 1. Your job is to: add debug printf statements, verify all struct members are initialized, and return clean compilable C. DO NOT restructure, reorder, or reconstruct anything from scratch.

---

## YOUR ROLE

| DO | DO NOT |
|------|--------|
| Keep all enum values exactly as-is from skeleton | Change any resolved enum value |
| Add printf debug messages at phase boundaries | Add pollCount / timeout counters |
| Keep all struct member initializations as skeleton provides | Add or remove struct members |
| Use exact function signatures from {AVAILABLE_FUNCTIONS} | Invent functions, variables, or enums |
| Copy skeleton code order exactly | Restructure, reorder, or reconstruct |
| Use TRUE/FALSE macros for booleans | Use lowercase true/false |

---

## CONSTRAINT: PRIMARY TEST FUNCTION

- DO NOT CALL {PRIMARY_TEST_FUNCTION} — this is the test target the user implements manually
- Generate ONLY setup/prerequisite functions from the skeleton
- If {PRIMARY_TEST_FUNCTION} is "None identified": copy all functions from skeleton normally

---

## DATA PLACEHOLDERS (Use ONLY These)

| Placeholder | Content | Authority |
|-------------|---------|-----------|
| {MODULE_NAME} | Module name | Reference |
| {FUNCTIONALITY} | Test description | Reference |
| {FEATURE_CLASSIFICATION} | test_mode and error_injection flags | Reference |
| {FUNCTION_SEQUENCE} | Ordered function list from PUML | Reference only — skeleton is authoritative |
| {AVAILABLE_FUNCTIONS} | Complete function signatures | Use for signature verification |
| {AVAILABLE_STRUCTS} | Struct definitions with all members | Use to verify member completeness |
| {AVAILABLE_ENUMS} | Enum type to value mappings | Use for TODO fallback (Rule 3) only |
| {CONFIG_INITIALIZATION_DETAILS} | Initial values for struct members | Reference |
| {EXTENDED_CONFIG_REQUIRED} | yes or no | Reference |
| {LOOP_PATTERNS} | Polling patterns already in skeleton | Reference only |
| {CHANNEL_INSTANTIATION_PATTERNS} | Channel variable naming | Reference |
| {USER_ADDITIONAL_NOTES} | Extra user context | Reference |

---

## CODE STRUCTURE (6 Phases - Fixed Order)

The skeleton already has all 6 phases in the correct order. Copy each phase exactly and add printf statements.

### Phase 1: [INIT] - Initialization
- Copy all init function calls from the skeleton `[INIT]` section verbatim
- The skeleton has already selected ForTest/ForErrorCtl variants — keep them as-is

### Phase 2: [CONFIG] - Configuration
- Copy all config init calls and struct member assignments from the skeleton `[CONFIG]` section verbatim
- Enum values are already resolved in the skeleton — do NOT change them
- If {EXTENDED_CONFIG_REQUIRED} = yes, the skeleton already includes extended config — copy it

### Phase 3: [SEQUENCE] - PUML-Driven Operations
- The skeleton's `[SEQUENCE]` section is AUTHORITATIVE — copy EVERY function call and while-loop from it verbatim, in the same order
- Do NOT drop, rename, or comment out any call or loop that appears in the skeleton
- Do NOT add any new while-loops — the skeleton already contains every necessary polling loop
- The skeleton places busy-wait polling AFTER TX calls and BEFORE RX calls — this positioning is already correct, do not change it
- Add printf before each function call (see DEBUG OUTPUT FORMAT below)

### Phase 4: [ERROR MONITORING] - Error Detection Loop (conditional)
- The skeleton already generates this loop when needed — it appears under `/* === [ERROR MONITORING] ... */`
- Copy it exactly as-is: `while(errorFlags.member == 0) { getErrorFlags(&channel, &errorFlags); }`
- This is a body loop `while(cond) { ... }` with a function call inside — NOT a spin-wait semicolon loop
- Do NOT construct a new one. Do NOT add a second one.

### Phase 5: [VALIDATION] - Data Verification
- Print all received data variables (rxData buffers, flags, status values) using printf
- Use variable names already declared in the skeleton globals — do not invent new ones

### Phase 6: [FINALIZE] - Cleanup (ALWAYS LAST)
- Copy all cleanup/clear function calls from the skeleton `[FINALIZE]` section verbatim
- `return 0;` MUST be the absolute last line inside `run_test()` — nothing after it

---

## MANDATORY RULES

### Rule 1: ForTest Variants — Already Done by Skeleton
The skeleton has already substituted ForTest/ForErrorCtl variants for all standard functions.
- Do NOT re-scan or re-substitute
- If you see a ForTest variant in the skeleton, keep it exactly as written

### Rule 2: Struct Members — Verify ALL Are Present
After each config init call, ALL struct members must be initialized. Cross-check against {AVAILABLE_STRUCTS}:

```c
initFunc(&configStruct, &module);
configStruct.member1 = VALUE;  /* Every member — no exceptions */
configStruct.member2 = VALUE;
configStruct.member3 = VALUE;
```

- Enum members: already in skeleton (Stage 1 resolved) — keep as-is
- Boolean: TRUE / FALSE (NEVER true/false)
- Numeric: 0 unless {CONFIG_INITIALIZATION_DETAILS} says otherwise
- Pointer: NULL
- If a member is missing from the skeleton, add it using the correct enum/value from {AVAILABLE_STRUCTS}

### Rule 3: Leftover TODO Fallback (Rare)
If you see `/* TODO: CHOOSE_FROM_ABOVE */` or `/* ENUM_PARAM: Select from [...] */`:
- Stage 1 failed for this specific value — you must resolve it
- Read the comment listing available options
- Choose based on {FUNCTIONALITY} + {USER_ADDITIONAL_NOTES} context
- NEVER use numeric values (0, 1, 2) — always use the enum name from the comment

### Rule 4: Zero Hardcoding
- Function names: ONLY from {AVAILABLE_FUNCTIONS}
- Struct names: ONLY from {AVAILABLE_STRUCTS}
- Enum values: ONLY from {AVAILABLE_ENUMS} or skeleton comments
- Module header: derive from function prefix (e.g. prefix `Abc_Xyz_` → `Abc_Xyz.h`)
- Variable names: derive from struct types and channel patterns already in skeleton

### Rule 5: Static Globals
All module handles, config structs, channel handles, data buffers, and error/status flag structs must be declared as `static` globals before `run_test()`:
- Numeric: `= 0`
- Arrays/structs: `= {0}`
- Pointers: `= NULL`

---

## FORBIDDEN PATTERNS — ZERO TOLERANCE

| # | Forbidden | Why | Verdict |
|---|-----------|-----|---------|
| 1 | `pollCount`, `timeout`, `maxRetries`, any counter variable in or near polling loops | Bare-metal hardware must spin until condition is met | FAIL |
| 2 | `if (count > N) break;` inside any loop | Artificial exit breaks hardware synchronization | FAIL |
| 3 | Cleanup/clear/deinit functions anywhere before `[FINALIZE]` | Clears hardware state needed by later steps | FAIL |
| 4 | Changing `while(cond);` spin-wait to `while(cond) { body; }` | Skeleton loop structure matches driver specification | FAIL |
| 5 | Adding any while-loop not already present in the skeleton | Skeleton already contains all necessary loops | FAIL |
| 6 | Inventing variable names, function names, or enum values not in provided data | Only use data from {AVAILABLE_FUNCTIONS}/{AVAILABLE_STRUCTS}/{AVAILABLE_ENUMS} | FAIL |
| 7 | Using numeric literals for enum members (`= 0`, `= 1`) | Must use named enum identifiers | FAIL |
| 8 | Calling `{PRIMARY_TEST_FUNCTION}` | User implements this manually — calling it here is incorrect | FAIL |

**TRUST THE SKELETON**: Its function order, loop patterns, enum values, and cleanup placement are all pre-validated. Your job is to enhance output quality — not to restructure.

---

## DEBUG OUTPUT FORMAT

Add `printf` at phase entry points and before each function call:

```c
printf("[INIT] Starting initialization\n");
printf("[CONFIG] Configuring %s channel\n", "master");
printf("[SEQUENCE] Calling sendHeader\n");
printf("[BUSY-WAIT] Waiting for TX completion\n");
printf("[ERROR] Polling for error flag detection\n");
printf("[VALIDATION] rxData[0]: 0x%02X\n", rxData[0]);
printf("[FINALIZE] Cleanup complete, returning\n");
```

- Place printf BEFORE each function call, not after
- Do NOT place printf inside empty spin-wait loops: `while(cond);`
- The error monitoring body loop `while(cond) { ... }` may have a printf after the closing brace

---

## PRE-SUBMISSION CHECKLIST

Before outputting, verify every item:

- [ ] Single function `uint8_t run_test(void)` — no other functions defined
- [ ] All enum values copied exactly from skeleton (Stage 1) — none changed
- [ ] Every struct member initialized after its init call — verified against {AVAILABLE_STRUCTS}
- [ ] ForTest/ForErrorCtl variants preserved as skeleton has them
- [ ] Cleanup calls ONLY in `[FINALIZE]` — none before it
- [ ] No `pollCount`, `timeout`, `break`, or any counter near polling loops
- [ ] All while-loops copied verbatim from skeleton — zero new while-loops added
- [ ] No invented functions, variables, or enum values
- [ ] `{PRIMARY_TEST_FUNCTION}` NOT called anywhere
- [ ] `TRUE`/`FALSE` macros used — no lowercase `true`/`false`
- [ ] `#include` header derived from function prefix — not hardcoded
- [ ] `return 0;` is the absolute last line of `run_test()`
