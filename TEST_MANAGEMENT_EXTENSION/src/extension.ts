import * as vscode from 'vscode';
import { BackendClient } from './backend/client';
import { WebviewManager } from './ui/webview';
import { SidebarViewProvider } from './ui/sidebarViewProvider';
import { FileGenerator } from './generators/fileGenerator';

let extensionContext: vscode.ExtensionContext;
let backendClient: BackendClient;
let webviewManager: WebviewManager;
let sidebarProvider: SidebarViewProvider;
let fileGenerator: FileGenerator;

// Promise that resolves when LLM models have been discovered and sent to backend
let modelsReadyResolve: () => void;
const modelsReady: Promise<void> = new Promise(resolve => { modelsReadyResolve = resolve; });

/**
 * Activation handler for the extension
 */
export async function activate(context: vscode.ExtensionContext) {
    console.log('[TEST-MANAGEMENT] Extension activated');
    
    extensionContext = context;
    
    // Initialize backend client
    const backendUrl = vscode.workspace.getConfiguration('testManagement').get<string>('backendUrl') || 'http://localhost:8000';
    backendClient = new BackendClient(backendUrl);
    
    // Initialize webview manager (pass modelsReady promise so it waits for model discovery)
    webviewManager = new WebviewManager(context, backendClient, modelsReady);
    
    // Initialize and register sidebar webview provider
    sidebarProvider = new SidebarViewProvider(context, backendClient);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            SidebarViewProvider.viewType,
            sidebarProvider
        )
    );
    
    // Initialize file generator
    fileGenerator = new FileGenerator();
    
    // Register commands first (so UI is available immediately)
    registerCommands(context);
    
    // Connect to backend with retries (backend may still be starting up)
    connectToBackendWithRetry(backendUrl, 10, 3000);
}

/**
 * Connect to backend with retries (backend may still be starting up)
 */
async function connectToBackendWithRetry(backendUrl: string, maxRetries: number, delayMs: number) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const health = await backendClient.checkHealth();
            if (health) {
                console.log(`[TEST-MANAGEMENT] Backend connected on attempt ${attempt}`);
                vscode.window.showInformationMessage('✅ Test Management System connected to backend');
                
                // Now send LLM models to backend
                await discoverAndSendLLMModels();
                return;
            }
        } catch (error: unknown) {
            console.log(`[TEST-MANAGEMENT] Backend not ready (attempt ${attempt}/${maxRetries}), retrying in ${delayMs/1000}s...`);
        }
        
        // Wait before next retry
        await new Promise(resolve => setTimeout(resolve, delayMs));
    }
    
    // All retries exhausted - resolve modelsReady so webview doesn't hang
    modelsReadyResolve();
    
    vscode.window.showWarningMessage(
        '⚠️ Could not connect to backend at ' + backendUrl + '. Click "Retry" to try again.',
        'Retry'
    ).then(choice => {
        if (choice === 'Retry') {
            connectToBackendWithRetry(backendUrl, 10, 3000);
        }
    });
}

/**
 * Discover available LLM models from VS Code and send to backend
 */
async function discoverAndSendLLMModels() {
    try {
        // Get all available chat models from VS Code
        const models = await vscode.lm.selectChatModels();
        
        if (models.length === 0) {
            console.log('[TEST-MANAGEMENT] No LLM models available in VS Code');
            modelsReadyResolve(); // Resolve even if empty, so webview doesn't hang
            return;
        }
        
        // Extract model names/IDs
        const modelNames = models.map(model => model.id || model.vendor || 'unknown');
        console.log(`[TEST-MANAGEMENT] Discovered ${modelNames.length} LLM models:`, modelNames);
        
        // Send to backend via environment variable or API call
        // The backend will use these models for dynamic selection
        try {
            await backendClient.updateAvailableModels(modelNames);
            console.log('[TEST-MANAGEMENT] LLM models sent to backend');
        } catch (error) {
            console.warn('[TEST-MANAGEMENT] Could not update backend with models:', error);
        }
    } catch (error) {
        console.warn('[TEST-MANAGEMENT] Could not discover LLM models:', error);
    }
    
    // Signal that models are ready (or best-effort done)
    modelsReadyResolve();
}

/**
 * Register all extension commands
 */
function registerCommands(context: vscode.ExtensionContext) {
    // Show test generator panel
    context.subscriptions.push(
        vscode.commands.registerCommand('testManagement.showPanel', () => {
            webviewManager.showPanel();
        })
    );
    
    // Generate test
    context.subscriptions.push(
        vscode.commands.registerCommand('testManagement.generateTest', async (description?: string) => {
            try {
                const panel = webviewManager.showPanel();
                
                if (description) {
                    // Generate directly if description provided
                    await generateTest(description);
                }
            } catch (error: unknown) {
                vscode.window.showErrorMessage(`❌ Failed to generate test: ${error}`);
            }
        })
    );
    
    // Select module
    context.subscriptions.push(
        vscode.commands.registerCommand('testManagement.selectModule', async () => {
            const modules = ['cxpi', 'lin', 'btl', 'can'];
            const selected = await vscode.window.showQuickPick(modules, {
                placeHolder: 'Select a module'
            });
            
            if (selected) {
                const config = vscode.workspace.getConfiguration('testManagement');
                await config.update('module', selected, vscode.ConfigurationTarget.Global);
                vscode.window.showInformationMessage(`✅ Module changed to: ${selected}`);
            }
        })
    );
    
    // Switch LLM model
    context.subscriptions.push(
        vscode.commands.registerCommand('testManagement.switchModel', async () => {
            try {
                const models = await backendClient.getAvailableModels();
                
                if (!models || models.length === 0) {
                    vscode.window.showErrorMessage('❌ No LLM models available. Configure GITHUB_COPILOT_MODELS environment variable.');
                    return;
                }
                
                const current = models.find((m: any) => m.isCurrent) || models[0];
                const items = models.map((m: any) => ({
                    label: m.name + (m.isCurrent ? ' ✓' : ''),
                    model: m.name
                }));
                
                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: `Current: ${current?.name}. Select a model to switch:`
                });
                
                if (selected && selected.model !== current?.name) {
                    await backendClient.selectModel(selected.model);
                    vscode.window.showInformationMessage(`✅ Switched to model: ${selected.model}`);
                    
                    // Notify webview
                    webviewManager.notifyModelChanged(selected.model);
                }
            } catch (error: unknown) {
                vscode.window.showErrorMessage(`❌ Failed to switch model: ${error}`);
            }
        })
    );
}

/**
 * Generate a test
 */
export async function generateTest(description: string) {
    try {
        const config = vscode.workspace.getConfiguration('testManagement');
        const module = config.get<string>('module') || 'cxpi';
        
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Generating test...',
            cancellable: false
        }, async (progress: vscode.Progress<{ increment: number }>) => {
            // Query backend
            progress.report({ increment: 20 });
            const result = await backendClient.generateTest({
                module,
                description,
                additional_notes: '',
                llm_model: config.get<string>('llmModel')
            });
            
            progress.report({ increment: 30 });
            
            // Generate files
            const files = fileGenerator.generateFiles(result);
            
            progress.report({ increment: 20 });
            
            // Save files to workspace
            const outputDir = config.get<string>('outputDirectory') || 'generated_tests';
            const savedFiles = await fileGenerator.saveFiles(files, outputDir);
            
            progress.report({ increment: 20 });
            
            // Show completion message
            vscode.window.showInformationMessage(
                `✅ Test generated successfully! Created ${savedFiles.length} file(s).`,
                'Open Folder',
                'View Summary'
            ).then((choice: string | undefined) => {
                if (choice === 'Open Folder') {
                    vscode.commands.executeCommand('revealFileInOS', 
                        vscode.Uri.file(savedFiles[0]));
                } else if (choice === 'View Summary') {
                    webviewManager.showSummary(result);
                }
            });
        });
    } catch (error: unknown) {
        vscode.window.showErrorMessage(`❌ Test generation failed: ${error}`);
    }
}

/**
 * Deactivation handler
 */
export function deactivate() {
    console.log('[TEST-MANAGEMENT] Extension deactivated');
}
