import * as vscode from 'vscode';
import { BackendClient } from '../backend/client';
import { getWebviewContent } from './webviewContent';

/**
 * Manages the webview panel for the test generator UI
 */
export class WebviewManager {
    private panel: vscode.WebviewPanel | undefined;
    private context: vscode.ExtensionContext;
    private backendClient: BackendClient;
    private modelsReady: Promise<void>;
    
    constructor(context: vscode.ExtensionContext, backendClient: BackendClient, modelsReady: Promise<void>) {
        this.context = context;
        this.backendClient = backendClient;
        this.modelsReady = modelsReady;
    }
    
    /**
     * Show or focus the webview panel
     */
    showPanel(): vscode.WebviewPanel {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.One);
            // Re-push models and modules on reveal in case they changed
            this.pushInitialData();
        } else {
            this.panel = vscode.window.createWebviewPanel(
                'testGeneratorPanel',
                'Test Generator',
                vscode.ViewColumn.One,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true
                }
            );
            
            this.panel.webview.html = getWebviewContent();
            
            // Handle messages from webview
            this.panel.webview.onDidReceiveMessage(
                (message: any) => this.handleWebviewMessage(message),
                undefined,
                this.context.subscriptions
            );
            
            // Clean up when panel is closed
            this.panel.onDidDispose(
                () => {
                    this.panel = undefined;
                },
                undefined,
                this.context.subscriptions
            );
            
            // Push models and modules once they're ready
            // pushInitialData internally waits for model discovery to complete
            // Small delay to ensure webview HTML has initialized its message listener
            setTimeout(() => this.pushInitialData(), 500);
        }
        
        return this.panel;
    }
    
    /**
     * Push models and modules data to webview proactively.
     * Waits for the modelsReady promise (i.e. extension has discovered and
     * sent models to backend) then polls backend until models are available.
     */
    private async pushInitialData() {
        // Step 1: Wait for extension.ts to finish discovering models and POSTing them to backend
        // This has a 15-second timeout so the webview doesn't hang forever
        try {
            await Promise.race([
                this.modelsReady,
                new Promise(resolve => setTimeout(resolve, 15000))
            ]);
        } catch (e) {
            console.warn('[WEBVIEW] modelsReady promise error:', e);
        }

        // Step 2: Poll backend for models (they should now be available)
        // Retry up to 5 times with 1s intervals
        let models: any[] = [];
        for (let attempt = 1; attempt <= 5; attempt++) {
            try {
                models = await this.backendClient.getAvailableModels();
                if (models.length > 0) {
                    console.log(`[WEBVIEW] Got ${models.length} models on attempt ${attempt}`);
                    break;
                }
            } catch (e) {
                console.warn(`[WEBVIEW] Model fetch attempt ${attempt} failed:`, e);
            }
            if (attempt < 5) {
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }

        // Step 3: Send models to webview
        this.panel?.webview.postMessage({
            command: 'modelsList',
            models
        });

        // Step 4: Also send modules
        try {
            await this.handleGetModules();
        } catch (e) {
            console.warn('[WEBVIEW] Could not push modules:', e);
        }
    }
    
    /**
     * Handle messages from the webview
     */
    private async handleWebviewMessage(message: any) {
        const { command, data } = message;
        
        switch (command) {
            case 'generateTest':
                await this.handleGenerateTest(data);
                break;
            case 'selectModel':
                await this.handleSelectModel(data);
                break;
            case 'getModels':
                await this.handleGetModels();
                break;
            case 'getModules':
                await this.handleGetModules();
                break;
            case 'acceptTest':
                await this.handleAcceptTest(data);
                break;
        }
    }
    
    /**
     * Handle test generation request from webview
     */
    private async handleGenerateTest(data: any) {
        try {
            // Step 1: Get RAG + KG context and skeleton code from backend
            const result = await this.backendClient.generateTest({
                module: data.module,
                description: data.description,
                additional_notes: data.notes,
                llm_model: data.llmModel
            });
            
            const selectedModel = data.llmModel;
            let llmPrompt = result.llm_enhancement?.llm_prompt;
            
            // ================================================================
            // STAGE 1: Enum Resolution (gpt-5-mini — automatic, no user choice)
            // ================================================================
            // If the backend prepared an enum resolver prompt, call gpt-5-mini 
            // to resolve all enum TODO placeholders BEFORE the main LLM call.
            // This prevents the main model from hallucinating wrong enum values.
            // ================================================================
            const enumResolverPrompt = result.llm_enhancement?.enum_resolver_prompt;
            
            if (enumResolverPrompt && llmPrompt) {
                try {
                    const stage1StartTime = Date.now();
                    console.log(`[STAGE-1] ⏱️  Starting enum resolution with gpt-5-mini...`);
                    
                    this.panel?.webview.postMessage({
                        command: 'llmProgress',
                        message: `Stage 1: Resolving enum values (gpt-5-mini)...`
                    });
                    
                    let llmCallDuration = 0;
                    let parseDuration = 0;
                    let applyDuration = 0;
                    
                    // Call gpt-5-mini for focused enum resolution
                    const llmCallStart = Date.now();
                    const enumResponse = await this.callVSCodeLLM('gpt-5-mini', enumResolverPrompt);
                    llmCallDuration = Date.now() - llmCallStart;
                    
                    if (enumResponse) {
                        console.log(`[STAGE-1] ✓ gpt-5-mini response received (${enumResponse.length} chars, ${llmCallDuration}ms)`);
                        
                        // Parse JSON response from gpt-5-mini
                        const parseStart = Date.now();
                        const resolvedValues = this.parseEnumResolverResponse(enumResponse);
                        parseDuration = Date.now() - parseStart;
                        
                        if (resolvedValues && Object.keys(resolvedValues).length > 0) {
                            console.log(`[STAGE-1] ✓ Parsed ${Object.keys(resolvedValues).length} enum values (${parseDuration}ms)`);
                            
                            // Apply resolved enums to skeleton via backend
                            const skeletonCode = result.generation_result?.sample_test_code || result.test_code || '';
                            if (skeletonCode) {
                                const applyStart = Date.now();
                                const resolvedSkeleton = await this.backendClient.applyEnumResolution(
                                    skeletonCode,
                                    resolvedValues
                                );
                                applyDuration = Date.now() - applyStart;
                                
                                // Update the LLM prompt with the resolved skeleton
                                // Replace the old skeleton in the prompt with the enum-resolved one
                                if (resolvedSkeleton && resolvedSkeleton !== skeletonCode) {
                                    llmPrompt = llmPrompt.replace(skeletonCode, resolvedSkeleton);
                                    console.log(`[STAGE-1] ✓ Applied resolved enums to skeleton (${applyDuration}ms)`);
                                }
                            }
                        } else {
                            console.warn(`[STAGE-1] ⚠️  Could not parse enum resolver response`);
                        }
                    }
                    
                    const stage1TotalDuration = Date.now() - stage1StartTime;
                    console.log(`[STAGE-1] ✅ COMPLETE - Total time: ${stage1TotalDuration}ms (LLM: ${llmCallDuration}ms | Parse: ${parseDuration}ms | Apply: ${applyDuration}ms)`);
                    
                } catch (enumError: unknown) {
                    console.warn(`[STAGE-1] ❌ Enum resolution failed, continuing with TODOs:`, enumError);
                    // Non-fatal: main LLM will attempt enum resolution as fallback
                }
            }
            
            // ================================================================
            // STAGE 2: Code Enhancement (user-selected model)
            // ================================================================
            if (llmPrompt && selectedModel) {
                try {
                    console.log(`[STAGE-2] Enhancing code with ${selectedModel}...`);
                    
                    this.panel?.webview.postMessage({
                        command: 'llmProgress',
                        message: `Stage 2: Enhancing with ${selectedModel}...`
                    });
                    
                    const enhancedCode = await this.callVSCodeLLM(selectedModel, llmPrompt);
                    
                    if (enhancedCode) {
                        console.log(`[STAGE-2] LLM enhancement complete (${enhancedCode.length} chars)`);
                        result.test_code = enhancedCode;
                        result.llm_enhancement.enhanced_code = enhancedCode;
                        
                        // Save enhanced code to the output file
                        if (result.output_file) {
                            try {
                                const fs = require('fs');
                                const header = [
                                    `/* Auto-generated test: ${result.test_id} */`,
                                    `/* Module: ${result.module} */`,
                                    `/* Description: ${result.description} */`,
                                    `/* Generated: ${new Date().toISOString()} */`,
                                    `/* LLM Model: ${selectedModel} */`,
                                    `/* LLM Enhanced: YES */`,
                                    ''
                                ].join('\n');
                                fs.writeFileSync(result.output_file, header + '\n' + enhancedCode, 'utf8');
                                console.log(`[STAGE-2] Enhanced code saved to: ${result.output_file}`);
                            } catch (fsErr) {
                                console.warn(`[STAGE-2] Could not save enhanced code to file:`, fsErr);
                            }
                        }
                    }
                } catch (llmError: unknown) {
                    console.warn(`[STAGE-2] LLM enhancement failed, using skeleton:`, llmError);
                    // Continue with skeleton code - not a fatal error
                }
            }
            
            this.panel?.webview.postMessage({
                command: 'generationComplete',
                data: result
            });
        } catch (error: unknown) {
            this.panel?.webview.postMessage({
                command: 'generationError',
                error: String(error)
            });
        }
    }
    
    /**
     * Parse the JSON response from the enum resolver model (gpt-5-mini).
     * Handles various response formats: pure JSON, markdown-wrapped JSON, etc.
     * 
     * DATA-DRIVEN: Extracts any valid JSON object from the response text.
     */
    private parseEnumResolverResponse(response: string): Record<string, string> | null {
        try {
            // Try 1: Direct JSON parse
            const trimmed = response.trim();
            if (trimmed.startsWith('{')) {
                return JSON.parse(trimmed);
            }
            
            // Try 2: Extract JSON from markdown code block
            const jsonMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[1].trim());
            }
            
            // Try 3: Find first { ... } block in the response
            const braceStart = trimmed.indexOf('{');
            const braceEnd = trimmed.lastIndexOf('}');
            if (braceStart !== -1 && braceEnd > braceStart) {
                return JSON.parse(trimmed.substring(braceStart, braceEnd + 1));
            }
            
            return null;
        } catch (parseError) {
            console.warn(`[STAGE-1] JSON parse failed:`, parseError);
            return null;
        }
    }
    
    /**
     * Call VS Code's Language Model API to enhance test code
     */
    private async callVSCodeLLM(modelId: string, prompt: string): Promise<string | null> {
        try {
            // Find matching model from VS Code's available models
            const models = await vscode.lm.selectChatModels({ id: modelId });
            
            let model = models[0];
            if (!model) {
                // Try broader search by family/name
                const allModels = await vscode.lm.selectChatModels();
                model = allModels.find(m => m.id === modelId || m.id.includes(modelId)) || allModels[0];
            }
            
            if (!model) {
                console.warn(`[LLM] No VS Code LM model found for: ${modelId}`);
                return null;
            }
            
            console.log(`[LLM] Using model: ${model.id} (${model.vendor})`);
            
            // Create chat messages
            const messages = [
                vscode.LanguageModelChatMessage.User(prompt)
            ];
            
            // Send request to the language model
            const response = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
            
            // Collect the streamed response
            let fullResponse = '';
            for await (const chunk of response.text) {
                fullResponse += chunk;
            }
            
            // Extract code from response (may be wrapped in markdown code blocks)
            const codeMatch = fullResponse.match(/```(?:c|C)?\n([\s\S]*?)```/);
            if (codeMatch) {
                return codeMatch[1].trim();
            }
            
            // If no code block found, return the full response if it looks like C code
            if (fullResponse.includes('#include') || fullResponse.includes('void ') || fullResponse.includes('int ')) {
                return fullResponse.trim();
            }
            
            return fullResponse.trim();
            
        } catch (error: unknown) {
            console.error(`[LLM] VS Code LM API error:`, error);
            throw error;
        }
    }
    
    /**
     * Handle model selection from webview
     */
    private async handleSelectModel(data: any) {
        try {
            await this.backendClient.selectModel(data.model);
            
            this.panel?.webview.postMessage({
                command: 'modelSwitched',
                model: data.model
            });
        } catch (error: unknown) {
            this.panel?.webview.postMessage({
                command: 'error',
                error: String(error)
            });
        }
    }
    
    /**
     * Handle accept test — open the generated file in the editor
     */
    private async handleAcceptTest(data: any) {
        try {
            if (data && data.output_file) {
                const filePath = data.output_file;
                const uri = vscode.Uri.file(filePath);
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
                vscode.window.showInformationMessage(`Test accepted: ${filePath}`);
            } else {
                vscode.window.showInformationMessage('Test accepted.');
            }
        } catch (error: unknown) {
            vscode.window.showWarningMessage(`Could not open file: ${String(error)}`);
        }
    }
    
    /**
     * Get available models - waits for modelsReady before querying backend
     */
    private async handleGetModels() {
        try {
            // Wait for models to be discovered (with 10s timeout)
            await Promise.race([
                this.modelsReady,
                new Promise(resolve => setTimeout(resolve, 10000))
            ]);
            
            const models = await this.backendClient.getAvailableModels();
            
            this.panel?.webview.postMessage({
                command: 'modelsList',
                models
            });
        } catch (error: unknown) {
            this.panel?.webview.postMessage({
                command: 'error',
                error: String(error)
            });
        }
    }
    
    /**
     * Get available modules
     */
    private async handleGetModules() {
        try {
            const modules = await this.backendClient.getAvailableModules();
            
            this.panel?.webview.postMessage({
                command: 'modulesList',
                modules
            });
        } catch (error: unknown) {
            this.panel?.webview.postMessage({
                command: 'error',
                error: String(error)
            });
        }
    }
    
    /**
     * Notify webview that model has changed
     */
    notifyModelChanged(model: string) {
        this.panel?.webview.postMessage({
            command: 'modelSwitched',
            model
        });
    }
    
    /**
     * Show test summary
     */
    showSummary(result: any) {
        const panel = this.showPanel();
        
        panel.webview.postMessage({
            command: 'showSummary',
            summary: {
                testId: result.test_id,
                complianceScore: result.compliance_score,
                ragContext: result.rag_context,
                kgContext: result.kg_context,
                llmEnhancement: result.llm_enhancement
            }
        });
    }
}
