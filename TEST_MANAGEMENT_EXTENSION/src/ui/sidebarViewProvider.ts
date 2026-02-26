import * as vscode from 'vscode';
import { BackendClient } from '../backend/client';

/**
 * Provides the sidebar webview view for the Test Generator.
 * This is registered with the "testManagementView" view ID declared in package.json.
 * 
 * The sidebar acts as a launcher — clicking the beaker icon opens the 
 * full Test Generator panel in the editor area for a proper workspace experience.
 */
export class SidebarViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'testManagementView';

    private _view?: vscode.WebviewView;
    private context: vscode.ExtensionContext;
    private backendClient: BackendClient;

    constructor(context: vscode.ExtensionContext, backendClient: BackendClient) {
        this.context = context;
        this.backendClient = backendClient;
    }

    /**
     * Called by VS Code when the sidebar view needs to be rendered.
     * Shows a launcher UI that opens the full panel in the editor area.
     */
    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void | Thenable<void> {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.context.extensionUri]
        };

        webviewView.webview.html = this.getLauncherHtml();

        webviewView.webview.onDidReceiveMessage(
            (message: any) => {
                if (message.command === 'openPanel') {
                    vscode.commands.executeCommand('testManagement.showPanel');
                }
            },
            undefined,
            this.context.subscriptions
        );

        // Auto-open the full panel when the sidebar view becomes visible
        vscode.commands.executeCommand('testManagement.showPanel');

        console.log('[TEST-MANAGEMENT] Sidebar launcher resolved — opening full panel');
    }

    /**
     * Simple launcher HTML for the sidebar
     */
    private getLauncherHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background-color: var(--vscode-sideBar-background);
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }
        .icon { font-size: 48px; margin-bottom: 12px; }
        h3 { margin-bottom: 8px; font-size: 14px; }
        p { font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 16px; }
        button {
            width: 100%;
            padding: 8px 16px;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            font-size: 13px;
            cursor: pointer;
            font-weight: 500;
        }
        button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }
    </style>
</head>
<body>
    <div class="icon">🧪</div>
    <h3>Test Generator</h3>
    <p>Generate semantic test code using RAG + Knowledge Graph</p>
    <button id="openBtn">Open Test Generator</button>
    <script>
        const vscode = acquireVsCodeApi();
        document.getElementById('openBtn').addEventListener('click', () => {
            vscode.postMessage({ command: 'openPanel' });
        });
    </script>
</body>
</html>`;
    }
}
