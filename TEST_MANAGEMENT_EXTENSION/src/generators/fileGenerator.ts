import * as vscode from 'vscode';

interface GeneratedFile {
    name: string;
    content: string;
    language: 'c' | 'h' | 'md';
}

/**
 * Generates test files from test generation results
 */
export class FileGenerator {
    /**
     * Generate files from test generation result
     */
    generateFiles(result: any): GeneratedFile[] {
        const files: GeneratedFile[] = [];
        
        // Get the generated code
        const generatedCode = result.generation_result?.test_code_template || '';
        const enhancedCode = result.llm_enhancement?.enhanced_code || '';
        
        // Use enhanced code if available, otherwise use generated code
        const testCode = enhancedCode || generatedCode || '// No test code generated';
        
        // Create test file (.c)
        files.push({
            name: `test_${result.test_id}.c`,
            content: testCode,
            language: 'c'
        });
        
        // Create header file (.h)
        files.push({
            name: `test_${result.test_id}.h`,
            content: this.generateHeader(result),
            language: 'h'
        });
        
        // Create documentation (.md)
        files.push({
            name: `TEST_${result.test_id}.md`,
            content: this.generateDocumentation(result),
            language: 'md'
        });
        
        return files;
    }
    
    /**
     * Generate header file content
     */
    private generateHeader(result: any): string {
        const testId = result.test_id.toUpperCase();
        return `#ifndef __${testId}_H__
#define __${testId}_H__

/**
 * Test ID: ${result.test_id}
 * Generated: ${result.timestamp}
 * Module: ${result.module}
 * Description: ${result.description}
 */

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

/* Test function declarations */
void test_setup(void);
void test_teardown(void);
void test_main(void);

/* Test result tracking */
extern int test_passed;
extern int test_failed;
extern int test_total;

#endif /* __${testId}_H__ */`;
    }
    
    /**
     * Generate documentation file content
     */
    private generateDocumentation(result: any): string {
        const ragContext = result.rag_context || {};
        const kgContext = result.kg_context || {};
        
        return `# Test: ${result.test_id}

## Overview
**Generated:** ${result.timestamp}  
**Module:** ${result.module}  
**Compliance Score:** ${(result.compliance_score * 100).toFixed(1)}%  

## Test Description
${result.description}

---

## Context Analysis

### RAG (Semantic) Context
- **Functions Found:** ${ragContext.functions_count || 0}
- **Structs Found:** ${ragContext.structs_count || 0}
- **Enums Found:** ${ragContext.enums_count || 0}
- **Requirements Found:** ${ragContext.requirements_count || 0}

### KG (Graph) Context
- **Dependencies Identified:** ${kgContext.dependency_count || 0}
- **Relationship Types:** ${Object.keys(kgContext.dependencies || {}).length}

---

## LLM Enhancement

${result.llm_enhancement.available ? `
**Model Used:** ${result.llm_enhancement.model}

The test code has been enhanced with:
1. Improved error handling
2. Comprehensive assertions
3. Edge case coverage
4. MISRA-C compliance
5. Detailed comments and documentation
` : '⚠️ LLM enhancement not available'}

---

## Generated Files

1. **test_${result.test_id}.c** - Main test implementation
2. **test_${result.test_id}.h** - Test header with declarations
3. **TEST_${result.test_id}.md** - This documentation

---

## Test Execution

\`\`\`bash
# Compile the test
gcc -o test_${result.test_id} test_${result.test_id}.c

# Run the test
./test_${result.test_id}
\`\`\`

---

## Compliance Information

**MISRA-C Compliance:** ${(result.compliance_score * 100).toFixed(1)}%

The generated test code has been validated against MISRA-C standards for:
- Type safety
- Memory management
- Function pointer usage
- Control flow clarity
- Code clarity and maintainability

---

## Metadata

\`\`\`
Test ID: ${result.test_id}
Status: ${result.status}
Module: ${result.module}
Generated: ${result.timestamp}
\`\`\`
`;
    }
    
    /**
     * Save files to workspace
     */
    async saveFiles(files: GeneratedFile[], outputDir: string): Promise<string[]> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open');
        }
        
        const outputUri = vscode.Uri.joinPath(workspaceFolder.uri, outputDir);
        
        // Create output directory if it doesn't exist
        try {
            await vscode.workspace.fs.stat(outputUri);
        } catch {
            await vscode.workspace.fs.createDirectory(outputUri);
        }
        
        const savedFiles: string[] = [];
        
        // Save each file
        for (const file of files) {
            const fileUri = vscode.Uri.joinPath(outputUri, file.name);
            const fileContent = new TextEncoder().encode(file.content);
            await vscode.workspace.fs.writeFile(fileUri, fileContent);
            savedFiles.push(fileUri.fsPath);
        }
        
        return savedFiles;
    }
}
